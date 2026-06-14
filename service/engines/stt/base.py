from abc import ABC, abstractmethod


class STTEngine(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, sample_rate: int) -> tuple[str, str]:
        """Transcribe PCM audio. Returns (text, detected_language_code). Empty text on silence."""
        ...
