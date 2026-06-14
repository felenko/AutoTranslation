"""
Ties STT + translation together and feeds results to a broadcast callback.
"""
import asyncio
from typing import Callable, Awaitable

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
        import traceback
        print("[Pipeline] WARNING: building MyMemoryEngine — stack:")
        traceback.print_stack()
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
    def __init__(self, cfg: Config, on_subtitle: Callable[[str, str], Awaitable[None]]):
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

        print(f"[Pipeline] target language: {cfg.translation.target_language}")

    def reload_engines(self, cfg: Config) -> None:
        """Full engine reload (kept for compatibility)."""
        self._cfg = cfg
        self._stt = build_stt_engine(cfg)
        self._translation = build_translation_engine(cfg)

    async def run(self) -> None:
        async for chunk in self._capture.stream():
            asyncio.create_task(self._process(chunk))

    async def _process(self, audio: bytes) -> None:
        try:
            await self._process_inner(audio)
        except Exception as exc:
            import traceback
            print(f"[Pipeline] UNHANDLED ERROR in _process: {exc}")
            traceback.print_exc()

    async def _process_inner(self, audio: bytes) -> None:
        self._chunks_seen += 1
        if self._chunks_seen == 1:
            print(f"[Pipeline] first audio chunk received ({len(audio)} bytes)")

        transcript, detected_lang = await self._stt.transcribe(audio, self._cfg.audio.sample_rate)
        if not transcript:
            if not self._warned_silence:
                self._warned_silence = True
                print(
                    "[STT] no speech detected in audio chunk. "
                    "Make sure sound is playing through your default output device "
                    "(the loopback device shown in [AudioCapture])."
                )
            return

        source_lang = self._cfg.translation.source_language or detected_lang
        print(f"[STT] transcript [{detected_lang}]: {transcript[:120]}")
        print(f"[Pipeline] translating {source_lang} -> '{self._cfg.translation.target_language}' "
              f"using engine '{self._cfg.translation.engine}'")

        translation = await self._translation.translate(
            transcript, self._cfg.translation.target_language, source_lang
        )

        print(f"[Pipeline] translation result: {translation[:120]}")
        print(f"[Pipeline] calling on_subtitle ...")
        await self._on_subtitle(transcript, translation)
        print(f"[Pipeline] on_subtitle completed")
