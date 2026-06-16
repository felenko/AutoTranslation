import asyncio
import sys
from .config import load_config
from .pipeline import Pipeline
from .websocket_server import SubtitleServer


async def main() -> None:
    cfg = load_config()
    server = SubtitleServer(cfg, on_config_change=_noop)

    async def on_subtitle(original: str, translation: str, audio: bytes = None) -> None:
        if not server._clients:
            print("[WS] no extension connected — subtitles won't appear in browser")
        await server.broadcast_subtitle(original, translation, audio)

    pipeline = Pipeline(cfg, on_subtitle=on_subtitle)

    async def on_config_change(new_cfg) -> None:
        pipeline.update_config(new_cfg)

    server._on_config_change = on_config_change

    print("[AutoTranslation] starting service...")
    if cfg.tts.enabled:
        try:
            import edge_tts  # noqa
            print(f"[TTS] edge-tts ready, gender={cfg.tts.voice_gender}, rate={cfg.tts.rate}")
        except ImportError as e:
            import traceback
            print(f"[TTS] WARNING: edge-tts failed to import: {e}")
            traceback.print_exc()
            print("[TTS] Voice synthesis will be skipped.")
    await asyncio.gather(
        server.serve(cfg.server.host, cfg.server.port),
        pipeline.run(),
    )


async def _noop(_cfg) -> None:
    pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[AutoTranslation] stopped.")
        sys.exit(0)
