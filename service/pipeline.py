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


# Maps common language names to Whisper's ISO 639-1 codes.
# Short codes (≤3 chars) are passed through as-is.
_LANG_TO_CODE: dict[str, str] = {
    "afrikaans": "af", "arabic": "ar", "armenian": "hy", "azerbaijani": "az",
    "belarusian": "be", "bosnian": "bs", "bulgarian": "bg", "catalan": "ca",
    "chinese": "zh", "croatian": "hr", "czech": "cs", "danish": "da",
    "dutch": "nl", "english": "en", "estonian": "et", "finnish": "fi",
    "french": "fr", "galician": "gl", "german": "de", "greek": "el",
    "hebrew": "he", "hindi": "hi", "hungarian": "hu", "icelandic": "is",
    "indonesian": "id", "italian": "it", "japanese": "ja", "korean": "ko",
    "latvian": "lv", "lithuanian": "lt", "macedonian": "mk", "malay": "ms",
    "maori": "mi", "nepali": "ne", "norwegian": "no", "persian": "fa",
    "polish": "pl", "portuguese": "pt", "romanian": "ro", "russian": "ru",
    "serbian": "sr", "slovak": "sk", "slovenian": "sl", "spanish": "es",
    "swahili": "sw", "swedish": "sv", "tagalog": "tl", "tamil": "ta",
    "thai": "th", "turkish": "tr", "ukrainian": "uk", "urdu": "ur",
    "vietnamese": "vi", "welsh": "cy",
}

def _strip_overlap(prev: str, curr: str, max_words: int = 10) -> str:
    """Remove leading words from curr that duplicate the tail of prev (overlap region).

    Uses exact word matching first, then a fuzzy SequenceMatcher fallback for cases
    where Whisper slightly rephrases the overlap audio.
    """
    if not prev or not curr:
        return curr
    pw = prev.split()
    cw = curr.split()
    if not cw:
        return curr
    # Exact match: find longest suffix of prev that equals a prefix of curr.
    for n in range(min(len(pw), len(cw), max_words), 0, -1):
        if pw[-n:] == cw[:n]:
            return " ".join(cw[n:]).strip()
    # Fuzzy fallback: require at least 2 consecutive matching words at the boundary.
    sm = difflib.SequenceMatcher(None, pw[-max_words:], cw[:max_words])
    for block in sm.get_matching_blocks():
        if block.b == 0 and block.size >= 2:
            return " ".join(cw[block.size:]).strip()
    return curr


def _to_whisper_lang(lang: str) -> str | None:
    if not lang:
        return None
    lang = lang.strip().lower()
    if len(lang) <= 3:
        return lang
    return _LANG_TO_CODE.get(lang)


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
            capture_device=cfg.audio.capture_device,
            playback_device=cfg.tts.playback_device,
            original_volume=cfg.audio.original_volume,
            overlap_seconds=cfg.audio.overlap_seconds,
        )
        self._tts_mute_until = 0.0
        self._recent_tts: list[tuple[str, float]] = []  # (text, monotonic timestamp)
        self._prev_transcript: str = ""  # last reported transcript, used for overlap dedup + prompt

    def update_config(self, cfg: Config) -> None:
        """Apply settings changes without reloading heavy engines unnecessarily."""
        old = self._cfg
        self._cfg = cfg

        if cfg.audio.chunk_duration_seconds != old.audio.chunk_duration_seconds:
            self._capture._chunk_duration = cfg.audio.chunk_duration_seconds
            self._prev_transcript = ""
            self._capture._tail_buf = b""
            print(f"[Pipeline] chunk duration -> {cfg.audio.chunk_duration_seconds}s")
        if cfg.audio.original_volume != old.audio.original_volume:
            self._capture._original_volume = cfg.audio.original_volume
        if cfg.audio.overlap_seconds != old.audio.overlap_seconds:
            self._capture._overlap_seconds = cfg.audio.overlap_seconds
            self._capture._tail_buf = b""
            print(f"[Pipeline] overlap -> {cfg.audio.overlap_seconds}s")

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

        print(f"[Pipeline] chunk={cfg.audio.chunk_duration_seconds}s lang={cfg.translation.source_language}->{cfg.translation.target_language} TTS={cfg.tts.enabled}")

    def reload_engines(self, cfg: Config) -> None:
        """Full engine reload (kept for compatibility)."""
        self._cfg = cfg
        self._capture._chunk_duration = cfg.audio.chunk_duration_seconds
        print(f"[Pipeline] chunk duration -> {cfg.audio.chunk_duration_seconds}s")
        self._stt = build_stt_engine(cfg)
        self._translation = build_translation_engine(cfg)

    async def run(self) -> None:
        async for chunk, captured_at in self._capture.stream():
            await self._process(chunk, captured_at)

    async def _process(self, audio: bytes, captured_at: float) -> None:
        try:
            await self._process_inner(audio, captured_at)
        except Exception as exc:
            import traceback
            print(f"[Pipeline] error: {exc}")
            traceback.print_exc()

    def _is_translation_echo(self, translation: str) -> bool:
        """Check if translation matches a recently synthesized TTS phrase.

        When English TTS audio leaks back through the loopback, Whisper (forced to
        source language) transcribes it as a phonetic approximation in that language.
        The resulting transcript passes the transcript-level echo checks because it
        doesn't look like English, but after translation the output is similar to
        what we originally synthesized.  Comparing *translations* against the TTS
        history catches this second-order echo path.
        """
        now = time.monotonic()
        norm = translation.lower().strip(" .,!?-")
        if not norm:
            return False
        for text, ts in self._recent_tts:
            if now - ts > 15.0:
                continue
            ref = text.lower().strip(" .,!?-")
            if difflib.SequenceMatcher(None, norm, ref).ratio() > 0.65:
                print(f"[echo] translation echo suppressed: {translation!r}")
                return True
            if len(norm) >= 5 and (norm in ref or ref.endswith(norm) or ref.startswith(norm)):
                print(f"[echo] translation partial echo suppressed: {translation!r}")
                return True
        return False

    def _is_tts_echo(self, transcript: str, detected_lang: str = "", captured_at: float = 0.0) -> bool:
        now = time.monotonic()
        self._recent_tts = [(t, ts) for t, ts in self._recent_tts if now - ts < 15.0]
        if not self._recent_tts:
            return False

        # Language mismatch: source is configured (e.g. Russian) but STT detected
        # something else — almost certainly TTS echo leaking into the loopback.
        if detected_lang and self._cfg.translation.source_language:
            src = self._cfg.translation.source_language.lower()
            det = detected_lang.lower()
            if not (src.startswith(det) or det.startswith(src[:2])):
                print(f"[echo] lang mismatch ({detected_lang} ≠ {src}): {transcript!r}")
                return True

        norm = transcript.lower().strip(" .,!?-")
        # Only suppress very short utterances if TTS was playing VERY recently (3 s),
        # not for the full 15-second history — real speech can be short too.
        very_recent = any(now - ts < 3.0 for _, ts in self._recent_tts)
        if len(norm) < 3 and very_recent:
            return True

        for text, _ in self._recent_tts:
            ref = text.lower().strip(" .,!?-")
            if difflib.SequenceMatcher(None, norm, ref).ratio() > 0.65:
                print(f"[echo] suppressed: {transcript!r}")
                return True
            if len(norm) >= 5 and (norm in ref or ref.endswith(norm) or ref.startswith(norm)):
                print(f"[echo] partial suppressed: {transcript!r}")
                return True

        return False

    async def _process_inner(self, audio: bytes, captured_at: float) -> None:
        # Use the chunk's capture timestamp (not wall-clock now) so that chunks
        # which were queued during a mute window are correctly discarded even if
        # they are dequeued after the mute has expired.
        if captured_at < self._tts_mute_until:
            print(f"[mute] dropping chunk captured at {captured_at:.1f} (mute until {self._tts_mute_until:.1f})")
            # Flush overlap state: the next chunk's tail won't align with anything we'll report.
            self._prev_transcript = ""
            self._capture._tail_buf = b""
            return

        whisper_lang = _to_whisper_lang(self._cfg.translation.source_language)
        # Pass last ~100 chars of previous transcript so Whisper can continue naturally.
        prompt = self._prev_transcript[-100:] if self._prev_transcript else None
        transcript_full, detected_lang = await self._stt.transcribe(
            audio, self._cfg.audio.sample_rate, language=whisper_lang, prompt=prompt
        )
        if not transcript_full:
            if not self._warned_silence:
                self._warned_silence = True
                print("[STT] no speech detected — make sure audio is playing through the loopback device")
            return

        # Remove words already reported from the overlap region at the start of this chunk.
        transcript = _strip_overlap(self._prev_transcript, transcript_full)
        if not transcript:
            return  # entire result was overlap repetition — nothing new to report

        self._prev_transcript = transcript
        print(f"[original] [{detected_lang}] {transcript}")

        if self._is_tts_echo(transcript, detected_lang, captured_at):
            return

        if not self._cfg.translation.enabled:
            # Translation disabled — show original transcript as subtitle
            await self._on_subtitle(transcript, transcript, None)
            return

        source_lang = self._cfg.translation.source_language or detected_lang
        translation = await self._translation.translate(
            transcript, self._cfg.translation.target_language, source_lang
        )

        print(f"[translated]          {translation}")

        if self._is_translation_echo(translation):
            return

        tts_audio: Optional[bytes] = None
        if self._cfg.tts.enabled and translation:
            play_secs = len(translation) / max(12.5 * self._cfg.tts.rate, 1.0)
            chunk_s = self._cfg.audio.chunk_duration_seconds
            self._tts_mute_until = time.monotonic() + min(play_secs + chunk_s + 2.0, 30.0)
            self._recent_tts.append((translation, time.monotonic()))

            if self._cfg.tts.playback_device:
                # Local device: fire synthesis in background so pipeline isn't blocked
                asyncio.create_task(self._tts_local(
                    translation,
                    self._cfg.translation.target_language,
                    self._cfg.tts.voice_gender,
                    self._cfg.tts.rate,
                    self._cfg.tts.playback_device,
                    self._cfg.tts.tts_volume,
                ))
            else:
                # Browser path: audio must accompany the subtitle message
                try:
                    from .engines.tts.edge import synthesize
                    tts_audio = await synthesize(
                        translation,
                        self._cfg.translation.target_language,
                        self._cfg.tts.voice_gender,
                        self._cfg.tts.rate,
                    )
                    if not tts_audio:
                        print("[TTS] WARNING: edge-tts returned empty audio")
                        self._tts_mute_until = 0.0
                except Exception as exc:
                    print(f"[TTS] ERROR: {exc}")
                    self._tts_mute_until = 0.0

        await self._on_subtitle(transcript, translation, tts_audio)

    async def _tts_local(self, text: str, target_lang: str, voice_gender: str,
                         rate: float, device: str, volume: float) -> None:
        try:
            from .engines.tts.edge import synthesize, play_locally
            raw_audio = await synthesize(text, target_lang, voice_gender, rate)
            if raw_audio:
                await asyncio.get_event_loop().run_in_executor(
                    None, play_locally, raw_audio, device, volume
                )
            else:
                print("[TTS] WARNING: edge-tts returned empty audio")
                self._tts_mute_until = 0.0
        except Exception as exc:
            print(f"[TTS] ERROR: {exc}")
            self._tts_mute_until = 0.0
