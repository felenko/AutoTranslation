"""
MyMemory translation engine — delegates to Lingva (daily limit exceeded).
"""
import traceback as _tb
from .base import TranslationEngine
from .lingva import LingvaEngine

_lingva = LingvaEngine()


class MyMemoryEngine(TranslationEngine):
    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        print("[MyMemory] called — delegating to Lingva. Caller:")
        _tb.print_stack(limit=6)
        return await _lingva.translate(text, target_language, source_language)
