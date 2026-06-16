import io
import wave
import openai
from .base import STTEngine


class WhisperAPIEngine(STTEngine):
    def __init__(self, api_key: str, model: str = "whisper-1"):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe(
        self, audio_bytes: bytes, sample_rate: int, language: str | None = None
    ) -> tuple[str, str]:
        wav_buffer = _pcm_to_wav(audio_bytes, sample_rate)
        try:
            result = await self._client.audio.transcriptions.create(
                model=self._model,
                file=("audio.wav", wav_buffer, "audio/wav"),
                response_format="verbose_json",
                **( {"language": language} if language else {} ),
            )
            return result.text.strip(), result.language or language or "en"
        except Exception as exc:
            print(f"[WhisperAPI] transcription error: {exc}")
            return "", language or "en"


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> io.BytesIO:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    buf.seek(0)
    return buf
