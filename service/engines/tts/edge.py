"""
Microsoft Edge neural TTS via the edge-tts package (no API key required).
Auto-selects a voice for the target language + gender.
"""
import asyncio
import edge_tts

# Maps language name or ISO code → (female_voice, male_voice)
_VOICE_MAP: dict[str, dict[str, str]] = {
    "english":    {"female": "en-US-AriaNeural",      "male": "en-US-GuyNeural"},
    "en":         {"female": "en-US-AriaNeural",      "male": "en-US-GuyNeural"},
    "spanish":    {"female": "es-ES-ElviraNeural",    "male": "es-ES-AlvaroNeural"},
    "es":         {"female": "es-ES-ElviraNeural",    "male": "es-ES-AlvaroNeural"},
    "french":     {"female": "fr-FR-DeniseNeural",    "male": "fr-FR-HenriNeural"},
    "fr":         {"female": "fr-FR-DeniseNeural",    "male": "fr-FR-HenriNeural"},
    "german":     {"female": "de-DE-KatjaNeural",     "male": "de-DE-ConradNeural"},
    "de":         {"female": "de-DE-KatjaNeural",     "male": "de-DE-ConradNeural"},
    "italian":    {"female": "it-IT-ElsaNeural",      "male": "it-IT-DiegoNeural"},
    "it":         {"female": "it-IT-ElsaNeural",      "male": "it-IT-DiegoNeural"},
    "portuguese": {"female": "pt-BR-FranciscaNeural", "male": "pt-BR-AntonioNeural"},
    "pt":         {"female": "pt-BR-FranciscaNeural", "male": "pt-BR-AntonioNeural"},
    "russian":    {"female": "ru-RU-SvetlanaNeural",  "male": "ru-RU-DmitryNeural"},
    "ru":         {"female": "ru-RU-SvetlanaNeural",  "male": "ru-RU-DmitryNeural"},
    "japanese":   {"female": "ja-JP-NanamiNeural",    "male": "ja-JP-KeitaNeural"},
    "ja":         {"female": "ja-JP-NanamiNeural",    "male": "ja-JP-KeitaNeural"},
    "chinese":    {"female": "zh-CN-XiaoxiaoNeural",  "male": "zh-CN-YunxiNeural"},
    "zh":         {"female": "zh-CN-XiaoxiaoNeural",  "male": "zh-CN-YunxiNeural"},
    "korean":     {"female": "ko-KR-SunHiNeural",     "male": "ko-KR-InJoonNeural"},
    "ko":         {"female": "ko-KR-SunHiNeural",     "male": "ko-KR-InJoonNeural"},
    "arabic":     {"female": "ar-EG-SalmaNeural",     "male": "ar-EG-ShakirNeural"},
    "ar":         {"female": "ar-EG-SalmaNeural",     "male": "ar-EG-ShakirNeural"},
    "hindi":      {"female": "hi-IN-SwaraNeural",     "male": "hi-IN-MadhurNeural"},
    "hi":         {"female": "hi-IN-SwaraNeural",     "male": "hi-IN-MadhurNeural"},
    "dutch":      {"female": "nl-NL-ColetteNeural",   "male": "nl-NL-MaartenNeural"},
    "nl":         {"female": "nl-NL-ColetteNeural",   "male": "nl-NL-MaartenNeural"},
    "polish":     {"female": "pl-PL-ZofiaNeural",     "male": "pl-PL-MarekNeural"},
    "pl":         {"female": "pl-PL-ZofiaNeural",     "male": "pl-PL-MarekNeural"},
    "turkish":    {"female": "tr-TR-EmelNeural",      "male": "tr-TR-AhmetNeural"},
    "tr":         {"female": "tr-TR-EmelNeural",      "male": "tr-TR-AhmetNeural"},
    "ukrainian":  {"female": "uk-UA-PolinaNeural",    "male": "uk-UA-OstapNeural"},
    "uk":         {"female": "uk-UA-PolinaNeural",    "male": "uk-UA-OstapNeural"},
    "swedish":    {"female": "sv-SE-SofieNeural",     "male": "sv-SE-MattiasNeural"},
    "sv":         {"female": "sv-SE-SofieNeural",     "male": "sv-SE-MattiasNeural"},
    "norwegian":  {"female": "nb-NO-PernilleNeural",  "male": "nb-NO-FinnNeural"},
    "nb":         {"female": "nb-NO-PernilleNeural",  "male": "nb-NO-FinnNeural"},
    "danish":     {"female": "da-DK-ChristelNeural",  "male": "da-DK-JeppeNeural"},
    "da":         {"female": "da-DK-ChristelNeural",  "male": "da-DK-JeppeNeural"},
    "finnish":    {"female": "fi-FI-NooraNeural",     "male": "fi-FI-HarriNeural"},
    "fi":         {"female": "fi-FI-NooraNeural",     "male": "fi-FI-HarriNeural"},
    "czech":      {"female": "cs-CZ-VlastaNeural",    "male": "cs-CZ-AntoninNeural"},
    "cs":         {"female": "cs-CZ-VlastaNeural",    "male": "cs-CZ-AntoninNeural"},
    "hungarian":  {"female": "hu-HU-NoemiNeural",     "male": "hu-HU-TamasNeural"},
    "hu":         {"female": "hu-HU-NoemiNeural",     "male": "hu-HU-TamasNeural"},
    "romanian":   {"female": "ro-RO-AlinaNeural",     "male": "ro-RO-EmilNeural"},
    "ro":         {"female": "ro-RO-AlinaNeural",     "male": "ro-RO-EmilNeural"},
    "greek":      {"female": "el-GR-AthinaNeural",    "male": "el-GR-NestorasNeural"},
    "el":         {"female": "el-GR-AthinaNeural",    "male": "el-GR-NestorasNeural"},
    "hebrew":     {"female": "he-IL-HilaNeural",      "male": "he-IL-AvriNeural"},
    "he":         {"female": "he-IL-HilaNeural",      "male": "he-IL-AvriNeural"},
    "thai":       {"female": "th-TH-PremwadeeNeural", "male": "th-TH-NiwatNeural"},
    "th":         {"female": "th-TH-PremwadeeNeural", "male": "th-TH-NiwatNeural"},
    "vietnamese": {"female": "vi-VN-HoaiMyNeural",    "male": "vi-VN-NamMinhNeural"},
    "vi":         {"female": "vi-VN-HoaiMyNeural",    "male": "vi-VN-NamMinhNeural"},
    "indonesian": {"female": "id-ID-GadisNeural",     "male": "id-ID-ArdiNeural"},
    "id":         {"female": "id-ID-GadisNeural",     "male": "id-ID-ArdiNeural"},
    "malay":      {"female": "ms-MY-YasminNeural",    "male": "ms-MY-OsmanNeural"},
    "ms":         {"female": "ms-MY-YasminNeural",    "male": "ms-MY-OsmanNeural"},
}

_DEFAULT = {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"}


def _pick_voice(target_language: str, gender: str) -> str:
    key = target_language.lower().strip()
    voices = _VOICE_MAP.get(key, _DEFAULT)
    return voices.get(gender, voices["female"])


def _rate_str(rate: float) -> str:
    pct = int((rate - 1.0) * 100)
    return f"+{pct}%" if pct >= 0 else f"{pct}%"


async def synthesize(text: str, target_language: str, gender: str = "female", rate: float = 1.0) -> bytes:
    voice = _pick_voice(target_language, gender)
    preview = text[:60].encode("ascii", errors="replace").decode("ascii")
    print(f"[TTS] voice={voice} rate={_rate_str(rate)} text={preview!r}")
    communicate = edge_tts.Communicate(text, voice, rate=_rate_str(rate))
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data


def play_locally(audio_bytes: bytes, device_name: str = "") -> None:
    """Decode MP3 and play through a local output device (blocking — run in executor)."""
    try:
        import miniaudio
        import pyaudiowpatch as pyaudio

        decoded = miniaudio.decode(
            audio_bytes,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=22050,
        )

        pa = pyaudio.PyAudio()
        try:
            device_index = None
            if device_name:
                needle = device_name.lower()
                for i in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(i)
                    if (info.get("maxOutputChannels", 0) > 0
                            and not info.get("isLoopbackDevice")
                            and needle in info["name"].lower()):
                        device_index = i
                        break
                if device_index is None:
                    print(f"[TTS] output device not found: {device_name!r}, using default")

            stream = pa.open(
                format=pyaudio.paInt16,
                channels=decoded.nchannels,
                rate=decoded.sample_rate,
                output=True,
                output_device_index=device_index,
            )
            try:
                pcm = bytes(decoded.samples)
                chunk_size = 4096
                for offset in range(0, len(pcm), chunk_size):
                    stream.write(pcm[offset:offset + chunk_size])
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            pa.terminate()
    except Exception as exc:
        print(f"[TTS] local playback error: {exc}")
