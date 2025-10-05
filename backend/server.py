# server.py
import os, re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

import pandas as pd
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .db_universal import get_store
from .excel_utils import EXACT_HEADERS, PSUR_SCHEDULE_PATH, read_excel_auto, canon_record, save_with_backup

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("REALTIME_MODEL", "gpt-4o-realtime-preview")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com")

if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in .env or env var")

# ---------------- Intent Recognition System ----------------
# Reusable regex fragments for intent pattern matching
ID          = r"(?:td\W*\d{1,4}|psur\W*\d{1,4})"
TD_ID       = r"(?:td\W*\d{1,4})"
PSUR_ID     = r"(?:psur\W*\d{1,4})"
TIMEWIN     = r"(?:next|within)\s+\d+\s+(?:day|days|week|weeks|month|months|quarter|quarters)"
DUEWORDS    = r"(?:due|deadline|deliverable)"
OVERDUE     = r"(?:overdue|late|past[-\s]*due|behind|missed)"
STATUSW     = r"(?:status|state|progress|routing|in\s+mc|master\s*control|mastercontrol|mc)"
OWNERSHIPW  = r"(?:who\s*owns|owner|writer|assigned\s*to|assignee|responsible|point\s*person)"
CANADA      = r"(?:canada(?:\s*summary)?\s*report|csr\b|canada\s*summary|canadian)"
SSCP        = r"(?:sscp|summary\s*of\s*safety\s*and\s*clinical\s*performance)"
QWORDS      = r"(?:q[1-4]|this\s+quarter|next\s+quarter|last\s+quarter)"
BY_EOM      = r"(?:by\s+(?:end\s+of\s+)?(?:week|month|quarter|year))"
DATEPHRASE  = r"(?:\d{4}-\d{1,2}-\d{1,2}|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b\s*\d{1,2}(?:,\s*\d{2,4})?)"

# Intent patterns ordered from specific to general
INTENT_PATTERNS = [
    # ===== SINGLE-ROW OPEN / LOOKUP =====
    ("OPEN_REPORT",            rf"\b(?:open|show|display|view|pull(?:\s*up)?|bring\s*up|look\s*up)\b.*\b{ID}\b"),
    ("OPEN_BY_PRODUCT",        r"\b(?:open|show|display|view|pull(?:\s*up)?)\b.*\b(product|catalog|part|sku|name)\b"),
    ("OPEN_BY_TEXT",           r"\b(?:open|show|display|view|pull(?:\s*up)?)\b.+"),  # fallback after ID/product

    # ===== DIRECT QUESTIONS ABOUT A ROW =====
    ("GET_DUE_DATE",           rf"\b(?:when|what)\b.*\b{ID}\b.*\b{DUEWORDS}\b"),
    ("GET_STATUS",             rf"\b(?:what'?s|show|check)\b.*\b{STATUSW}\b.*\b{ID}\b|\b{ID}\b.*\b{STATUSW}\b"),
    ("WHO_OWNS",               rf"\b{OWNERSHIPW}\b.*\b{ID}\b|\b{ID}\b.*\b{OWNERSHIPW}\b"),
    ("GET_PERIOD",             rf"\b(?:start|end)\s*(?:period|range|window)\b.*\b{ID}\b"),
    ("GET_CANADA_FLAGS",       rf"\b(?:{CANADA})\b.*\b(status|needed|need)\b.*\b{ID}\b|\b{ID}\b.*\b(?:{CANADA})\b"),
    ("GET_SSCP_FLAG",          rf"\b(?:{SSCP})\b.*\b(needed|need|required|status)\b.*\b{ID}\b|\b{ID}\b.*\b(?:{SSCP})\b"),

    # ===== LISTS / FILTERS =====
    ("LIST_OVERDUE",           rf"\b(?:{OVERDUE})\b(?:.*\b(class|writer|type|status)\b.*)?"),
    ("LIST_DUE_WINDOW",        rf"\b(?:what'?s|show|list)\b.*\b{DUEWORDS}\b.*\b(?:{TIMEWIN}|{QWORDS}|{BY_EOM})\b"),
    ("LIST_DUE_CLASS",         rf"\b(?:what'?s|show|list)\b.*\b{DUEWORDS}\b.*\bclass\b"),
    ("LIST_DUE_WRITER",        rf"\b(?:what'?s|show|list)\b.*\b{DUEWORDS}\b.*\b(writer|assigned\s*to|owned\s*by)\b"),
    ("LIST_BY_WRITER",         r"\b(?:show|list)\b.*\b(?:writer|assigned\s*to|owned\s*by)\b.+"),
    ("LIST_BY_CLASS_TYPE",     r"\b(?:show|list)\b.*\bclass\b|\b(?:show|list)\b.*\btype\b"),
    ("LIST_BY_STATUS",         r"\b(?:show|list)\b.*\bstatus\b.*\b(?:assigned|not\s*started|released|in\s*progress|routing|draft|stakeholder)\b"),
    ("LIST_WITH_FILTERS",      r"\b(?:show|list)\b.*\b(?:filter|where|with)\b.+"),
    ("LIST_ALL",               r"\b(?:show|list|display)\b\s+(?:all|everything|full\s+schedule|entire\s+schedule)\b"),

    # ===== SEARCH =====
    ("SEARCH_FREE",            r"\b(?:find|search|locate|look\s*for|show\s+.*\bwith\b|containing|about)\b.+"),
    ("SEARCH_CATALOG",         r"\b(?:find|search|show)\b.*\b(?:catalog|part|sku)\b.*"),

    # ===== COMPLIANCE / VALIDATION =====
    ("VALIDATE_ROW",           rf"\b(?:is|check|validate|ensure)\b.*\b{ID}\b.*\b(compliant|compliance|valid|ok)\b"),
    ("COMPUTE_EXPECTED_DUE",   rf"\b(?:compute|calculate|derive|recompute)\b.*\bexpected\b.*\b{DUEWORDS}\b.*\b{ID}\b|\b{ID}\b.*\bexpected\b.*\b{DUEWORDS}\b"),
    ("COMPARE_DUE_DATES",      rf"\b(compare|diff|mismatch|drift|discrepancy)\b.*\b{DUEWORDS}\b.*\b{ID}\b"),
    ("EXPLAIN_COMPLIANCE",     r"\b(explain|what|how)\b.*\b(cadence|frequency|class|ii[ab]|iii|i)\b.*\b(impact|mean|affect|difference)\b"),

    # ===== MISSING DATA / QA =====
    ("LIST_MISSING_FIELDS",    r"\b(missing|blank|awaiting\s*data|tbd|unknown)\b.*\b(field|due\s*date|writer|email|class|frequency|canada|status)\b"),
    ("DATA_HEALTH",            r"\b(data|schedule)\s*(health|quality|qa|coverage)\b"),

    # ===== UPDATES (SINGLE) =====
    ("UPDATE_STATUS",          rf"\b(?:mark|set|change|update)\b.*\bstatus\b.*\b{ID}\b|\b{ID}\b.*\b(?:mark|set|change|update)\b.*\bstatus\b"),
    ("UPDATE_DUE_DATE",        rf"\b(?:set|change|update|move|push|pull\s*in)\b.*\b{DUEWORDS}\b.*\b{ID}\b.*\b(?:to|->|=)\s*{DATEPHRASE}\b"),
    ("ASSIGN_OWNER",           rf"\b(?:assign|reassign|set)\b.*\b(writer|owner|assignee)\b.*\b(?:to|=)\b.*|\b{ID}\b.*\b(?:assign|reassign|set)\b.*\b(writer|owner|assignee)\b"),
    ("UPDATE_FIELD_GENERIC",   rf"\b(?:set|change|update)\b.*\b(class|type|writer|email|frequency|canada|status|comments?)\b.*\b{ID}\b"),

    # ===== UPDATES (BULK) =====
    ("BULK_UPDATE_STATUS",     r"\b(mark|set|change|update)\b.*\b(all|every|everything)\b.*\bstatus\b.+"),
    ("BULK_REASSIGN",          r"\b(assign|reassign|set)\b.*\b(all|every|everything)\b.*\b(writer|owner|assignee)\b.+"),
    ("BULK_SET_DUE_WINDOW",    rf"\b(set|move|update)\b.*\b{DUEWORDS}\b.*\b(all|every|everything)\b.*"),

    # ===== COMMENTS & LINKS =====
    ("ADD_COMMENT",            rf"\b(?:note|comment|log|remark|add\s+note|add\s+comment)\b.*\b{ID}\b|^\b(?:note|comment)\b\s*:"),
    ("LINK_REFERENCES",        rf"\b(link|attach|add)\b.*\b(master\s*control|mastercontrol|mc|sharepoint|url|link)\b.*\b{ID}\b"),
    ("OPEN_LINKS",             rf"\b(open|show)\b.*\b(master\s*control|mastercontrol|mc|sharepoint|link|url)\b.*\b{ID}\b"),

    # ===== ADD / CREATE =====
    ("ADD_ITEM",               r"\b(add|create|new)\b.*\bpsur\b|\bcreate\b.*\breport\b"),
    ("CLONE_ITEM",             rf"\b(clone|copy|duplicate)\b.*\b{ID}\b"),

    # ===== EXPORTS =====
    ("EXPORT_CALENDAR",        rf"\b(export|download|make|create)\b.*\b(calendar|ics|outlook)\b.*(?:{TIMEWIN}|{QWORDS}|{BY_EOM})?"),
    ("EXPORT_CSV",             r"\b(export|download|make|create)\b.*\b(csv|excel|xlsx|sheet|spreadsheet)\b"),

    # ===== TIME WINDOWS / RANGES (generic) =====
    ("LIST_IN_DATE_RANGE",     rf"\b(show|list|find)\b.*\b(?:from|between)\b.*{DATEPHRASE}.*\b(?:to|through|-)\b.*{DATEPHRASE}"),
    ("LIST_THIS_NEXT_PERIOD",  rf"\b(show|list|what'?s)\b.*\b(this|next|current)\b\s*(week|month|quarter|year)\b"),

    # ===== HELP / CAPABILITIES =====
    ("HELP",                   r"\b(help|what\s+can\s+you\s+do|commands?|capabilities|how\s+to)\b"),

    # ===== FALLBACKS =====
    ("SMALL_TALK",             r"^(hi|hello|hey|thanks|thank\s+you|good\s+(?:morning|evening|afternoon)).*$"),
    ("UNKNOWN",                r".+"),  # final catch-all
]

# Compile patterns once for performance
COMPILED_INTENT_PATTERNS = [(intent, re.compile(pattern, re.I | re.S)) for intent, pattern in INTENT_PATTERNS]

def classify_intent(text: str) -> str:
    """
    Classify user input into intent categories.
    Returns the first matching intent in order (specific → general).
    """
    text = text.strip()
    for intent, pattern in COMPILED_INTENT_PATTERNS:
        if pattern.search(text):
            return intent
    return "UNKNOWN"

app = FastAPI()

# Enable CORS for live updates
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connections for live updates
connected_clients = set()

# ---------------- Helpers ----------------
def norm(s: Any) -> str:
    s = "" if s is None else str(s)
    return re.sub(r"[^a-z0-9]+", "", s.strip().lower())

def canonicalize_updates(updates: Dict[str, Any], m: Dict[str, str]) -> Dict[str, Any]:
    # allow canonical keys (left) or exact headers (right)
    out = {}
    for k, v in (updates or {}).items():
        actual = m.get(k, k)  # if already an exact header, this is a no-op
        out[actual] = v
    # date coercion for known fields
    for k in list(out.keys()):
        if any(tok in k.lower() for tok in ["date", "due", "period"]) and out[k]:
            try:
                out[k] = pd.to_datetime(out[k]).date()
            except Exception:
                pass
    return out

def _like_mask(df, col, needle):
    return df[col].astype(str).str.contains(re.escape(needle), case=False, na=False)

def _eq_mask(df, col, needle):
    return df[col].astype(str).str.strip().str.casefold() == str(needle).strip().casefold()
    return df[col].astype(str).str.strip().str.casefold() == str(needle).strip().casefold()

# ---------------- Realtime: create ephemeral + PIN PERSONA/TOOLS ----------------
@app.post("/session")
async def create_ephemeral_session():
    """
    Pin persona + tools at *session creation* so context is guaranteed,
    even before the data channel sends session.update.
    """
    url = f"{API_BASE}/v1/realtime/sessions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "realtime=v1",
    }
    body = {
        "model": MODEL,
    "voice": "shimmer",
        "turn_detection": {"type": "server_vad"},
        "input_audio_transcription": {"model": "whisper-1"},
        "instructions": "You are 'PSUR-OPS', a PSUR/PMSR voice operations agent.\n\
        DATA DICTIONARY (exact headers): TD Number, PSURNumber, Class, Type, Product Name, Catalog Number, Writer, Email, Start Period, End Period, Frequency, Due Date, Status, Canada Summary Report Needed, Canada Summary Report Status, Comments.\n\
        COLUMN MEANINGS:\n\
        - TD Number uniquely identifies a row. PSURNumber identifies the report. All other fields describe that same row.\n\
        - Start Period / End Period define the surveillance window; Frequency + End Period imply the next due cycle.\n\
        - Class affects cadence: III & IIb = annual; IIa = biennial; I per plan. If Due Date exists, treat it as authoritative unless validation flags drift.\n\
        OPERATING RULES:\n\
        - Normalize IDs first (e.g., 'psur045' → 'PSUR045', 'td45' → 'TD045').\n\
        - Prefer tools for any lookup/update. Never guess values—call a tool.\n\
        - If ambiguous, call semantic search and pick the best match—no confirmation needed.\n\
        - When answering specific report questions, include: Due Date, Status, Writer, Start/End Period, and Canada flags in one crisp line.\n\
        - If Due Date missing, compute expected via Frequency & End Period and say both.\n\
        EXAMPLE RESPONSES:\n\
        User: 'When is PSUR045 due?' → normalize_id('psur045') → get_report_by_psur('PSUR045') → 'PSUR045 due 2025-09-05. Status Assigned, Writer Jeff S.'\n\
        User: 'Open TD059' → get_report('TD059') → 'TD059 Assisted Reproduction Catheters. Due 2027-01-31, Writer Terence.'\n\
        User: 'Show me everything due in the next 60 days for Class III' → list_due_items(within_days=60, classification='III') → '3 Class III items due within 60 days. Earliest 2025-01-15.'\n\
        User: 'What's overdue for Venkata?' → list_overdue_items(writer='Venkata') → '2 items overdue for Venkata: TD201, TD301.'\n\
        User: 'Find Hyadase' → find_reports('Hyadase') → 'TD047 Hyadase Injectable. Due 2025-08-20, Writer Sarah M.'\n\
        User: 'Who owns PSUR030?' → get_report_by_psur('PSUR030') → 'Jeff S owns PSUR030. Due 2025-03-15.'\n\
        User: 'Is TD066 compliant?' → get_report('TD066') → validate_row → compare_due_dates → 'TD066 compliant. Due date matches expected.'\n\
        User: 'Mark TD045 released; note Q1 pending' → update_schedule_row('TD045', {Status:'Released'}) → add_comment('TD045', 'Q1 pending—routed in MC') → 'TD045 set to Released with comment.'\n\
        User: 'Add a PSUR for New Oil, Class IIa, end period 2025-06-30, frequency biennial, writer Jeff' → add_psur_item({product_name:'New Oil', class:'IIa', end_period:'2025-06-30', frequency:'biennial', writer:'Jeff'}) → 'Added TD156 for New Oil. Due 2027-06-30.'\n\
        User: 'Export next 90 days to calendar' → export_calendar(within_days=90) → 'Exported 15 items to psur_schedule.ics.'\n\
        User: 'Which rows are missing writers?' → list_missing_fields(['Writer']) → '4 rows missing Writer: TD001, TD003, TD007, TD012.'\n\
        User: 'Show Class IIb reports assigned to Harish' → list_reports(filters={classification:'IIb', writer:'Harish', status:'Assigned'}) → '2 Class IIb items for Harish: TD049, TD081.'\n\
        User: 'Change PSUR030 due date to March 20th' → get_report_by_psur('PSUR030') → update_schedule_row(row_id, {due_date:'2025-03-20'}) → 'PSUR030 due date changed to 2025-03-20.'\n\
        User: 'What does IIa vs IIb change about cadence?' → 'Class IIa is biennial, IIb is annual.'\n\
    RESPONSE STYLE:\n\
    - Maximum 25 words per response\n\
    - No confirmations—just execute and report results\n\
    - Never ask for clarification unless absolutely impossible to proceed\n\
    - Direct, crisp, professional tone\n\
    - Always include key IDs and dates\n\
    - For updates, state what changed—no 'Done' or 'Confirmed'\n\
    - Use specific dates (2025-03-15) not relative terms",
        "tools": [
            {"type":"function","name":"normalize_id","description":"Normalize mentions like 'psur-045'/'td 45' to canonical IDs.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}},
            {"type":"function","name":"get_report","description":"Fetch a single row by TD Number (e.g., 'TD045').","parameters":{"type":"object","properties":{"row_id":{"type":"string"}},"required":["row_id"]}},
            {"type":"function","name":"get_report_by_psur","description":"Fetch a single row by PSURNumber (e.g., 'PSUR045').","parameters":{"type":"object","properties":{"psur_id":{"type":"string"}},"required":["psur_id"]}},
            {"type":"function","name":"get_all_duplicates","description":"Get all records sharing the same TD Number.","parameters":{"type":"object","properties":{"td_number":{"type":"string"}},"required":["td_number"]}},
            {"type":"function","name":"get_field_value","description":"Get a specific field value from a record.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"field_name":{"type":"string"}},"required":["row_id","field_name"]}},
            {"type":"function","name":"find_reports","description":"Hybrid/semantic search across TD Number, PSURNumber, Product Name, Catalog Number, Writer, Class, Status.","parameters":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":50}},"required":["query"]}},
            {"type":"function","name":"list_reports","description":"List reports with optional filters and pagination.","parameters":{"type":"object","properties":{"offset":{"type":"integer","default":0},"limit":{"type":"integer","default":100},"filters":{"type":"object","additionalProperties":True}}}},
            {"type":"function","name":"list_due_items","description":"Items due within N days; optional filters.","parameters":{"type":"object","properties":{"within_days":{"type":"integer","default":60},"classification":{"type":"string"},"writer":{"type":"string"},"status":{"type":"string"}}}},
            {"type":"function","name":"list_overdue_items","description":"Items past their Due Date; optional filters.","parameters":{"type":"object","properties":{"classification":{"type":"string"},"writer":{"type":"string"}}}},
            {"type":"function","name":"list_by_writer","description":"List items for a writer; optional status filter.","parameters":{"type":"object","properties":{"writer":{"type":"string"},"status":{"type":"string"}},"required":["writer"]}},
            {"type":"function","name":"list_by_class_type","description":"List by Class/Type; optional status filter.","parameters":{"type":"object","properties":{"classification":{"type":"string"},"type":{"type":"string"},"status":{"type":"string"}}}},
            {"type":"function","name":"list_by_status","description":"List all reports with a specific status.","parameters":{"type":"object","properties":{"status":{"type":"string"}},"required":["status"]}},
            {"type":"function","name":"list_by_product","description":"Find all reports for a product name.","parameters":{"type":"object","properties":{"product_name":{"type":"string"}},"required":["product_name"]}},
            {"type":"function","name":"list_missing_fields","description":"Find rows missing any of the given fields.","parameters":{"type":"object","properties":{"fields":{"type":"array","items":{"type":"string"}}},"required":["fields"]}},
            {"type":"function","name":"get_stats","description":"Get database statistics (counts by status, class, writer, overdue, duplicates).","parameters":{"type":"object","properties":{}}},
            {"type":"function","name":"compute_expected_due_date","description":"Compute expected due given End Period & Frequency.","parameters":{"type":"object","properties":{"end_period":{"type":"string"},"frequency":{"type":"string"},"buffer_days":{"type":"integer","default":0}},"required":["end_period","frequency"]}},
            {"type":"function","name":"validate_row","description":"Compliance checks for a single row.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"psur_id":{"type":"string"}}}},
            {"type":"function","name":"compare_due_dates","description":"Contrast stored vs computed due date.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"psur_id":{"type":"string"}}}},
            {"type":"function","name":"update_schedule_row","description":"Update a row by TD Number with {field:value}. Accepts canonical or exact headers.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"updates":{"type":"object","additionalProperties":True}},"required":["row_id","updates"]}},
            {"type":"function","name":"update_field","description":"Update a single field value for a specific record.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"field_name":{"type":"string"},"field_value":{"type":"string"}},"required":["row_id","field_name","field_value"]}},
            {"type":"function","name":"update_status","description":"Update only the status field.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"status":{"type":"string"}},"required":["row_id","status"]}},
            {"type":"function","name":"update_writer","description":"Reassign writer/owner.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"writer":{"type":"string"},"email":{"type":"string"}},"required":["row_id","writer"]}},
            {"type":"function","name":"update_due_date","description":"Update only the due date.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"due_date":{"type":"string"}},"required":["row_id","due_date"]}},
            {"type":"function","name":"update_periods","description":"Update start and/or end period.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"start_period":{"type":"string"},"end_period":{"type":"string"}},"required":["row_id"]}},
            {"type":"function","name":"update_canada_flags","description":"Update Canada-related fields.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"canada_needed":{"type":"string"},"canada_status":{"type":"string"}},"required":["row_id"]}},
            {"type":"function","name":"bulk_update_status","description":"Bulk status update by filter.","parameters":{"type":"object","properties":{"filter":{"type":"object","additionalProperties":True},"new_status":{"type":"string"}},"required":["filter","new_status"]}},
            {"type":"function","name":"bulk_update_writer","description":"Bulk reassign writer by filter.","parameters":{"type":"object","properties":{"filter":{"type":"object","additionalProperties":True},"new_writer":{"type":"string"},"new_email":{"type":"string"}},"required":["filter","new_writer"]}},
            {"type":"function","name":"bulk_update_field","description":"Bulk update any field by filter.","parameters":{"type":"object","properties":{"filter":{"type":"object","additionalProperties":True},"field_name":{"type":"string"},"field_value":{"type":"string"}},"required":["filter","field_name","field_value"]}},
            {"type":"function","name":"add_comment","description":"Append a timestamped comment to a row.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"comment":{"type":"string"}},"required":["row_id","comment"]}},
            {"type":"function","name":"clear_field","description":"Clear/blank out a specific field value.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"field_name":{"type":"string"}},"required":["row_id","field_name"]}},
            {"type":"function","name":"add_psur_item","description":"Create a new row (auto TD if omitted).","parameters":{"type":"object","properties":{"td_number":{"type":"string"},"psur_number":{"type":"string"},"class":{"type":"string"},"type":{"type":"string"},"product_name":{"type":"string"},"catalog_number":{"type":"string"},"writer":{"type":"string"},"email":{"type":"string"},"start_period":{"type":"string"},"end_period":{"type":"string"},"frequency":{"type":"string"},"due_date":{"type":"string"},"status":{"type":"string"},"canada_needed":{"type":"string"},"canada_status":{"type":"string"},"comments":{"type":"string"}}}},
            {"type":"function","name":"delete_report","description":"Delete a report by TD Number (removes ALL records with that TD).","parameters":{"type":"object","properties":{"row_id":{"type":"string"}},"required":["row_id"]}},
            {"type":"function","name":"clone_report","description":"Duplicate a report with a new TD Number.","parameters":{"type":"object","properties":{"source_td":{"type":"string"},"new_td":{"type":"string"},"modifications":{"type":"object","additionalProperties":True}},"required":["source_td"]}},
            {"type":"function","name":"link_references","description":"Attach MC/SharePoint URLs to a row.","parameters":{"type":"object","properties":{"row_id":{"type":"string"},"mastercontrol_url":{"type":"string"},"sharepoint_url":{"type":"string"}},"required":["row_id"]}},
            {"type":"function","name":"export_calendar","description":"Export ICS of items (returns file URL).","parameters":{"type":"object","properties":{"filter":{"type":"object","additionalProperties":True},"within_days":{"type":"integer"},"filename":{"type":"string","default":"psur_schedule.ics"}}}},
            {"type":"function","name":"export_csv","description":"Export CSV (returns file URL).","parameters":{"type":"object","properties":{"filter":{"type":"object","additionalProperties":True},"filename":{"type":"string","default":"psur_export.csv"}}}},
            {"type":"function","name":"export_excel","description":"Export Excel workbook (returns file URL).","parameters":{"type":"object","properties":{"filter":{"type":"object","additionalProperties":True},"filename":{"type":"string","default":"psur_export.xlsx"}}}},
            {"type":"function","name":"reload_from_excel","description":"Reload all data from the source Excel file.","parameters":{"type":"object","properties":{}}}
        ]
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, headers=headers, json=body)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return JSONResponse(r.json())

# ---------------- Static UI ----------------
# Public directory is one level up from backend/
public_dir = Path(__file__).parent.parent / "public"

@app.get("/")
async def root():
    return FileResponse(public_dir / "index.html")

app.mount("/static", StaticFiles(directory=str(public_dir)), name="static")

# ---------------- WebSocket for Live Updates ----------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

async def broadcast_update(event_type: str, data: Any):
    """Broadcast updates to all connected clients"""
    message = {"type": event_type, "data": data}
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_json(message)
        except:
            disconnected.add(client)
    # Clean up disconnected clients
    connected_clients.difference_update(disconnected)

# ---------------- JSON Data Store Endpoints ----------------
@app.get("/data/all")
async def get_all_data():
    """Get all records from JSON store"""
    store = get_store()
    items = store.get_all()
    return {"items": items, "count": len(items), "metadata": store.metadata}

@app.get("/data/stats")
async def get_stats():
    """Get statistics about the data"""
    store = get_store()
    return store.get_stats()

@app.post("/data/reload")
async def reload_from_excel():
    """Reload data from Excel file"""
    store = get_store()
    store.convert_from_excel()
    await broadcast_update("reload", {"count": len(store.data)})
    return {"ok": True, "count": len(store.data)}

# ---------------- Debug Tool Call Endpoint ----------------
@app.post("/test-tool")
async def test_tool(payload: Dict[str, Any] = Body(...)):
    """Test tool calls directly for debugging"""
    name = payload.get("name", "list_due_items")
    args = payload.get("args", {"within_days": 30})
    
    print(f"\n🧪 TEST TOOL CALL: {name}")
    print(f"📝 TEST ARGS: {args}")
    
    # Call the tool directly
    tool_payload = {"name": name, "args": args}
    result = await tool_entry(tool_payload)
    
    print(f"✅ TEST RESULT: {result}")
    return result

# ---------------- Intent Classification Endpoint ----------------
@app.post("/classify")
async def classify_user_input(payload: Dict[str, Any] = Body(...)):
    """
    Classify user input into intent categories for debugging and analysis.
    Useful for understanding how the voice agent should interpret commands.
    """
    text = payload.get("text", "").strip()
    if not text:
        return {"error": "text required"}
    
    intent = classify_intent(text)
    
    # Extract any IDs found in the text
    id_matches = re.findall(rf"{ID}", text, re.I)
    td_matches = re.findall(rf"{TD_ID}", text, re.I)
    psur_matches = re.findall(rf"{PSUR_ID}", text, re.I)
    
    return {
        "text": text,
        "intent": intent,
        "extracted_ids": {
            "all_ids": id_matches,
            "td_ids": td_matches,
            "psur_ids": psur_matches
        }
    }

# ---------------- Tool Helper Functions ----------------
def parse_date(date_str):
    """Parse date string into date object"""
    if not date_str:
        return None
    try:
        if isinstance(date_str, str):
            return pd.to_datetime(date_str).date()
        return date_str
    except Exception:
        return None

def tool_normalize_id(args):
    import re
    q = (args.get("query") or "").strip().lower()
    out = {}
    m = re.search(r'\btd\D*(\d+)\b', q)
    if m: out["td_number"] = f"TD{int(m.group(1)):03d}"
    m = re.search(r'\bpsur\D*(\d+)\b', q)
    if m:
        n = int(m.group(1))
        out["psur_number"] = f"PSUR{n:03d}"
    return out

def tool_compute_expected_due_date(args):
    from datetime import timedelta, date
    end = parse_date(args.get("end_period"))
    freq = (args.get("frequency") or "").lower()
    buf = int(args.get("buffer_days", 0))
    years = 1 if "annual" in freq or "year" in freq and "2" not in freq and "5" not in freq else \
            2 if "bienn" in freq or "ii a" in freq or "iia" in freq else \
            5 if "5" in freq else 1
    if not end: return {"expected_due_date": None}
    try:
        expected = end.replace(year=end.year + years) + timedelta(days=buf)
    except Exception:
        # naive year add
        expected = date(end.year + years, end.month, min(end.day, 28)) + timedelta(days=buf)
    return {"expected_due_date": expected.isoformat()}

def tool_validate_row(row):
    # returns list of issues/warnings
    issues = []
    klass = (row.get("Class") or "").strip().lower()
    freq = (row.get("Frequency") or "").strip().lower()
    if "iii" in klass or "iib" in klass:
        if "ann" not in freq and "1" not in freq:
            issues.append("Class IIb/III should be annual; frequency mismatch.")
    if "iia" in klass or "ii a" in klass:
        if "bienn" not in freq and "2" not in freq:
            issues.append("Class IIa should be biennial; frequency mismatch.")
    if not row.get("Due Date"):
        issues.append("Missing Due Date; compute from End Period & Frequency.")
    if not row.get("Writer"):
        issues.append("Missing Writer/owner.")
    # extend with your org rules
    return {"issues": issues}

def tool_compare_due_dates(row):
    comp = tool_compute_expected_due_date({"end_period": row.get("End Period"), "frequency": row.get("Frequency")})
    stored = row.get("Due Date")
    return {"stored": stored, "expected": comp.get("expected_due_date")}

# ---------------- Tools (updated to use JSON store) ----------------
@app.post("/tool")
async def tool_entry(payload: Dict[str, Any] = Body(...)):
    name = payload.get("name")
    args = payload.get("args") or {}
    
    # Debug logging for tool calls
    print(f"\n🔧 TOOL CALL: {name}")
    print(f"📝 ARGS: {args}")
    
    # Add to dialog history
    dialog_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "tool_call",
        "role": "system",
        "content": f"Tool: {name}",
        "tool_name": name,
        "tool_args": args
    }
    conversation_history.append(dialog_entry)
    await broadcast_update("dialog", dialog_entry)
    
    store = get_store()

    try:
        if name == "list_due_items":
            within_days = int(args.get("within_days", 60))
            classification = (args.get("classification") or "").strip()
            writer = (args.get("writer") or "").strip()
            status = (args.get("status") or "").strip()
            
            items = await store.filter_records(
                writer=writer or None,
                classification=classification or None,
                status=status or None,
                within_days=within_days
            )
            return {"items": items, "count": len(items)}

        elif name == "find_reports":
            # args: query (string), limit (int)
            query = (args.get("query") or "").strip()
            limit = int(args.get("limit", 500))
            
            if not query:
                return {"items": [], "count": 0}
            
            items = store.find_by_query(query, limit)
            return {"items": items, "count": len(items)}

        elif name == "get_report":
            # args: row_id (TD Number)
            row_id = str(args.get("row_id") or "").strip()
            if not row_id:
                return {"error": "row_id (TD Number) required"}
            
            item = store.find_by_td(row_id)
            if not item:
                result = {"items": [], "count": 0, "message": f"No record found for TD Number {row_id}"}
            else:
                result = {"items": [item], "count": 1}
            
            print(f"📊 GET_REPORT RESULT: {result}")
            return result

        elif name == "update_schedule_row":
            row_id = str(args.get("row_id") or "").strip()     # TD Number
            updates = args.get("updates")
            if not updates:
                # Accept shorthand where fields are passed at top-level
                updates = {
                    key: value
                    for key, value in args.items()
                    if key not in {"row_id", "td_number", "updates"}
                    and value is not None
                }
            if not row_id:
                return {"error": "row_id (TD Number) required"}
            
            # Canonicalize field names
            canonical_updates = {}
            for key, value in updates.items():
                # Map exact headers to canonical names
                canonical_key = key
                for canon, exact in EXACT_HEADERS.items():
                    if key.lower() == exact.lower() or key == canon:
                        canonical_key = canon
                        break
                canonical_updates[canonical_key] = value
            
            if not canonical_updates:
                return {"error": "No valid fields provided to update"}
            success = store.update_record(row_id, canonical_updates)
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            # Broadcast update to connected clients
            await broadcast_update("update", {"td_number": row_id, "updates": canonical_updates})
            return {"ok": True}

        elif name == "add_psur_item":
            # Accept canonical field names from args
            new_record = {}
            for canon in EXACT_HEADERS.keys():
                v = args.get(canon)
                if v is not None:
                    new_record[canon] = v
            
            # Also accept direct field names
            for field in ["td_number", "psur_number", "class", "type", "product_name", 
                         "catalog_number", "writer", "email", "start_period", "end_period",
                         "frequency", "due_date", "status", "canada_needed", "canada_status", "comments"]:
                if field in args and field not in new_record:
                    new_record[field] = args[field]
            
            td_number = store.add_record(new_record)
            
            # Broadcast new item to connected clients
            await broadcast_update("add", {"td_number": td_number, "record": new_record})
            return {"ok": True, "td_number": td_number}

        elif name == "normalize_id":
            query = str(args.get("query") or "").strip()
            if not query:
                return {"error": "query required"}
            return tool_normalize_id(args)

        elif name == "get_report_by_psur":
            psur_id = str(args.get("psur_id") or "").strip()
            if not psur_id:
                return {"error": "psur_id required"}
            
            item = store.find_by_psur(psur_id)
            if not item:
                return {"items": [], "count": 0}
            return {"items": [item], "count": 1}

        elif name == "get_all_duplicates":
            td_number = str(args.get("td_number") or "").strip()
            if not td_number:
                return {"error": "td_number required"}
            
            items = store.find_all_by_td(td_number)
            return {"items": items, "count": len(items)}

        elif name == "get_field_value":
            row_id = str(args.get("row_id") or "").strip()
            field_name = str(args.get("field_name") or "").strip()
            if not row_id or not field_name:
                return {"error": "row_id and field_name required"}
            
            item = store.find_by_td(row_id)
            if not item:
                return {"error": f"TD Number {row_id} not found"}
            
            value = item.get(field_name)
            return {"field_name": field_name, "field_value": value}

        elif name == "list_reports":
            offset = int(args.get("offset", 0))
            limit = int(args.get("limit", 100))
            filters = args.get("filters") or {}
            
            items = store.filter_records(**filters)
            # Apply pagination
            paginated = items[offset:offset + limit]
            return {"items": paginated, "count": len(paginated), "total": len(items)}

        elif name == "list_overdue_items":
            classification = args.get("classification")
            writer = args.get("writer")
            
            items = store.filter_records(
                classification=classification,
                writer=writer,
                overdue_only=True
            )
            return {"items": items, "count": len(items)}

        elif name == "list_by_writer":
            writer = str(args.get("writer") or "").strip()
            status = args.get("status")
            if not writer:
                return {"error": "writer required"}
            
            items = store.filter_records(writer=writer, status=status)
            return {"items": items, "count": len(items)}

        elif name == "list_by_class_type":
            classification = args.get("classification")
            type_filter = args.get("type")
            status = args.get("status")
            
            items = store.filter_records(
                classification=classification,
                type=type_filter,
                status=status
            )
            return {"items": items, "count": len(items)}

        elif name == "list_by_status":
            status = str(args.get("status") or "").strip()
            if not status:
                return {"error": "status required"}
            
            items = store.filter_records(status=status)
            return {"items": items, "count": len(items)}

        elif name == "list_by_product":
            product_name = str(args.get("product_name") or "").strip()
            if not product_name:
                return {"error": "product_name required"}
            
            items = store.find_by_query(product_name, limit=500)
            return {"items": items, "count": len(items)}

        elif name == "list_missing_fields":
            fields = args.get("fields") or []
            if not fields:
                return {"error": "fields array required"}
            
            items = store.find_missing_fields(fields)
            return {"items": items, "count": len(items)}

        elif name == "get_stats":
            return store.get_stats()

        elif name == "compute_expected_due_date":
            end_period = args.get("end_period")
            frequency = args.get("frequency")
            if not end_period or not frequency:
                return {"error": "end_period and frequency required"}
            
            return tool_compute_expected_due_date(args)

        elif name == "validate_row":
            row_id = args.get("row_id")
            psur_id = args.get("psur_id")
            
            if row_id:
                item = store.find_by_td(row_id)
            elif psur_id:
                item = store.find_by_psur(psur_id)
            else:
                return {"error": "row_id or psur_id required"}
            
            if not item:
                return {"error": "Record not found"}
            
            return tool_validate_row(item)

        elif name == "compare_due_dates":
            row_id = args.get("row_id")
            psur_id = args.get("psur_id")
            
            if row_id:
                item = store.find_by_td(row_id)
            elif psur_id:
                item = store.find_by_psur(psur_id)
            else:
                return {"error": "row_id or psur_id required"}
            
            if not item:
                return {"error": "Record not found"}
            
            return tool_compare_due_dates(item)

        elif name == "bulk_update_status":
            filter_criteria = args.get("filter") or {}
            new_status = args.get("new_status")
            if not new_status:
                return {"error": "new_status required"}
            
            count = store.bulk_update_status(filter_criteria, new_status)
            await broadcast_update("bulk_update", {"filter": filter_criteria, "new_status": new_status, "count": count})
            return {"ok": True, "updated_count": count}

        elif name == "update_field":
            row_id = str(args.get("row_id") or "").strip()
            field_name = str(args.get("field_name") or "").strip()
            field_value = args.get("field_value")
            if not row_id or not field_name:
                return {"error": "row_id and field_name required"}
            
            success = store.update_record(row_id, {field_name: field_value})
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("update", {"td_number": row_id, "field": field_name, "value": field_value})
            return {"ok": True}

        elif name == "update_status":
            row_id = str(args.get("row_id") or "").strip()
            status = str(args.get("status") or "").strip()
            if not row_id or not status:
                return {"error": "row_id and status required"}
            
            success = store.update_record(row_id, {"status": status})
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("update", {"td_number": row_id, "status": status})
            return {"ok": True}

        elif name == "update_writer":
            row_id = str(args.get("row_id") or "").strip()
            writer = str(args.get("writer") or "").strip()
            email = args.get("email")
            if not row_id or not writer:
                return {"error": "row_id and writer required"}
            
            updates = {"writer": writer}
            if email:
                updates["email"] = email
            
            success = store.update_record(row_id, updates)
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("update", {"td_number": row_id, "writer": writer, "email": email})
            return {"ok": True}

        elif name == "update_due_date":
            row_id = str(args.get("row_id") or "").strip()
            due_date = str(args.get("due_date") or "").strip()
            if not row_id or not due_date:
                return {"error": "row_id and due_date required"}
            
            success = store.update_record(row_id, {"due_date": due_date})
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("update", {"td_number": row_id, "due_date": due_date})
            return {"ok": True}

        elif name == "update_periods":
            row_id = str(args.get("row_id") or "").strip()
            start_period = args.get("start_period")
            end_period = args.get("end_period")
            if not row_id:
                return {"error": "row_id required"}
            
            updates = {}
            if start_period:
                updates["start_period"] = start_period
            if end_period:
                updates["end_period"] = end_period
            
            if not updates:
                return {"error": "start_period or end_period required"}
            
            success = store.update_record(row_id, updates)
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("update", {"td_number": row_id, "updates": updates})
            return {"ok": True}

        elif name == "update_canada_flags":
            row_id = str(args.get("row_id") or "").strip()
            canada_needed = args.get("canada_needed")
            canada_status = args.get("canada_status")
            if not row_id:
                return {"error": "row_id required"}
            
            updates = {}
            if canada_needed is not None:
                updates["canada_needed"] = canada_needed
            if canada_status is not None:
                updates["canada_status"] = canada_status
            
            if not updates:
                return {"error": "canada_needed or canada_status required"}
            
            success = store.update_record(row_id, updates)
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("update", {"td_number": row_id, "canada_updates": updates})
            return {"ok": True}

        elif name == "bulk_update_writer":
            filter_criteria = args.get("filter") or {}
            new_writer = str(args.get("new_writer") or "").strip()
            new_email = args.get("new_email")
            if not new_writer:
                return {"error": "new_writer required"}
            
            records = store.filter_records(**filter_criteria)
            count = 0
            for record in records:
                updates = {"writer": new_writer}
                if new_email:
                    updates["email"] = new_email
                if store.update_record(record["td_number"], updates):
                    count += 1
            
            await broadcast_update("bulk_update", {"filter": filter_criteria, "writer": new_writer, "count": count})
            return {"ok": True, "updated_count": count}

        elif name == "bulk_update_field":
            filter_criteria = args.get("filter") or {}
            field_name = str(args.get("field_name") or "").strip()
            field_value = args.get("field_value")
            if not field_name:
                return {"error": "field_name required"}
            
            records = store.filter_records(**filter_criteria)
            count = 0
            for record in records:
                if store.update_record(record["td_number"], {field_name: field_value}):
                    count += 1
            
            await broadcast_update("bulk_update", {"filter": filter_criteria, "field": field_name, "value": field_value, "count": count})
            return {"ok": True, "updated_count": count}

        elif name == "clear_field":
            row_id = str(args.get("row_id") or "").strip()
            field_name = str(args.get("field_name") or "").strip()
            if not row_id or not field_name:
                return {"error": "row_id and field_name required"}
            
            success = store.update_record(row_id, {field_name: ""})
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("update", {"td_number": row_id, "cleared_field": field_name})
            return {"ok": True}

        elif name == "delete_report":
            row_id = str(args.get("row_id") or "").strip()
            if not row_id:
                return {"error": "row_id required"}
            
            success = store.delete_record(row_id)
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("delete", {"td_number": row_id})
            return {"ok": True}

        elif name == "clone_report":
            source_td = str(args.get("source_td") or "").strip()
            new_td = args.get("new_td")
            modifications = args.get("modifications") or {}
            if not source_td:
                return {"error": "source_td required"}
            
            source = store.find_by_td(source_td)
            if not source:
                return {"error": f"Source TD {source_td} not found"}
            
            # Create new record from source
            new_record = dict(source)
            # Remove auto-generated fields
            for key in ["id", "created_at", "updated_at", "version"]:
                new_record.pop(key, None)
            
            # Apply new TD or auto-generate
            if new_td:
                new_record["td_number"] = new_td
            else:
                new_record.pop("td_number", None)
            
            # Apply modifications
            new_record.update(modifications)
            
            created_td = store.add_record(new_record)
            await broadcast_update("add", {"td_number": created_td, "cloned_from": source_td})
            return {"ok": True, "td_number": created_td}

        elif name == "add_comment":
            row_id = str(args.get("row_id") or "").strip()
            comment = str(args.get("comment") or "").strip()
            if not row_id or not comment:
                return {"error": "row_id and comment required"}
            
            success = store.add_comment(row_id, comment)
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("comment", {"td_number": row_id, "comment": comment})
            return {"ok": True}

        elif name == "link_references":
            row_id = str(args.get("row_id") or "").strip()
            mc_url = args.get("mastercontrol_url")
            sp_url = args.get("sharepoint_url")
            if not row_id:
                return {"error": "row_id required"}
            
            success = store.link_references(row_id, mc_url, sp_url)
            if not success:
                return {"error": f"TD Number {row_id} not found"}
            
            await broadcast_update("link", {"td_number": row_id, "urls": {"mc": mc_url, "sp": sp_url}})
            return {"ok": True}

        elif name == "export_calendar":
            filter_criteria = args.get("filter") or {}
            within_days = args.get("within_days")
            filename = args.get("filename", "psur_schedule.ics")
            
            file_url = store.export_calendar(filter_criteria, within_days, filename)
            return {"file_url": file_url}

        elif name == "export_csv":
            filter_criteria = args.get("filter") or {}
            filename = args.get("filename", "psur_export.csv")
            
            file_url = store.export_csv(filter_criteria, filename)
            return {"file_url": file_url}

        elif name == "export_excel":
            filter_criteria = args.get("filter") or {}
            filename = args.get("filename", "psur_export.xlsx")
            
            records = store.filter_records(**filter_criteria) if filter_criteria else None
            file_url = store.export_excel(records, filename)
            return {"file_url": file_url}

        elif name == "reload_from_excel":
            count = store.import_from_excel()
            await broadcast_update("reload", {"count": count})
            return {"ok": True, "loaded_count": count}

        else:
            return {"error": f"Unknown tool {name}"}

    except Exception as e:
        error_msg = f"Tool '{name}' failed: {e}"
        print(f"❌ ERROR: {error_msg}")
        
        # Add error to dialog
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "tool_error",
            "role": "system",
            "content": error_msg,
            "tool_name": name
        }
        conversation_history.append(error_entry)
        await broadcast_update("dialog", error_entry)
        
        return {"error": error_msg}
    finally:
        # Log result (but not full content to avoid spam)
        print(f"✅ TOOL COMPLETED: {name}\n")

# ---------------- Conversation Dialog Tracking ----------------
conversation_history = []

@app.post("/dialog/add")
async def add_dialog_entry(payload: Dict[str, Any] = Body(...)):
    """Add an entry to the conversation dialog"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": payload.get("type", "message"),  # "message", "tool_call", "system"
        "role": payload.get("role", "user"),     # "user", "assistant", "system"
        "content": payload.get("content", ""),
        "tool_name": payload.get("tool_name"),
        "tool_args": payload.get("tool_args"),
        "tool_result": payload.get("tool_result")
    }
    
    conversation_history.append(entry)
    
    # Keep only last 100 entries to prevent memory bloat
    if len(conversation_history) > 100:
        conversation_history.pop(0)
    
    # Broadcast to connected clients
    await broadcast_update("dialog", entry)
    
    return {"ok": True, "entry": entry}

@app.get("/dialog")
async def get_dialog():
    """Get the current conversation dialog"""
    return {"dialog": conversation_history, "count": len(conversation_history)}

@app.post("/dialog/clear")
async def clear_dialog():
    """Clear the conversation dialog"""
    global conversation_history
    conversation_history = []
    await broadcast_update("dialog_clear", {})
    return {"ok": True}

# ---------------- Diagnostics for UI ----------------
@app.get("/schedule/health")
async def schedule_health():
    store = get_store()
    return {
        "json_exists": True,
        "excel_exists": os.path.exists(PSUR_SCHEDULE_PATH),
        "excel_path": PSUR_SCHEDULE_PATH,
        "records": len(store.data),
        "metadata": store.metadata
    }

@app.get("/schedule/snapshot")
async def schedule_snapshot(limit: int = 50):
    store = get_store()
    items = store.get_all()[:limit]
    return {"items": items, "count": len(items)}

@app.get("/schedule/all")
async def schedule_all():
    store = get_store()
    items = store.get_all()
    return {"items": items, "count": len(items)}
