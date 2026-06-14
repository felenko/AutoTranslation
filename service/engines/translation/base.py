from abc import ABC, abstractmethod


class TranslationEngine(ABC):
    @abstractmethod
    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        """Translate text to target_language. Returns original text on failure."""
        ...
