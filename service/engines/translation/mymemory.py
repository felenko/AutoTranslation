"""
MyMemory translation engine.
Free, no API key required, no installation needed.
Limit: ~500 requests/day, 500 words/request on the free tier.
"""
import aiohttp
from .base import TranslationEngine

# Map common language names to BCP-47 codes MyMemory understands
_LANG_CODES = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "chinese": "zh",
    "japanese": "ja", "korean": "ko", "arabic": "ar", "hindi": "hi",
    "dutch": "nl", "polish": "pl", "turkish": "tr", "ukrainian": "uk",
    "swedish": "sv", "norwegian": "no", "danish": "da", "finnish": "fi",
    "czech": "cs", "romanian": "ro", "hungarian": "hu", "greek": "el",
    "hebrew": "he", "thai": "th", "vietnamese": "vi", "indonesian": "id",
}

_API_URL = "https://api.mymemory.translated.net/get"


def _to_code(language: str) -> str:
    return _LANG_CODES.get(language.lower().strip(), language.lower().strip()[:2])


class MyMemoryEngine(TranslationEngine):
    """
    Free translation via MyMemory API.
    No API key or account required.
    """

    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        if not text:
            return ""
        target_code = _to_code(target_language)
        source_code = source_language if source_language != target_code else "en"
        params = {
            "q": text[:500],
            "langpair": f"{source_code}|{target_code}",
        }
        print(f"[MyMemory] requesting: {source_code}|{target_code} | text={text[:60]!r}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    print(f"[MyMemory] raw response: status={resp.status} responseStatus={data.get('responseStatus')} "
                          f"translatedText={str(data.get('responseData', {}).get('translatedText', ''))[:80]!r}")
                    translated = data.get("responseData", {}).get("translatedText", "")
                    if not translated or translated == text:
                        print(f"[MyMemory] WARNING: no usable translation returned")
                        return text
                    return translated.strip()
        except Exception as exc:
            import traceback
            print(f"[MyMemory] ERROR: {exc}")
            traceback.print_exc()
            return text
