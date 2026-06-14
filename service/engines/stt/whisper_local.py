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

    async def transcribe(self, audio_bytes: bytes, sample_rate: int) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run, audio_bytes, sample_rate)

    def _run(self, audio_bytes: bytes, sample_rate: int) -> tuple[str, str]:
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(audio, beam_size=1, vad_filter=True)
        text = " ".join(seg.text for seg in segments).strip()
        return text, info.language
