"""Log-validation ingest (single 'Priority' column) → Detection priority pie."""
import io
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger("mssp-soc.logval")

_KNOWN = {"essential": "Essential", "selective": "Selective",
          "redundant": "Redundant", "undefined": "Undefined"}


def _norm_priority(v) -> str:
    s = "" if v is None else str(v).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    return _KNOWN.get(s.lower(), s.strip().title())


def parse_rows(contents: bytes, filename: str) -> List[Dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        frames = [pd.read_csv(io.BytesIO(contents))]
    else:
        frames = list(pd.read_excel(io.BytesIO(contents), sheet_name=None).values())

    out = []
    for df in frames:
        col = next((c for c in df.columns if str(c).strip().lower() == "priority"), None)
        if col is None:
            continue
        for v in df[col].tolist():
            p = _norm_priority(v)
            if p:
                out.append({"priority": p})
    return out


async def save_upload(db, tenant_id: str, filename: str, rows: List[Dict[str, Any]]):
    tid = tenant_id or "all"
    await db.logval_rows.delete_many({"tenant_id": tid})
    if rows:
        await db.logval_rows.insert_many([{**r, "tenant_id": tid} for r in rows])
    await db.logval_uploads.update_one(
        {"tenant_id": tid},
        {"$set": {"tenant_id": tid, "filename": filename, "row_count": len(rows),
                  "uploaded_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return len(rows)


async def latest_upload(db, tenant_id: str):
    return await db.logval_uploads.find_one({"tenant_id": tenant_id or "all"}, {"_id": 0})


async def delete_data(db, tenant_id: str):
    tid = tenant_id or "all"
    await db.logval_rows.delete_many({"tenant_id": tid})
    await db.logval_uploads.delete_many({"tenant_id": tid})


async def compute(db, tenant_id: str) -> Dict[str, Any]:
    rows = await db.logval_rows.find({"tenant_id": tenant_id or "all"}, {"_id": 0}).to_list(20000)
    if not rows:
        return {"data_status": "empty"}
    counts = Counter(r["priority"] for r in rows)
    order = ["Essential", "Selective", "Redundant", "Undefined"]
    breakdown = [{"name": k, "value": counts[k]} for k in order if counts.get(k)]
    breakdown += [{"name": k, "value": v} for k, v in counts.items() if k not in order]
    return {
        "data_status": "live",
        "total": len(rows),
        "priority_breakdown": breakdown,
        "upload": await latest_upload(db, tenant_id),
    }
