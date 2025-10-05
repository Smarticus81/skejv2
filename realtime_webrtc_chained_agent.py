"""
realtime_webrtc_chained_agent.py

Chained-architecture, multi-turn voice agent over WebRTC:

Mic → Realtime VAD/transcripts → response.create (LLM) → output audio (TTS) → Speaker

Fixes vs prior version:
- Do NOT await pc.addTrack() or sender.setParameters() (aiortc API is sync for these)
- Consume remote audio with: while True: frame = await track.recv()
- Optional .env loading with python-dotenv for Windows/PowerShell convenience

Docs:
- Realtime WebRTC offer/answer & session config: https://platform.openai.com/docs/guides/realtime-webrtc
- Realtime conversations & events (response.create, tool calls): https://platform.openai.com/docs/guides/realtime-conversations
- VAD (server_vad) & transcripts: https://platform.openai.com/docs/guides/realtime-vad
- Chained voice-agent pattern: https://platform.openai.com/docs/guides/voice-agents?voice-agent-architecture=chained
- aiortc API (addTrack returns RTCRtpSender; use track.recv() to read frames): https://aiortc.readthedocs.io/en/latest/api.html
"""

import os
import sys
import json
import signal
import asyncio
import numpy as np

# Optional: load .env in the current folder (helps on Windows/PowerShell)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import sounddevice as sd
import av
from aiohttp import ClientSession
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaBlackhole

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("REALTIME_MODEL", "gpt-4o-realtime-preview")  # override via env to your latest realtime model
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com")
REALTIME_ENDPOINT = f"{API_BASE}/v1/realtime?model={MODEL}"

INSTRUCTIONS = (
    "You are 'PSUR-OPS', a regulatory compliance voice agent for PSUR/PMSR schedules.\n\n"
    
    "## DATA STRUCTURE CONTEXT ##\n"
    "The schedule tracks Post-Market Safety Update Reports (PSURs) and contains these fields:\n"
    "- TD Number: Unique identifier (e.g., TD001, TD002)\n"
    "- PSURNumber: Report identifier (e.g., PSUR-2025-001)\n"
    "- Class: Medical device classification (I, IIa, IIb, III) - determines frequency\n"
    "- Type: Report type (PSUR, PMSR, etc.)\n"
    "- Product Name: Device name (searchable)\n"
    "- Catalog Number: SKU/catalog number\n"
    "- Writer: Assigned technical writer\n"
    "- Email: Writer's contact\n"
    "- Start Period/End Period: Reporting period dates\n"
    "- Frequency: Report cadence (yearly, bi-yearly based on class)\n"
    "- Due Date: Submission deadline (critical for compliance)\n"
    "- Status: Current state (Released, Assigned, In Progress, Completed, etc.)\n"
    "- Canada Needed/Status: Canada-specific requirements\n"
    "- Comments: Additional notes\n\n"
    
    "## REGULATORY COMPLIANCE RULES ##\n"
    "1. Class IIb & III devices: Annual PSUR reporting required\n"
    "2. Class IIa devices: Bi-annual (every 2 years) reporting\n"
    "3. Class I devices: Typically exempt unless specified\n"
    "4. Overdue reports (past due_date) are CRITICAL compliance violations\n"
    "5. Canada reports may have separate requirements\n\n"
    
    "## TOOL USAGE ##\n"
    "- list_due_items: Filter by writer, class, status, within_days\n"
    "- find_reports: Search TD numbers, PSUR IDs, products (use for 'find TD045' or 'what's PSUR030')\n"
    "- get_report: Get full details for specific TD number (use after find_reports)\n"
    "- update_schedule_row: Update status, dates, writers, comments\n"
    "- add_psur_item: Create new entries\n\n"
    
    "## RESPONSE STYLE ##\n"
    "- Be concise and direct (voice interface)\n"
    "- Mention TD numbers when discussing reports\n"
    "- Flag overdue items as 'CRITICAL' or 'URGENT'\n"
    "- Suggest actions ('Should I update the status?' or 'Shall I assign this to X?')\n"
    "- For blank data, say 'Awaiting Data' and ask what to fill in\n"
    "- Use compliance language ('due for submission', 'regulatory deadline', 'compliance window')\n"
)

# Toggle: we trigger the chain when transcripts arrive
CHAINED_USE_TRANSCRIPTS = True
ENABLE_TOOLS = False  # set True and declare tools in _configure_session()

# ----------------- Audio sinks/sources -----------------
class SpeakerSink:
    """Plays 48kHz mono float32 frames via PortAudio/sounddevice."""
    def __init__(self, sample_rate=48000, channels=1, device=None):
        self.stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            blocksize=1024,
            device=device,
        )
        self.stream.start()

    def write(self, frame: av.AudioFrame):
        pcm = frame.to_ndarray(format="flt")  # (channels, samples)
        pcm = np.transpose(pcm)               # (samples, channels)
        self.stream.write(pcm)

    def close(self):
        try:
            self.stream.stop()
        finally:
            self.stream.close()

class MicrophoneTrack(MediaStreamTrack):
    """Live mic track (48kHz mono float32) packaged as av.AudioFrame."""
    kind = "audio"
    def __init__(self, sample_rate=48000, channels=1, device=None):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = 1024
        self.stream = sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            blocksize=self.blocksize,
            device=device,
        )
        self.stream.start()

    async def recv(self):
        data, _ = self.stream.read(self.blocksize)  # (blocksize, channels)
        data = np.transpose(data)  # to (channels, samples)
        frame = av.AudioFrame.from_ndarray(
            data, format="flt",
            layout="mono" if self.channels == 1 else "stereo"
        )
        frame.sample_rate = self.sample_rate
        return frame

    def stop(self):
        try:
            self.stream.stop()
        finally:
            self.stream.close()

# ----------------- Core agent -----------------
class RealtimeChainedAgent:
    def __init__(self, mic_device=None, spk_device=None):
        if not OPENAI_API_KEY:
            print("ERROR: Set OPENAI_API_KEY in your environment or .env", file=sys.stderr)
            sys.exit(1)

        self.pc = RTCPeerConnection()
        self.mic = MicrophoneTrack(device=mic_device)
        self.speaker = SpeakerSink(device=spk_device)
        self.blackhole = MediaBlackhole()
        self.control_channel = None
        self.turn_index = 0

        self.pc.on("iceconnectionstatechange", self.on_ice_state_change)
        self.pc.on("track", self.on_track)
        self.pc.on("datachannel", self.on_datachannel)

    # ---------- WebRTC ----------
    async def connect(self):
        # Publish mic (NOTE: addTrack is sync — returns RTCRtpSender)
        self.pc.addTrack(self.mic)

        # Optionally tweak sender params (sync in aiortc)
        for sender in self.pc.getSenders():
            if sender and sender.kind == "audio":
                params = sender.getParameters()
                sender.setParameters(params)

        # Create a data channel for control/events
        self.control_channel = self.pc.createDataChannel("oai-events")
        self.control_channel.on("open", self.on_control_open)
        self.control_channel.on("message", self.on_control_message)

        # Create local offer
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        # Exchange SDP with OpenAI Realtime (per docs)
        async with ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1",
                "Content-Type": "application/sdp",
            }
            async with session.post(REALTIME_ENDPOINT, data=offer.sdp, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Realtime offer failed: {resp.status} - {text}")
                answer_sdp = await resp.text()

        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=answer_sdp, type="answer"))

        # Configure session (instructions, VAD, audio, tools)
        await self._configure_session()

        print("✅ WebRTC connected to OpenAI Realtime.")

    async def _configure_session(self):
        if not self.control_channel:
            return
        session_update = {
            "type": "session.update",
            "session": {
                "instructions": INSTRUCTIONS,
                # Let the server detect speech boundaries and emit transcripts
                "turn_detection": {"type": "server_vad"},
                # Ask for audio output when we call response.create
                "output_audio_format": {"type": "pcm16", "sample_rate_hz": 24000},
                "voice": "verse",
                # Optional: expose tools here and implement in _handle_tool_call()
                "tools": [
                    # {
                    #   "type": "function",
                    #   "name": "get_time",
                    #   "description": "Get current local time",
                    #   "parameters": {"type": "object", "properties": {}}
                    # }
                ],
                "tool_choice": "auto",
            }
        }
        self.control_channel.send(json.dumps(session_update))

    def on_ice_state_change(self):
        print("ICE state:", self.pc.iceConnectionState)

    def on_track(self, track):
        print(f"🔊 Remote track received: {track.kind}")
        if track.kind == "audio":
            asyncio.create_task(self._play_remote_audio(track))
        else:
            self.blackhole.addTrack(track)

    async def _play_remote_audio(self, track):
        """Continuously read remote frames and play via speaker."""
        try:
            while True:
                frame = await track.recv()
                self.speaker.write(frame)
        except Exception as e:
            print(f"[remote audio ended] {e}")

    def on_datachannel(self, channel):
        print(f"📡 Server opened data channel: {channel.label}")
        if channel.label == "oai-events":
            channel.on("message", self.on_control_message)
            self.control_channel = channel

    # ---------- Control / events ----------
    def on_control_open(self):
        print("📨 Control channel ready.")

    def on_control_message(self, message):
        try:
            evt = json.loads(message)
        except Exception:
            return

        t = evt.get("type")
        if not t:
            return

        # Debug: uncomment to inspect events
        # print("EVENT:", json.dumps(evt, indent=2)[:800])

        # Chained flow: when we get a transcript, create a response with audio
        if CHAINED_USE_TRANSCRIPTS and t in ("transcript.completed", "input_audio_buffer.committed"):
            user_text = None
            if t == "transcript.completed":
                user_text = (evt.get("transcript") or {}).get("text")
            else:
                user_text = evt.get("text")
            if user_text:
                asyncio.create_task(self._chain_to_llm(user_text))

        # Tools (server-side controls)
        if ENABLE_TOOLS and t == "tool.call":
            asyncio.create_task(self._handle_tool_call(evt))

        if t == "response.completed":
            rid = (evt.get("response") or {}).get("id")
            if rid:
                print(f"🤖 Response {rid} completed.")

    async def _chain_to_llm(self, user_text: str):
        if not self.control_channel or not user_text.strip():
            return
        self.turn_index += 1
        print(f"\n🎤 User said (turn {self.turn_index}): {user_text}\n")
        create = {
            "type": "response.create",
            "response": {
                "conversation": "default",
                "modalities": ["text", "audio"],
                "input": [
                    {"role": "user", "content": [{"type": "input_text", "text": user_text}]}
                ],
                "audio": {"voice": "verse", "format": "wav"}
            }
        }
        self.control_channel.send(json.dumps(create))

    async def _handle_tool_call(self, evt: dict):
        call = evt.get("call", {})
        tool_name = call.get("name")
        call_id = call.get("id")
        args = call.get("arguments", {}) or {}

        print(f"🧰 Tool requested: {tool_name}({args})")

        if tool_name == "get_time":
            import datetime
            result = {"now": datetime.datetime.now().isoformat()}
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        result_evt = {"type": "tool.result", "call_id": call_id, "result": result}
        self.control_channel.send(json.dumps(result_evt))

    # ---------- Shutdown ----------
    async def close(self):
        try:
            self.mic.stop()
        except Exception:
            pass
        try:
            self.speaker.close()
        except Exception:
            pass
        await self.pc.close()

# --------------- Entrypoint ---------------
async def main():
    agent = RealtimeChainedAgent()

    def _sig(*_):
        asyncio.create_task(agent.close())
        try:
            loop = asyncio.get_event_loop()
            loop.stop()
        except Exception:
            pass

    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, _sig)

    try:
        await agent.connect()
        while True:
            await asyncio.sleep(1)
    finally:
        await agent.close()

if __name__ == "__main__":
    asyncio.run(main())
