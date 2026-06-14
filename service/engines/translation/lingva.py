"""
Translation engine: tries Lingva instances first, falls back to Google Translate
unofficial endpoint (client=gtx, no API key required).
"""
import json
import urllib.parse
import aiohttp
from .base import TranslationEngine

_LINGVA_INSTANCES = [
    "https://lingva.ml",
    "https://translate.plausibility.cloud",
    "https://lingva.thedaviddelta.com",
    "https://lingva.pussthecat.org",
    "https://lingva.garudalinux.org",
]

_GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"

_LANG_CODES = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "chinese": "zh",
    "japanese": "ja", "korean": "ko", "arabic": "ar", "hindi": "hi",
    "dutch": "nl", "polish": "pl", "turkish": "tr", "ukrainian": "uk",
    "swedish": "sv", "norwegian": "no", "danish": "da", "finnish": "fi",
    "czech": "cs", "romanian": "ro", "hungarian": "hu", "greek": "el",
    "hebrew": "he", "thai": "th", "vietnamese": "vi", "indonesian": "id",
}


def _to_code(language: str) -> str:
    code = language.lower().strip()
    return _LANG_CODES.get(code, code[:2] if len(code) > 2 else code)


class LingvaEngine(TranslationEngine):
    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        if not text:
            return ""
        src = _to_code(source_language) if source_language else "auto"
        tgt = _to_code(target_language)
        print(f"[Translate] {src} -> {tgt}: {text[:60]!r}")

        async with aiohttp.ClientSession() as session:
            # Google Translate unofficial endpoint — primary backend
            try:
                params = {
                    "client": "gtx",
                    "sl": src,
                    "tl": tgt,
                    "dt": "t",
                    "q": text[:500],
                }
                async with session.get(_GOOGLE_URL, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        parts = [seg[0] for seg in data[0] if seg[0]]
                        translated = "".join(parts).strip()
                        if translated and translated != text:
                            print(f"[Translate] Google ok: {translated[:80]!r}")
                            return translated
            except Exception as exc:
                print(f"[Translate] Google error: {exc}")

            # Lingva instances — fallback
            encoded = urllib.parse.quote(text[:500], safe="")
            for base in _LINGVA_INSTANCES:
                try:
                    url = f"{base}/api/v1/{src}/{tgt}/{encoded}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        translated = data.get("translation", "")
                        if translated and translated != text:
                            print(f"[Translate] Lingva ok: {translated[:80]!r}")
                            return translated.strip()
                except Exception:
                    continue

        print("[Translate] all backends failed, returning original")
        return text
