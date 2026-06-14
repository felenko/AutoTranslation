# AutoTranslation

Real-time AI subtitles for streaming and any audio playing on your Windows PC. Captures system audio, transcribes speech, translates it, and overlays subtitles in your browser.

![AutoTranslation subtitles overlay](docs/ai-speech-transcript.png)

## How it works

```
System audio (WASAPI loopback)
        ↓
   Speech-to-text (Whisper)
        ↓
   Translation engine
        ↓
   WebSocket → Chrome extension overlay
```

## Requirements

- **Windows** (uses WASAPI loopback audio capture)
- **Python 3.10+**
- **Chrome** or **Edge** (Chromium)

## Quick start

### 1. Install the Python service

```powershell
cd AutoTranslation
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# For local Whisper (no OpenAI key needed):
.\.venv\Scripts\pip install "faster-whisper>=1.0.0" numpy

# Create your config from the example:
copy config.json.example config.json
```

### 2. Run the service

```powershell
.\.venv\Scripts\python.exe run.py
```

You should see:

```
[WhisperLocal] model 'base' ready
[WS] listening on ws://127.0.0.1:8765
[AudioCapture] capturing from '...' at 48000Hz, 2ch
```

**Important:** Audio must play through your **default Windows output device** — the service captures loopback from that device, not the microphone.

### 3. Load the browser extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension` folder in this repo
5. Open a video page, click the extension icon, and click **Apply settings**

The status dot should turn green when connected to the service.

## Configuration

Edit `config.json` (copy from `config.json.example`) or use the extension popup.

### Speech-to-text (STT)

| Engine | Description |
|--------|-------------|
| `whisper_local` | Runs locally via [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Free, offline after first model download (~150 MB for `base`). |
| `whisper_api` | OpenAI Whisper API. Requires an API key. |

### Translation

| Engine | Description |
|--------|-------------|
| `mymemory` | Free, no API key. Good default. ~500 requests/day. |
| `claude` | Anthropic API. Requires API key in `config.json`. |
| `openai` | OpenAI GPT. Requires API key. |
| `ollama` | Local [Ollama](https://ollama.com/) instance. |
| `cursor` | Uses Cursor install auth (experimental). |

Set `target_language` to any language name (e.g. `Russian`, `Spanish`, `Japanese`).

## Project structure

```
AutoTranslation/
├── run.py                 # Entry point
├── config.json.example    # Config template
├── requirements.txt
├── service/
│   ├── main.py            # Async service orchestration
│   ├── pipeline.py        # STT → translation pipeline
│   ├── audio_capture.py   # Windows WASAPI loopback
│   ├── websocket_server.py
│   └── engines/
│       ├── stt/           # Whisper API & local
│       └── translation/   # MyMemory, Claude, OpenAI, Ollama, Cursor
└── extension/             # Chrome MV3 extension
    ├── manifest.json
    ├── background.js      # WebSocket client
    ├── content.js         # Subtitle overlay
    └── popup.html/js      # Settings UI
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port already in use (`10048`) | Kill stale processes: `Get-Process python* \| Stop-Process -Force` |
| No subtitles | Ensure audio plays on your default output device; check green status dot in popup |
| No speech detected | Set the correct device as Windows default output; play audio through it |
| Settings not saving | Service must be running; popup shows "Not connected!" if WebSocket is down |
| Cyrillic / Unicode crash | Fixed in `run.py` via UTF-8 console reconfigure |

## License

MIT
