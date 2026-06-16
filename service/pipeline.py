"""
Ties STT + translation together and feeds results to a broadcast callback.
"""
import asyncio
import difflib
import time
from typing import Callable, Awaitable, Optional

from .audio_capture import AudioCapture
from .config import Config
from .engines.stt import STTEngine, WhisperAPIEngine, LocalWhisperEngine
from .engines.translation import TranslationEngine, ClaudeEngine, CursorEngine, LingvaEngine, MyMemoryEngine, OpenAIEngine, OllamaEngine


def build_stt_engine(cfg: Config) -> STTEngine:
    if cfg.stt.engine == "whisper_local":
        return LocalWhisperEngine(model_size=cfg.stt.whisper_local.model_size)
    return WhisperAPIEngine(
        api_key=cfg.stt.whisper_api.api_key,
        model=cfg.stt.whisper_api.model,
    )


def build_translation_engine(cfg: Config) -> TranslationEngine:
    if cfg.translation.engine == "mymemory":
        return MyMemoryEngine()
    if cfg.translation.engine == "lingva":
        return LingvaEngine()
    if cfg.translation.engine == "openai":
        return OpenAIEngine(
            api_key=cfg.translation.openai.api_key,
            model=cfg.translation.openai.model,
        )
    if cfg.translation.engine == "ollama":
        return OllamaEngine(
            host=cfg.translation.ollama.host,
            model=cfg.translation.ollama.model,
        )
    if cfg.translation.engine == "cursor":
        return CursorEngine(
            model=cfg.translation.cursor.model,
            token=cfg.translation.cursor.token,
        )
    return ClaudeEngine(
        api_key=cfg.translation.claude.api_key,
        model=cfg.translation.claude.model,
    )


def _translation_settings_changed(cfg: Config, old: Config) -> bool:
    tr, prev = cfg.translation, old.translation
    if tr.engine == "mymemory":
        return False
    if tr.engine == "openai":
        return tr.openai.api_key != prev.openai.api_key or tr.openai.model != prev.openai.model
    if tr.engine == "ollama":
        return tr.ollama.host != prev.ollama.host or tr.ollama.model != prev.ollama.model
    if tr.engine == "cursor":
        return tr.cursor.model != prev.cursor.model or tr.cursor.token != prev.cursor.token
    return tr.claude.api_key != prev.claude.api_key or tr.claude.model != prev.claude.model


class Pipeline:
    def __init__(self, cfg: Config, on_subtitle: Callable[[str, str, Optional[bytes]], Awaitable[None]]):
        self._cfg = cfg
        self._on_subtitle = on_subtitle
        self._chunks_seen = 0
        self._warned_silence = False
        print(f"[Pipeline] STT engine: {cfg.stt.engine}")
        self._stt = build_stt_engine(cfg)
        print(f"[Pipeline] translation engine: {cfg.translation.engine}")
        self._translation = build_translation_engine(cfg)
        self._capture = AudioCapture(
            chunk_duration=cfg.audio.chunk_duration_seconds,
            sample_rate=cfg.audio.sample_rate,
        )
        self._tts_mute_until = 0.0
        self._recent_tts: list[tuple[str, float]] = []  # (text, monotonic timestamp)
        self._active_tasks = 0

    def update_config(self, cfg: Config) -> None:
        """Apply settings changes without reloading heavy engines unnecessarily."""
        old = self._cfg
        self._cfg = cfg

        stt_changed = (
            cfg.stt.engine != old.stt.engine
            or cfg.stt.whisper_api.api_key != old.stt.whisper_api.api_key
            or cfg.stt.whisper_api.model != old.stt.whisper_api.model
            or cfg.stt.whisper_local.model_size != old.stt.whisper_local.model_size
        )
        if stt_changed:
            print(f"[Pipeline] reloading STT engine: {cfg.stt.engine}")
            self._stt = build_stt_engine(cfg)

        tr_changed = cfg.translation.engine != old.translation.engine or _translation_settings_changed(cfg, old)
        if tr_changed:
            print(f"[Pipeline] reloading translation engine: {cfg.translation.engine}")
            self._translation = build_translation_engine(cfg)

        print(f"[Pipeline] target language: {cfg.translation.target_language}, TTS: {cfg.tts.enabled}")

    def reload_engines(self, cfg: Config) -> None:
        """Full engine reload (kept for compatibility)."""
        self._cfg = cfg
        self._capture._chunk_duration = cfg.audio.chunk_duration_seconds
        print(f"[Pipeline] chunk duration -> {cfg.audio.chunk_duration_seconds}s")
        self._stt = build_stt_engine(cfg)
        self._translation = build_translation_engine(cfg)

    async def run(self) -> None:
        async for chunk in self._capture.stream():
            if self._active_tasks >= 2:
                continue  # drop chunk to stay current rather than building a backlog
            asyncio.create_task(self._process(chunk))

    async def _process(self, audio: bytes) -> None:
        self._active_tasks += 1
        try:
            await self._process_inner(audio)
        except Exception as exc:
            import traceback
            print(f"[Pipeline] error: {exc}")
            traceback.print_exc()
        finally:
            self._active_tasks -= 1

    def _is_tts_echo(self, transcript: str, detected_lang: str = "") -> bool:
        now = time.monotonic()
        self._recent_tts = [(t, ts) for t, ts in self._recent_tts if now - ts < 15.0]
        if not self._recent_tts:
            return False

        # Language mismatch: source is configured (e.g. Russian) but STT detected a
        # different language — almost certainly a TTS echo leaking into the loopback.
        if detected_lang and self._cfg.translation.source_language:
            cfg = self._cfg.translation.source_language.lower()
            det = detected_lang.lower()
            if not (cfg.startswith(det) or det.startswith(cfg[:2])):
                print(f"[echo] lang mismatch ({detected_lang} ≠ {cfg}): {transcript!r}")
                return True

        norm = transcript.lower().strip(" .,!?-")
        if len(norm) < 3:
            return True  # too short to be real when TTS was recently played

        for text, _ in self._recent_tts:
            ref = text.lower().strip(" .,!?-")
            # Full-text similarity
            if difflib.SequenceMatcher(None, norm, ref).ratio() > 0.65:
                print(f"[echo] suppressed: {transcript!r}")
                return True
            # Partial match: transcript is a tail/head fragment of a TTS phrase
            if len(norm) >= 5 and (norm in ref or ref.endswith(norm) or ref.startswith(norm)):
                print(f"[echo] partial suppressed: {transcript!r}")
                return True

        return False

    async def _process_inner(self, audio: bytes) -> None:
        if time.monotonic() < self._tts_mute_until:
            return

        transcript, detected_lang = await self._stt.transcribe(audio, self._cfg.audio.sample_rate)
        if not transcript:
            if not self._warned_silence:
                self._warned_silence = True
                print("[STT] no speech detected — make sure audio is playing through the loopback device")
            return

        print(f"[original] [{detected_lang}] {transcript}")

        if self._is_tts_echo(transcript, detected_lang):
            return

        source_lang = self._cfg.translation.source_language or detected_lang
        translation = await self._translation.translate(
            transcript, self._cfg.translation.target_language, source_lang
        )

        print(f"[translated]          {translation}")

        tts_audio: Optional[bytes] = None
        if self._cfg.tts.enabled and translation:
            try:
                from .engines.tts.edge import synthesize
                tts_audio = await synthesize(
                    translation,
                    self._cfg.translation.target_language,
                    self._cfg.tts.voice_gender,
                    self._cfg.tts.rate,
                )
                if tts_audio:
                    self._tts_mute_until = time.monotonic() + 0.4
                    self._recent_tts.append((translation, time.monotonic()))
                else:
                    print("[TTS] WARNING: edge-tts returned empty audio")
            except ImportError as e:
                print(f"[TTS] ERROR: {e}")
            except Exception as exc:
                print(f"[TTS] ERROR: {exc}")

        await self._on_subtitle(transcript, translation, tts_audio)
