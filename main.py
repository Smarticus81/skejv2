"""
PSUR-OPS Voice Agent - Main Entry Point
Run with: uvicorn main:app --reload --port 8000
"""
from backend.server import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
