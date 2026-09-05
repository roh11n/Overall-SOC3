"""QRadar offense ingestion + KPI derivation.

Parses a QRadar offense CSV/XLSX export (the wide offense schema with columns
like id, magnitude, severity, offenseSource, localizedCloseReason,
formattedCreatedTime, eventCount, domainName, closeUser ...) and computes
offense KPIs used by the SOC Manager dashboard, the Executive roll-up and the
PPTX incident-management slide.

False positives are counted directly from the QRadar `localizedCloseReason`
column: any value containing "false-positive" / "false positive" is an FP.
"""
from __future__ import annotations

import io
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd


def _norm_col(c: str) -> str:
    return re.sub(r"\s+", "", str(c).strip().lower())


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _parse_dt(v) -> Optional[str]:
    if not v or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        ts = pd.to_datetime(v, errors="coerce", utc=True)
        if pd.isna(ts):
            return None
        return ts.isoformat()
    except Exception:
        return None


def _first(row: Dict[str, Any], *keys):
    for k in keys:
        if k in row:
            val = _clean(row[k])
            if val is not None:
                return val
    return None


def _is_false_positive(reason) -> bool:
    r = (reason or "").strip().lower()
    if not r:
        return False
    return "false-positive" in r or "false positive" in r or "falsepositive" in r


def parse_rows(contents: bytes, filename: str) -> List[Dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents), low_memory=False)
    else:
        sheets = pd.read_excel(io.BytesIO(contents), sheet_name=None)
        frames = [f for f in sheets.values() if f is not None and not f.empty]
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    df.columns = [_norm_col(c) for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        row = r.to_dict()
        close_reason = _first(row, "localizedclosereason", "closedwithcustomizedreason",
                               "closereason", "dismissedcode")
        created = _parse_dt(_first(row, "formattedcreatedtime", "starttimeabs", "starttime",
                                   "formattedstarttime"))
        closed = _parse_dt(_first(row, "formattedcloseddate"))
        close_user = _first(row, "closeuser", "closingusername")
        is_closed = bool(closed or close_user or close_reason)
        rec = {
            "offense_id": _first(row, "id", "offenseid"),
            "description": _first(row, "description", "offensesource",
                                  "escapedformattedoffensesource", "fulldescription"),
            "offense_source": _first(row, "offensesource", "escapedformattedoffensesource"),
            "offense_type": _first(row, "formattedoffensetype", "offensemappertype"),
            "severity": _first(row, "severityformatted", "severity"),
            "magnitude": _first(row, "magnitude"),
            "event_count": _first(row, "eventcount", "formattedeventcount"),
            "category_count": _first(row, "categorycount"),
            "domain": _first(row, "domainname", "domaininfo"),
            "close_reason": close_reason,
            "close_user": close_user,
            "created": created,
            "closed": closed,
            "status": "Closed" if is_closed else "Open",
            "is_false_positive": _is_false_positive(close_reason),
        }
        if rec["offense_id"] is None and rec["description"] is None:
            continue
        rows.append(rec)
    return rows


async def save_upload(db, tenant_id: str, uploaded_by: str, filename: str,
                      rows: List[Dict[str, Any]]) -> str:
    upload_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    tid = tenant_id or "all"
    await db.qradar_rows.delete_many({"tenant_id": tid})
    if rows:
        docs = [{**r, "tenant_id": tid, "upload_id": upload_id, "uploaded_at": now} for r in rows]
        for i in range(0, len(docs), 1000):
            await db.qradar_rows.insert_many(docs[i:i + 1000])
    await db.qradar_uploads.insert_one({
        "upload_id": upload_id, "tenant_id": tid, "filename": filename,
        "row_count": len(rows), "uploaded_by": uploaded_by, "uploaded_at": now,
    })
    return upload_id


async def latest_upload(db, tenant_id: str) -> Optional[dict]:
    return await db.qradar_uploads.find_one(
        {"tenant_id": tenant_id or "all"}, sort=[("uploaded_at", -1)], projection={"_id": 0},
    )


async def _rows(db, tenant_id: str) -> List[dict]:
    return await db.qradar_rows.find(
        {"tenant_id": tenant_id or "all"}, projection={"_id": 0, "tenant_id": 0},
    ).to_list(200000)


async def delete_data(db, tenant_id: str):
    tid = tenant_id or "all"
    await db.qradar_rows.delete_many({"tenant_id": tid})
    await db.qradar_uploads.delete_many({"tenant_id": tid})


def _sev_norm(s: Optional[str]) -> str:
    if not s:
        return "Unknown"
    s2 = str(s).strip().lower()
    if s2 in {"critical", "5", "5.0"}:
        return "Critical"
    if s2 in {"high", "4", "4.0"}:
        return "High"
    if s2 in {"medium", "med", "3", "3.0"}:
        return "Medium"
    if s2 in {"low", "2", "2.0", "1", "1.0"}:
        return "Low"
    return str(s).title()


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


async def compute(db, tenant_id: str) -> Dict[str, Any]:
    rows = await _rows(db, tenant_id)
    upload = await latest_upload(db, tenant_id)
    if not rows:
        return {"data_status": "empty", "upload": None}

    total = len(rows)
    fp = sum(1 for r in rows if r.get("is_false_positive"))
    closed = sum(1 for r in rows if r.get("status") == "Closed")
    open_now = total - closed

    sev_c: Counter = Counter(_sev_norm(r.get("severity")) for r in rows)
    severity_distribution = [
        {"severity": k, "count": sev_c.get(k, 0)}
        for k in ("Critical", "High", "Medium", "Low", "Unknown")
        if sev_c.get(k, 0) > 0
    ]

    src_c: Counter = Counter(r.get("offense_source") for r in rows if r.get("offense_source"))
    top_sources = [{"source": (k or "")[:60], "count": v} for k, v in src_c.most_common(10)]

    # Timeline by created date (day, roll up to week if too many buckets)
    def _bins(bucket):
        c: Counter = Counter()
        for r in rows:
            d = r.get("created")
            if not d:
                continue
            try:
                ts = pd.to_datetime(d)
                label = ts.strftime("%Y-%m-%d") if bucket == "day" else f"{ts.isocalendar()[0]}-W{ts.isocalendar()[1]:02d}"
                c[label] += 1
            except Exception:
                continue
        return sorted(c.items())
    tl = _bins("day")
    if len(tl) > 45:
        tl = _bins("week")
    offenses_timeline = [{"date": d, "value": c} for d, c in tl]

    return {
        "data_status": "live",
        "upload": upload,
        "summary": {
            "total_offenses": total,
            "false_positives": fp,
            "false_positive_rate": _pct(fp, total),
            "closed": closed,
            "open": open_now,
        },
        "severity_distribution": severity_distribution,
        "top_sources": top_sources,
        "offenses_timeline": offenses_timeline,
    }
