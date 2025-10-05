"""Convex database client for PSUR schedule - SYNC VERSION (replaces SQLite)."""
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

CONVEX_URL = os.getenv("CONVEX_URL", "https://unique-heron-539.convex.cloud").rstrip("/")


class ConvexStore:
    """Synchronous Convex database client."""
    
    def __init__(self):
        self.base_url = CONVEX_URL
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self.metadata = {"source": "convex", "url": CONVEX_URL}
        print(f"✅ Convex store initialized: {self.base_url}")
    
    def _call_query(self, function_path: str, args: Dict[str, Any] = None) -> Any:
        """Call a Convex query function."""
        try:
            response = self.client.post(
                "/api/query",
                json={"path": function_path, "args": args or {}, "format": "json"}
            )
            response.raise_for_status()
            result = response.json()
            return result.get("value") if "value" in result else result
        except Exception as e:
            print(f"❌ Convex query failed ({function_path}): {e}")
            return None
    
    def _call_mutation(self, function_path: str, args: Dict[str, Any] = None) -> Any:
        """Call a Convex mutation function."""
        try:
            response = self.client.post(
                "/api/mutation",
                json={"path": function_path, "args": args or {}, "format": "json"}
            )
            response.raise_for_status()
            result = response.json()
            return result.get("value") if "value" in result else result
        except Exception as e:
            print(f"❌ Convex mutation failed ({function_path}): {e}")
            return None
    
    def _clean_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Remove Convex internal fields (_id, _creationTime)."""
        if not record:
            return record
        return {k: v for k, v in record.items() if not k.startswith('_')}
    
    # ========== QUERIES ==========
    
    def find_by_td(self, td_number: str) -> Optional[Dict[str, Any]]:
        """Find first record by TD Number."""
        result = self._call_query("psur:getByTd", {"tdNumber": td_number})
        return self._clean_record(result) if result else None
    
    def find_all_by_td(self, td_number: str) -> List[Dict[str, Any]]:
        """Find all records with same TD Number (for duplicates)."""
        results = self._call_query("psur:getAllByTd", {"tdNumber": td_number}) or []
        return [self._clean_record(r) for r in results]
    
    def find_by_psur(self, psur_number: str) -> Optional[Dict[str, Any]]:
        """Find record by PSUR Number."""
        result = self._call_query("psur:getByPsur", {"psurNumber": psur_number})
        return self._clean_record(result) if result else None
    
    def find_by_query(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Semantic search across fields."""
        results = self._call_query("psur:search", {"query": query, "limit": limit}) or []
        return [self._clean_record(r) for r in results]
    
    def filter_records(
        self,
        writer: Optional[str] = None,
        classification: Optional[str] = None,
        status: Optional[str] = None,
        within_days: Optional[int] = None,
        overdue_only: bool = False,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Filter records with multiple criteria."""
        args = {}
        if writer:
            args["writer"] = writer
        if classification:
            args["classification"] = classification
        if status:
            args["status"] = status
        if overdue_only:
            args["overdue"] = True
        if within_days:
            cutoff = (date.today() + timedelta(days=within_days)).isoformat()
            args["dueBefore"] = cutoff
        
        results = self._call_query("psur:filter", args) or []
        return [self._clean_record(r) for r in results]
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all records."""
        results = self._call_query("psur:getAll") or []
        return [self._clean_record(r) for r in results]
    
    def find_missing_fields(self, fields: List[str]) -> List[Dict[str, Any]]:
        """Find records missing specified fields."""
        results = self._call_query("psur:findMissingFields", {"fields": fields}) or []
        return [self._clean_record(r) for r in results]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        return self._call_query("psur:getStats") or {}
    
    # ========== MUTATIONS ==========
    
    def add_record(self, record: Dict[str, Any]) -> str:
        """Add new record and return TD Number."""
        clean = {k: v for k, v in record.items() if not k.startswith('_') and v is not None}
        result = self._call_mutation("psur:create", clean)
        
        if result and isinstance(result, dict):
            return result.get("td_number", record.get("td_number", "UNKNOWN"))
        return record.get("td_number", "UNKNOWN")
    
    def update_record(self, td_number: str, updates: Dict[str, Any]) -> bool:
        """Update record by TD Number (first match)."""
        clean_updates = {k: v for k, v in updates.items() if not k.startswith('_')}
        result = self._call_mutation("psur:update", {
            "tdNumber": td_number,
            "updates": clean_updates
        })
        return bool(result)
    
    def delete_record(self, td_number: str) -> bool:
        """Delete ALL records with given TD Number."""
        result = self._call_mutation("psur:deleteRecord", {"tdNumber": td_number})
        return bool(result)
    
    def bulk_update_status(self, filter_criteria: Dict[str, Any], new_status: str) -> int:
        """Bulk status update by filter."""
        result = self._call_mutation("psur:bulkUpdateStatus", {
            "filter": filter_criteria,
            "newStatus": new_status
        })
        return result if isinstance(result, int) else 0
    
    def add_comment(self, td_number: str, comment: str) -> bool:
        """Append timestamped comment to record."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamped = f"[{timestamp}] {comment}"
        result = self._call_mutation("psur:addComment", {
            "tdNumber": td_number,
            "comment": timestamped
        })
        return bool(result)
    
    def link_references(
        self, 
        td_number: str, 
        mc_url: Optional[str] = None, 
        sp_url: Optional[str] = None
    ) -> bool:
        """Attach MC/SharePoint URLs to record."""
        args = {"tdNumber": td_number}
        if mc_url:
            args["mastercontrolUrl"] = mc_url
        if sp_url:
            args["sharepointUrl"] = sp_url
        
        result = self._call_mutation("psur:linkReferences", args)
        return bool(result)
    
    # ========== EXPORT STUBS (TODO) ==========
    
    def export_excel(self, records: Optional[List[Dict]] = None, filename: str = "export.xlsx") -> str:
        """Export to Excel (stub)."""
        print("⚠️  Excel export not yet implemented for Convex")
        return filename
    
    def export_csv(self, filter_criteria: Dict = None, filename: str = "export.csv") -> str:
        """Export to CSV (stub)."""
        print("⚠️  CSV export not yet implemented for Convex")
        return filename
    
    def export_calendar(
        self, 
        filter_criteria: Dict = None, 
        within_days: int = None, 
        filename: str = "calendar.ics"
    ) -> str:
        """Export to ICS calendar (stub)."""
        print("⚠️  Calendar export not yet implemented for Convex")
        return filename
    
    def import_from_excel(self, excel_path: Optional[str] = None) -> int:
        """Import from Excel (stub)."""
        print("⚠️  Excel import not yet implemented for Convex")
        return 0
    
    def close(self):
        """Close HTTP client."""
        self.client.close()


# Global store instance
_store: Optional[ConvexStore] = None


def get_store() -> ConvexStore:
    """Get or create the global Convex store instance."""
    global _store
    if _store is None:
        _store = ConvexStore()
    return _store


def close_store():
    """Close the global store instance."""
    global _store
    if _store:
        _store.close()
        _store = None
