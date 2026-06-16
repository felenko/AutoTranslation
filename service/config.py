import json
import os
from dataclasses import dataclass, field
from typing import Literal

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 8765


@dataclass
class AudioConfig:
    chunk_duration_seconds: float = 4.0
    sample_rate: int = 16000
    capture_device: str = ""  # partial name match, e.g. "CABLE" for VB-Audio Virtual Cable
    original_volume: float = 1.0  # passthrough volume (0.0–1.0)


@dataclass
class WhisperAPIConfig:
    api_key: str = ""
    model: str = "whisper-1"


@dataclass
class LocalWhisperConfig:
    model_size: str = "base"


@dataclass
class STTConfig:
    engine: Literal["whisper_api", "whisper_local"] = "whisper_api"
    whisper_api: WhisperAPIConfig = field(default_factory=WhisperAPIConfig)
    whisper_local: LocalWhisperConfig = field(default_factory=LocalWhisperConfig)


@dataclass
class ClaudeConfig:
    api_key: str = ""
    model: str = "claude-sonnet-4-6"


@dataclass
class OpenAITranslationConfig:
    api_key: str = ""
    model: str = "gpt-4o"


@dataclass
class OllamaConfig:
    host: str = "http://localhost:11434"
    model: str = "llama3"


@dataclass
class CursorConfig:
    model: str = "claude-3-5-sonnet"
    # Leave token empty to auto-discover from local Cursor installation
    token: str = ""


@dataclass
class TranslationConfig:
    engine: Literal["mymemory", "claude", "openai", "ollama", "cursor"] = "mymemory"
    source_language: str = ""
    target_language: str = "English"
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    openai: OpenAITranslationConfig = field(default_factory=OpenAITranslationConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)


@dataclass
class TTSConfig:
    enabled: bool = False
    voice_gender: str = "female"
    rate: float = 1.0
    playback_device: str = ""  # partial name match; empty = play in browser via extension
    tts_volume: float = 1.0


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)


def load_config(path: str = CONFIG_PATH) -> Config:
    if not os.path.exists(path):
        cfg = Config()
        save_config(cfg, path)
        return cfg

    with open(path, "r") as f:
        raw = json.load(f)

    cfg = Config()
    s = raw.get("server", {})
    cfg.server = ServerConfig(
        host=s.get("host", cfg.server.host),
        port=s.get("port", cfg.server.port),
    )
    a = raw.get("audio", {})
    cfg.audio = AudioConfig(
        chunk_duration_seconds=a.get("chunk_duration_seconds", cfg.audio.chunk_duration_seconds),
        sample_rate=a.get("sample_rate", cfg.audio.sample_rate),
        capture_device=a.get("capture_device", cfg.audio.capture_device),
        original_volume=float(a.get("original_volume", cfg.audio.original_volume)),
    )
    stt = raw.get("stt", {})
    wa = stt.get("whisper_api", {})
    wl = stt.get("whisper_local", {})
    cfg.stt = STTConfig(
        engine=stt.get("engine", cfg.stt.engine),
        whisper_api=WhisperAPIConfig(
            api_key=wa.get("api_key", ""),
            model=wa.get("model", "whisper-1"),
        ),
        whisper_local=LocalWhisperConfig(
            model_size=wl.get("model_size", "base"),
        ),
    )
    tr = raw.get("translation", {})
    cl = tr.get("claude", {})
    oa = tr.get("openai", {})
    ol = tr.get("ollama", {})
    cu = tr.get("cursor", {})
    cfg.translation = TranslationConfig(
        engine=tr.get("engine", cfg.translation.engine),
        source_language=tr.get("source_language", cfg.translation.source_language),
        target_language=tr.get("target_language", cfg.translation.target_language),
        claude=ClaudeConfig(api_key=cl.get("api_key", ""), model=cl.get("model", "claude-sonnet-4-6")),
        openai=OpenAITranslationConfig(api_key=oa.get("api_key", ""), model=oa.get("model", "gpt-4o")),
        ollama=OllamaConfig(host=ol.get("host", "http://localhost:11434"), model=ol.get("model", "llama3")),
        cursor=CursorConfig(model=cu.get("model", "claude-3-5-sonnet"), token=cu.get("token", "")),
    )
    tts = raw.get("tts", {})
    cfg.tts = TTSConfig(
        enabled=tts.get("enabled", False),
        voice_gender=tts.get("voice_gender", "female"),
        rate=float(tts.get("rate", 1.0)),
        playback_device=tts.get("playback_device", ""),
        tts_volume=float(tts.get("tts_volume", 1.0)),
    )
    return cfg


def save_config(cfg: Config, path: str = CONFIG_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "server": {"host": cfg.server.host, "port": cfg.server.port},
        "audio": {
            "chunk_duration_seconds": cfg.audio.chunk_duration_seconds,
            "sample_rate": cfg.audio.sample_rate,
            "capture_device": cfg.audio.capture_device,
            "original_volume": cfg.audio.original_volume,
        },
        "stt": {
            "engine": cfg.stt.engine,
            "whisper_api": {
                "api_key": cfg.stt.whisper_api.api_key,
                "model": cfg.stt.whisper_api.model,
            },
            "whisper_local": {
                "model_size": cfg.stt.whisper_local.model_size,
            },
        },
        "translation": {
            "engine": cfg.translation.engine,
            "source_language": cfg.translation.source_language,
            "target_language": cfg.translation.target_language,
            "claude": {
                "api_key": cfg.translation.claude.api_key,
                "model": cfg.translation.claude.model,
            },
            "openai": {
                "api_key": cfg.translation.openai.api_key,
                "model": cfg.translation.openai.model,
            },
            "ollama": {
                "host": cfg.translation.ollama.host,
                "model": cfg.translation.ollama.model,
            },
            "cursor": {
                "model": cfg.translation.cursor.model,
                "token": cfg.translation.cursor.token,
            },
        },
        "tts": {
            "enabled": cfg.tts.enabled,
            "voice_gender": cfg.tts.voice_gender,
            "rate": cfg.tts.rate,
            "playback_device": cfg.tts.playback_device,
            "tts_volume": cfg.tts.tts_volume,
        },
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
