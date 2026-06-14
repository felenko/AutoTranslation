"""
Cursor AI translation engine — PENDING.

Investigation status (2026-06-14):
  - Cursor's JWT access token is auto-discoverable from state.vscdb.
  - api2.cursor.sh accepts requests at /aiserver.v1.AiService/StreamChat,
    but the endpoint returns grpc-status 12 UNIMPLEMENTED:
    "Request type deprecated. Please upgrade to the latest version of Cursor."
  - The replacement endpoint (/StreamUnifiedChat etc.) returns 404 —
    it is served by a different backend not yet identified.
  - Until the correct endpoint/proto is found, this engine falls back to
    MyMemory so the pipeline still works.
"""
import json
import os
import sqlite3

from .base import TranslationEngine
from .mymemory import MyMemoryEngine

_CURSOR_DB = os.path.expandvars(r"%APPDATA%\Cursor\User\globalStorage\state.vscdb")


def discover_cursor_token() -> str:
    if not os.path.exists(_CURSOR_DB):
        return ""
    try:
        conn = sqlite3.connect(f"file:{_CURSOR_DB}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = 'cursorAuth/accessToken'"
        ).fetchone()
        conn.close()
        if row:
            val = row[0]
            try:
                return json.loads(val).get("accessToken", val)
            except (json.JSONDecodeError, AttributeError):
                return val
    except Exception as exc:
        print(f"[Cursor] token discovery failed: {exc}")
    return ""


class CursorEngine(TranslationEngine):
    """
    Intended to use Cursor's built-in AI subscription.
    Currently falls back to MyMemory (free, no-key) while the
    new Cursor gRPC endpoint is being investigated.
    """

    def __init__(self, model: str = "claude-3-5-sonnet", token: str = ""):
        self._token = token or discover_cursor_token()
        self._fallback = MyMemoryEngine()
        if self._token:
            print(
                "[Cursor] token discovered — gRPC endpoint investigation pending, "
                "using MyMemory as fallback."
            )
        else:
            print("[Cursor] no token found — using MyMemory fallback.")

    async def translate(self, text: str, target_language: str, source_language: str = "en") -> str:
        return await self._fallback.translate(text, target_language, source_language)
