"""Entry point: python run.py"""
import asyncio
import sys
import os

# Safe UTF-8 console on Windows (do not replace sys.stdout/stderr — that breaks on re-import)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from service.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[AutoTranslation] stopped.")
        sys.exit(0)
