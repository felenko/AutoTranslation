import asyncio
import numpy as np
from .base import STTEngine


class LocalWhisperEngine(STTEngine):
    def __init__(self, model_size: str = "base"):
        # Import lazily so the service starts even if faster-whisper isn't installed
        from faster_whisper import WhisperModel

        print(
            f"[WhisperLocal] loading model '{model_size}' "
            "(first run downloads ~150 MB from Hugging Face, then caches locally)..."
        )
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8", num_workers=2)
        print(f"[WhisperLocal] model '{model_size}' ready")

    async def transcribe(
        self, audio_bytes: bytes, sample_rate: int, language: str | None = None,
        prompt: str | None = None,
    ) -> tuple[str, str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run, audio_bytes, sample_rate, language, prompt)

    def _run(self, audio_bytes: bytes, sample_rate: int, language: str | None = None,
             prompt: str | None = None) -> tuple[str, str]:
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(
            audio,
            language=language,
            initial_prompt=prompt or "",
            beam_size=1,               # greedy: ~3-4x faster on CPU, essential for real-time
            vad_filter=True,
            condition_on_previous_text=False,
            no_speech_threshold=0.8,
            repetition_penalty=1.3,
            compression_ratio_threshold=2.0,
        )
        text = _strip_repetitions(" ".join(seg.text for seg in segments).strip())
        return text, info.language


def _strip_repetitions(text: str) -> str:
    """Remove repeated phrase loops that Whisper hallucinates on noisy audio.
    Finds the first repeating block of 3+ words and truncates at it."""
    words = text.split()
    n = len(words)
    for window in range(n // 2, 2, -1):
        for start in range(n - window * 2 + 1):
            if words[start:start + window] == words[start + window:start + window * 2]:
                return " ".join(words[:start + window]).strip()
    return text
