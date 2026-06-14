import aiohttp
from .base import TranslationEngine


class OllamaEngine(TranslationEngine):
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3"):
        self._host = host.rstrip("/")
        self._model = model

    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        if not text:
            return ""
        prompt = (
            f"Translate the following to {target_language}. "
            "Output only the translation, no explanations.\n\n"
            f"{text}"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._host}/api/generate",
                    json={"model": self._model, "prompt": prompt, "stream": False},
                ) as resp:
                    data = await resp.json()
                    return data.get("response", text).strip()
        except Exception as exc:
            print(f"[Ollama] translation error: {exc}")
            return text
