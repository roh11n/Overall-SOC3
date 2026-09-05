"""Log-source inventory ingest (QRadar log-source export) → SOC Manager KPIs.

Computes:
  - Total Enabled Log Sources  (rows where the enabled/status column is truthy)
  - Log Sources Added          (rows that carry a parseable creation date)
  - Added in last 30 days      (recent onboarding, relative to newest creation)

Column detection is flexible so it works across QRadar export variants.
"""
from __future__ import annotations

import io
from datetime import timedelta
from typing import Any, Dict, List, Optional

import pandas as pd


def _norm(c: str) -> str:
    return str(c).strip().lower().replace("_", " ").replace("-", " ").strip()


def _find(cols: Dict[str, str], *candidates) -> Optional[str]:
    for cand in candidates:
        if cand in cols:
            return cols[cand]
    # substring fallback
    for norm, orig in cols.items():
        if any(cand in norm for cand in candidates):
            return orig
    return None


def _truthy_enabled(v) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True  # blank in an enabled column → treat as enabled
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if not s:
        return True
    disabled = {"false", "0", "0.0", "no", "n", "disabled", "inactive", "off",
                "error", "down", "stopped", "paused"}
    return s not in disabled


def parse_rows(contents: bytes, filename: str) -> List[Dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        frames = [pd.read_csv(io.BytesIO(contents), low_memory=False)]
    else:
        frames = [f for f in pd.read_excel(io.BytesIO(contents), sheet_name=None).values()
                  if f is not None and not f.empty]

    out: List[Dict[str, Any]] = []
    for df in frames:
        cols = {_norm(c): c for c in df.columns}
        name_col = _find(cols, "log source name", "logsourcename", "log source", "name",
                         "source name", "device name")
        enabled_col = _find(cols, "enabled", "status", "state", "is enabled")
        created_col = _find(cols, "creation date", "created date", "creationdate", "created",
                            "date added", "timestamp created", "creation time")
        if name_col is None and enabled_col is None:
            continue
        for _, r in df.iterrows():
            nm = r.get(name_col) if name_col else None
            nm = None if (nm is None or (isinstance(nm, float) and pd.isna(nm))) else str(nm).strip()
            # If there is an explicit enabled/status column use it, else assume enabled.
            enabled = _truthy_enabled(r.get(enabled_col)) if enabled_col else None
            created = None
            if created_col is not None:
                created = pd.to_datetime(r.get(created_col), errors="coerce", utc=True)
                created = None if pd.isna(created) else created.isoformat()
            if not nm and enabled_col is None and created_col is None:
                continue
            out.append({"name": nm, "enabled": enabled, "created": created})
        if out:
            break
    return out


async def save_upload(db, tenant_id: str, filename: str, rows: List[Dict[str, Any]]):
    tid = tenant_id or "all"
    await db.logsources_rows.delete_many({"tenant_id": tid})
    if rows:
        await db.logsources_rows.insert_many([{**r, "tenant_id": tid} for r in rows])
    from datetime import datetime, timezone
    await db.logsources_uploads.update_one(
        {"tenant_id": tid},
        {"$set": {"tenant_id": tid, "filename": filename, "row_count": len(rows),
                  "uploaded_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return len(rows)


async def latest_upload(db, tenant_id: str):
    return await db.logsources_uploads.find_one({"tenant_id": tenant_id or "all"}, {"_id": 0})


async def delete_data(db, tenant_id: str):
    tid = tenant_id or "all"
    await db.logsources_rows.delete_many({"tenant_id": tid})
    await db.logsources_uploads.delete_many({"tenant_id": tid})


async def compute(db, tenant_id: str) -> Dict[str, Any]:
    rows = await db.logsources_rows.find({"tenant_id": tenant_id or "all"}, {"_id": 0}).to_list(50000)
    if not rows:
        return {"data_status": "empty", "upload": None}

    total = len(rows)
    # Count as enabled unless the export explicitly marked the source disabled
    # (enabled is False). None means the file had no enabled/status column.
    enabled = sum(1 for r in rows if r.get("enabled") is not False)
    dated = [pd.to_datetime(r["created"]) for r in rows if r.get("created")]
    added_recent = 0
    if dated:
        newest = max(dated)
        cutoff = newest - timedelta(days=30)
        added_recent = sum(1 for d in dated if d >= cutoff)

    return {
        "data_status": "live",
        "upload": await latest_upload(db, tenant_id),
        "summary": {
            "total_log_sources": total,
            "total_enabled_log_sources": enabled,
            "log_sources_added": added_recent,
            "log_sources_added_total": len(dated),
        },
    }
