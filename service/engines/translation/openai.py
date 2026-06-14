import openai
from .base import TranslationEngine


class OpenAIEngine(TranslationEngine):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        if not text:
            return ""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a translator. Translate input to {target_language}. Output only the translation.",
                    },
                    {"role": "user", "content": text},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[OpenAI] translation error: {exc}")
            return text
