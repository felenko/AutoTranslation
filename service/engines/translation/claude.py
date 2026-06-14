import anthropic
from .base import TranslationEngine


class ClaudeEngine(TranslationEngine):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        if not text:
            return ""
        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Translate the following to {target_language}. "
                            "Output only the translation, no explanations.\n\n"
                            f"{text}"
                        ),
                    }
                ],
            )
            return message.content[0].text.strip()
        except Exception as exc:
            print(f"[Claude] translation error: {exc}")
            return text
