"""
WebSocket server.
- Broadcasts subtitle events to all connected extension clients.
- Accepts settings-update messages from the extension.
"""
import asyncio
import base64
import json
from typing import Callable, Awaitable, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .config import Config, load_config, save_config


class SubtitleServer:
    def __init__(self, cfg: Config, on_config_change: Callable[[Config], Awaitable[None]]):
        self._cfg = cfg
        self._on_config_change = on_config_change
        self._clients: set[WebSocketServerProtocol] = set()

    async def broadcast_subtitle(self, original: str, translation: str, audio: Optional[bytes] = None) -> None:
        if not self._clients:
            return
        if "MYMEMORY WARNING" in translation.upper():
            print(f"[WS] blocked MyMemory quota message from reaching extension")
            return
        payload: dict = {"type": "subtitle", "original": original, "translation": translation}
        if audio:
            payload["audio"] = base64.b64encode(audio).decode("utf-8")
        msg = json.dumps(payload)
        await asyncio.gather(
            *[_safe_send(ws, msg) for ws in list(self._clients)],
            return_exceptions=True,
        )

    async def broadcast_status(self, status: str) -> None:
        if not self._clients:
            return
        msg = json.dumps({"type": "status", "status": status})
        await asyncio.gather(
            *[_safe_send(ws, msg) for ws in list(self._clients)],
            return_exceptions=True,
        )

    async def _handler(self, ws: WebSocketServerProtocol) -> None:
        # Evict only connections that are already closed (dead service workers).
        # Closing a live connection triggers onclose → reconnect on the other end,
        # which then boots this new connection, creating an infinite fight loop.
        if self._clients:
            stale = [c for c in self._clients if c.closed]
            live = [c for c in self._clients if not c.closed]
            self._clients = set(live)
            await asyncio.gather(
                *[old.close(1001, "replaced by new connection") for old in stale],
                return_exceptions=True,
            )
        self._clients.add(ws)
        try:
            await ws.send(json.dumps({"type": "config", "config": _config_to_dict(self._cfg)}))
            async for raw in ws:
                await self._handle_message(raw)
        except websockets.exceptions.ConnectionClosedOK:
            pass
        except Exception as exc:
            print(f"[WS] client error: {exc}")
        finally:
            self._clients.discard(ws)

    async def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        if msg.get("type") == "ping":
            return

        if msg.get("type") == "update_config":
            cfg = load_config()
            patch = msg.get("config", {})
            print(f"[WS] update_config received: {patch}")
            _apply_patch(cfg, patch)
            print(f"[WS] after patch: engine={cfg.translation.engine} lang={cfg.translation.target_language}")
            save_config(cfg)
            self._cfg = cfg
            await self._on_config_change(cfg)
            config_msg = json.dumps({"type": "config", "config": _config_to_dict(self._cfg)})
            await asyncio.gather(
                *[_safe_send(ws, config_msg) for ws in list(self._clients)],
                return_exceptions=True,
            )

    async def serve(self, host: str, port: int) -> None:
        print(f"[WS] listening on ws://{host}:{port}")
        async with websockets.serve(self._handler, host, port):
            await asyncio.Future()  # run forever


async def _safe_send(ws: WebSocketServerProtocol, msg: str) -> None:
    try:
        await ws.send(msg)
    except Exception:
        pass


def _config_to_dict(cfg: Config) -> dict:
    from .audio_capture import list_loopback_device_names, list_output_device_names
    return {
        "stt_engine": cfg.stt.engine,
        "translation_enabled": cfg.translation.enabled,
        "translation_engine": cfg.translation.engine,
        "source_language": cfg.translation.source_language,
        "target_language": cfg.translation.target_language,
        "ollama_host": cfg.translation.ollama.host,
        "ollama_model": cfg.translation.ollama.model,
        "openai_model": cfg.translation.openai.model,
        "claude_model": cfg.translation.claude.model,
        "cursor_model": cfg.translation.cursor.model,
        "chunk_duration": cfg.audio.chunk_duration_seconds,
        "capture_device": cfg.audio.capture_device,
        "original_volume": cfg.audio.original_volume,
        "tts_enabled": cfg.tts.enabled,
        "tts_voice_gender": cfg.tts.voice_gender,
        "tts_rate": cfg.tts.rate,
        "tts_playback_device": cfg.tts.playback_device,
        "tts_volume": cfg.tts.tts_volume,
        "loopback_devices": list_loopback_device_names(),
        "output_devices": list_output_device_names(),
    }


def _apply_patch(cfg: Config, patch: dict) -> None:
    if "stt_engine" in patch:
        cfg.stt.engine = patch["stt_engine"]
    if "translation_enabled" in patch:
        cfg.translation.enabled = bool(patch["translation_enabled"])
    if "translation_engine" in patch:
        engine = patch["translation_engine"]
        if engine in ("mymemory", "lingva", "claude", "openai", "ollama", "cursor"):
            cfg.translation.engine = engine
    if "source_language" in patch:
        cfg.translation.source_language = patch["source_language"]
    if "target_language" in patch:
        cfg.translation.target_language = patch["target_language"]
    if "ollama_host" in patch:
        cfg.translation.ollama.host = patch["ollama_host"]
    if "ollama_model" in patch:
        cfg.translation.ollama.model = patch["ollama_model"]
    if "openai_model" in patch:
        cfg.translation.openai.model = patch["openai_model"]
    if "claude_model" in patch:
        cfg.translation.claude.model = patch["claude_model"]
    if "cursor_model" in patch:
        cfg.translation.cursor.model = patch["cursor_model"]
    if "chunk_duration" in patch:
        cfg.audio.chunk_duration_seconds = float(patch["chunk_duration"])
    if "capture_device" in patch:
        cfg.audio.capture_device = patch["capture_device"]
    if "original_volume" in patch:
        cfg.audio.original_volume = float(patch["original_volume"])
    if "tts_enabled" in patch:
        cfg.tts.enabled = bool(patch["tts_enabled"])
    if "tts_voice_gender" in patch:
        cfg.tts.voice_gender = patch["tts_voice_gender"]
    if "tts_rate" in patch:
        cfg.tts.rate = float(patch["tts_rate"])
    if "tts_playback_device" in patch:
        cfg.tts.playback_device = patch["tts_playback_device"]
    if "tts_volume" in patch:
        cfg.tts.tts_volume = float(patch["tts_volume"])
