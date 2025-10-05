# 🎤 Skej - AI Voice Assistant

A modern voice assistant powered by OpenAI's Realtime API and WebRTC.

## Project Structure

```
skej/
├── server.py                          # FastAPI web server
├── realtime_webrtc_chained_agent.py  # WebRTC voice agent
├── .env                               # Environment configuration
├── requirements.txt                   # Python dependencies
├── public/
│   └── index.html                    # Web interface
└── app/
    ├── main.py                       # Application logic
    └── data/
        └── schedule.db               # SQLite database
```

## Setup

### 1. Install Dependencies

```powershell
# Activate virtual environment (if not already active)
.\.venv\Scripts\Activate.ps1

# Install all dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Edit `.env` file with your API keys (already configured):
- `OPENAI_API_KEY` - Your OpenAI API key
- `GROQ_API_KEY` - Your Groq API key (optional)

### 3. Run the Server

**Option A: Web Server (with UI)**
```powershell
python server.py
```
Then open: http://localhost:8000

**Option B: Voice Agent (standalone)**
```powershell
python realtime_webrtc_chained_agent.py
```

## Features

### Web Interface (`server.py`)
- ✅ FastAPI REST API
- ✅ Static file serving
- ✅ Health check endpoint
- ✅ WebSocket support
- ✅ Configuration API
- 🎨 Beautiful responsive UI

### Voice Agent (`realtime_webrtc_chained_agent.py`)
- 🎤 Real-time voice input via microphone
- 🔊 Audio output via speakers
- 🧠 OpenAI GPT-4 Realtime API
- 🔄 WebRTC peer connection
- 📝 Server-side VAD (Voice Activity Detection)
- 🛠️ Function calling support (optional)
- 💬 Multi-turn conversations

## API Endpoints

### `GET /`
Serves the main web interface

### `GET /health`
Returns server health status
```json
{
  "status": "healthy",
  "service": "Skej Voice Assistant",
  "openai_configured": true
}
```

### `GET /api/config`
Returns configuration information
```json
{
  "model": "gpt-4o-realtime-preview",
  "api_base": "https://api.openai.com",
  "has_api_key": true
}
```

### `WebSocket /ws`
WebSocket endpoint for real-time communication

## Usage

### Starting a Conversation

1. Start the server:
   ```powershell
   python server.py
   ```

2. Open http://localhost:8000 in your browser

3. Click "Connect to Voice Agent"

4. Start speaking! The assistant will:
   - Listen to your voice
   - Transcribe your speech
   - Generate an intelligent response
   - Speak back to you

### Using the Standalone Agent

For direct voice interaction without the web interface:

```powershell
python realtime_webrtc_chained_agent.py
```

Press Ctrl+C to stop.

## Architecture

### Voice Pipeline Flow

```
User Mic → WebRTC → OpenAI Realtime API → Response Generation → TTS → Speaker
                            ↓
                    Server VAD detects speech
                            ↓
                    Transcript generated
                            ↓
                    LLM processes & responds
```

### Components

**Server (`server.py`)**
- FastAPI application
- Serves web UI
- Provides REST API
- Manages WebSocket connections

**Voice Agent (`realtime_webrtc_chained_agent.py`)**
- WebRTC peer connection
- Audio I/O management
- OpenAI Realtime API integration
- Conversation state management

**Frontend (`public/index.html`)**
- Responsive web interface
- Connection status display
- Conversation transcript
- Error handling

## Configuration

### Environment Variables

```env
# API Keys
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# OpenAI Realtime
REALTIME_MODEL=gpt-4o-realtime-preview
OPENAI_API_BASE=https://api.openai.com

# Server
HOST=0.0.0.0
PORT=8000

# Database
DATABASE_URL=sqlite:///./app/data/schedule.db

# Debugging
ENV=development
DEBUG=true
LOG_LEVEL=info
```

### Customizing the Assistant

Edit `realtime_webrtc_chained_agent.py`:

```python
INSTRUCTIONS = (
    "You are a helpful, low-latency voice assistant. "
    "Use short answers unless asked for detail. "
    "Maintain conversational context in this session."
)
```

## Troubleshooting

### "No OPENAI_API_KEY found"
- Check your `.env` file
- Ensure `.env` is in the same directory as your scripts
- Restart the terminal after editing `.env`

### Audio Issues
- Check your microphone/speaker permissions
- Try listing available audio devices:
  ```python
  import sounddevice as sd
  print(sd.query_devices())
  ```

### Port Already in Use
Change the port in `.env`:
```env
PORT=8001
```

## Development

### Running Tests
```powershell
python test.py
```

### Code Style
```powershell
black *.py
flake8 *.py
```

## Advanced Features

### Adding Custom Tools

Edit the `_configure_session()` method in `realtime_webrtc_chained_agent.py`:

```python
"tools": [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"}
            }
        }
    }
]
```

Then implement in `_handle_tool_call()`.

### Multi-Agent Workflows

See `AGENTS.md` for detailed guide on:
- Creating custom agents
- Agent handoff patterns
- State management
- Tool development

## Resources

- [OpenAI Realtime API Docs](https://platform.openai.com/docs/guides/realtime)
- [WebRTC Documentation](https://platform.openai.com/docs/guides/realtime-webrtc)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [aiortc Documentation](https://aiortc.readthedocs.io/)

## License

MIT License - See LICENSE file for details

---

Built with ❤️ using OpenAI Realtime API, FastAPI, and WebRTC
