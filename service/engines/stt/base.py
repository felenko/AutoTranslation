from abc import ABC, abstractmethod


class STTEngine(ABC):
    @abstractmethod
    async def transcribe(
        self, audio_bytes: bytes, sample_rate: int, language: str | None = None
    ) -> tuple[str, str]:
        """Transcribe PCM audio. Returns (text, language_code).
        language: ISO 639-1 code to force (e.g. 'ru'); None = auto-detect."""
        ...
