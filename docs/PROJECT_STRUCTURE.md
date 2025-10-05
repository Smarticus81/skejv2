# PSUR-OPS Voice Agent - Project Structure

## 📁 Directory Structure

```
skej/
├── backend/               # Backend application code
│   ├── __init__.py       # Package initialization
│   ├── server.py         # FastAPI server with voice agent
│   ├── db_store.py       # SQLite database layer (SOURCE OF TRUTH)
│   ├── excel_utils.py    # Excel import/export utilities
│   └── init_data.py      # Database initialization script
│
├── public/               # Frontend static files
│   └── index.html        # Voice-enabled UI with spreadsheet view
│
├── data/                 # Data storage
│   └── psur_schedule.db  # SQLite database (SOURCE OF TRUTH)
│
├── docs/                 # Documentation
│   ├── README.md         # Project documentation
│   └── AGENTS.md         # Agent architecture details
│
├── archive/              # Deprecated/backup files
│   ├── data_store.py     # Old JSON-based store (deprecated)
│   ├── index_old.html    # Previous UI version
│   └── *.json            # Old JSON data files
│
├── .venv/                # Python virtual environment
├── .env                  # Environment variables (API keys)
├── main.py               # Application entry point
├── requirements.txt      # Python dependencies
└── 2025 Periodic Safety Update Report Master Schedule (2).xlsx  # Source Excel file
```

## 🚀 Quick Start

### Start the Server
```bash
# Activate virtual environment
.venv\Scripts\activate

# Run the application
uvicorn main:app --reload --port 8000
```

### Access the Application
- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 🗄️ Database Architecture

### SQLite Database (data/psur_schedule.db)
- **Single source of truth** for all PSUR schedule data
- Auto-imports from Excel on first run
- Indexed for fast lookups (TD number, PSUR number, writer, status, due date)
- ACID transactions ensure data integrity
- Version tracking and timestamps on every record

### Key Features
- ✅ Real-time updates via WebSocket
- ✅ Voice-controlled data management
- ✅ Spreadsheet-style card grid UI
- ✅ Automatic Excel import
- ✅ Transaction-safe updates

## 📝 API Endpoints

### Data Access
- `GET /schedule/all` - Get all records
- `GET /schedule/snapshot` - Get quick summary
- `POST /tool` - Execute voice agent tools

### Session Management
- `POST /session` - Create WebRTC session
- `WebSocket /ws` - Real-time updates

## 🎯 Voice Agent Tools

The voice agent can:
- Find reports by TD/PSUR number
- Update assignments, dates, status
- Filter by classification, writer, due date
- Search across all fields
- Get statistics and summaries

## 🔧 Configuration

Edit `.env` file:
```env
OPENAI_API_KEY=your_api_key_here
REALTIME_MODEL=gpt-4o-realtime-preview
```

## 📦 Dependencies

See `requirements.txt` for full list. Key dependencies:
- FastAPI - Web framework
- OpenAI - Realtime voice API
- SQLite3 - Database
- Pandas - Excel import
- Uvicorn - ASGI server
