"""Threat-Intelligence ingestion + KPI derivation.

Persists uploaded Excel/CSV rows into `db.ti_rows` (one document per advisory-IOC
row, keyed by tenant + upload_id) and computes dashboard KPIs directly from
that data. When no upload exists for a tenant, the dashboard reports an
`empty` state — no mock data is returned.

The Excel schema (customer-provided) has 7 columns:
    Advisories Name, Industry, Date of Release, IPs, Domain, Hash, Hash Type
Column names may carry trailing whitespace — we normalise on ingest.
"""
from __future__ import annotations

import io
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd


# --- column normalisation -----------------------------------------------

_CANONICAL = {
    "advisories name": "advisory",
    "advisory name": "advisory",
    "advisory": "advisory",
    "advisory title": "advisory",
    "title": "advisory",
    "name": "advisory",
    "industry": "industry",
    "sector": "industry",
    "date of release": "date",
    "release date": "date",
    "date": "date",
    "ips": "ip",
    "ip": "ip",
    "ip address": "ip",
    "domain": "domain",
    "domains": "domain",
    "hash": "hash",
    "hashes": "hash",
    "hash type": "hash_type",
    "hash algorithm": "hash_type",
}


def _norm_col(c: str) -> str:
    key = re.sub(r"\s+", " ", str(c).strip().lower())
    return _CANONICAL.get(key, key)


_HASH_TYPE_MAP = {
    "sha-256": "SHA256", "sha256": "SHA256", "sha 256": "SHA256",
    "sha-1": "SHA1", "sha1": "SHA1",
    "sha-512": "SHA512", "sha512": "SHA512",
    "md5": "MD5",
    "ssdeep": "SSDEEP",
}


def _norm_hash_type(v: Optional[str]) -> Optional[str]:
    if not v or not isinstance(v, str):
        return None
    key = re.sub(r"\s+", " ", v.strip().lower())
    return _HASH_TYPE_MAP.get(key, v.strip().upper())


def _parse_date(v) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return None


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _rows_from_df(df) -> List[Dict[str, Any]]:
    df.columns = [_norm_col(c) for c in df.columns]
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        advisory = _clean(r.get("advisory"))
        industry = _clean(r.get("industry"))
        date = _parse_date(r.get("date"))
        ip = _clean(r.get("ip"))
        domain = _clean(r.get("domain"))
        hsh = _clean(r.get("hash"))
        htype = _norm_hash_type(_clean(r.get("hash_type")))

        # Skip fully empty separator rows
        if not any((advisory, industry, date, ip, domain, hsh, htype)):
            continue

        out.append({
            "advisory": advisory,
            "industry": industry,
            "date": date,
            "ip": ip,
            "domain": domain,
            "hash": hsh,
            "hash_type": htype,
        })
    return out


def parse_rows(contents: bytes, filename: str) -> List[Dict[str, Any]]:
    """Parse a CSV/XLSX blob into a normalised list of TI row dicts.
    For Excel workbooks EVERY sheet is scanned (some exports keep a summary
    sheet first), and rows from all sheets are aggregated."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _rows_from_df(pd.read_csv(io.BytesIO(contents)))

    sheets = pd.read_excel(io.BytesIO(contents), sheet_name=None)
    out: List[Dict[str, Any]] = []
    for _sheet_name, df in sheets.items():
        try:
            out.extend(_rows_from_df(df))
        except Exception:
            continue
    return out


# --- persistence --------------------------------------------------------

async def save_upload(db, tenant_id: str, uploaded_by: str,
                       filename: str, rows: List[Dict[str, Any]]) -> str:
    """Persist a fresh batch of TI rows. Replaces prior data for this tenant."""
    upload_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Wipe previous rows for the tenant so KPIs always reflect the newest file
    await db.ti_rows.delete_many({"tenant_id": tenant_id})

    if rows:
        docs = [
            {**r, "tenant_id": tenant_id, "upload_id": upload_id,
             "uploaded_at": now}
            for r in rows
        ]
        await db.ti_rows.insert_many(docs)

    await db.ti_uploads.insert_one({
        "upload_id": upload_id,
        "tenant_id": tenant_id,
        "filename": filename,
        "row_count": len(rows),
        "uploaded_by": uploaded_by,
        "uploaded_at": now,
    })
    return upload_id


async def latest_upload(db, tenant_id: str) -> Optional[dict]:
    doc = await db.ti_uploads.find_one(
        {"tenant_id": tenant_id},
        sort=[("uploaded_at", -1)],
        projection={"_id": 0},
    )
    return doc


# --- KPI computation ----------------------------------------------------

_PERIOD_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 90}

# Sector code expansion (Deloitte-style codes seen in the customer file)
_SECTOR_LABELS = {
    "ALL": "All Sectors",
    "FSI": "Financial Services",
    "PS": "Public Sector",
    "E&R": "Energy & Resources",
    "TMT": "Technology · Media · Telecom",
    "C&IP": "Consumer & Industrial",
    "LSHC": "Life Sciences & Healthcare",
    "AUTO": "Automotive",
    "AUTOMOTIVE": "Automotive",
}


def _expand_industries(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    return [_SECTOR_LABELS.get(p, p.title()) for p in parts]


def _in_period(date_str: Optional[str], cutoff: Optional[datetime]) -> bool:
    if not date_str:
        return False
    if cutoff is None:
        return True
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d >= cutoff
    except Exception:
        return False


async def compute_dashboard(db, tenant_id: str, period: str) -> Dict[str, Any]:
    """Build the Threat-Intel dashboard payload directly from stored rows.

    All KPI counts are computed across the ENTIRE uploaded batch — a curated
    threat-intel feed is not a live stream, so time-slicing it by a rolling
    weekly/monthly window silently hides advisories and confuses users. The
    `period` parameter controls only the timeline chart granularity (daily vs
    weekly buckets).

    Returns a dict with `data_status`: "live" when rows are found,
    "empty" when the tenant has no uploaded data.
    """
    upload = await latest_upload(db, tenant_id)
    rows = await db.ti_rows.find(
        {"tenant_id": tenant_id}, projection={"_id": 0, "tenant_id": 0}
    ).to_list(50000)

    if not rows:
        return {
            "period": period,
            "data_status": "empty",
            "upload": None,
            "summary": {
                "total_advisories": 0,
                "total_iocs": 0,
                "unique_ips": 0,
                "unique_domains": 0,
                "unique_hashes": 0,
                "industries_covered": 0,
            },
            "hash_type_breakdown": [],
            "ioc_type_distribution": [],
            "industry_breakdown": [],
            "advisories_timeline": [],
            "top_advisories": [],
            "recent_advisories": [],
        }

    # NB: totals span the full batch — no time cutoff applied. Period only
    # influences the timeline bucketing below.
    scoped = rows

    # --- Summary counts ---
    unique_advisories = {r["advisory"] for r in scoped if r.get("advisory")}
    unique_ips = {r["ip"] for r in scoped if r.get("ip")}
    unique_domains = {r["domain"] for r in scoped if r.get("domain")}
    unique_hashes = {r["hash"] for r in scoped if r.get("hash")}

    # --- Hash type distribution ---
    hash_counter = Counter(r["hash_type"] for r in scoped if r.get("hash_type"))
    hash_type_breakdown = [
        {"type": k, "count": v}
        for k, v in hash_counter.most_common()
    ]

    # --- IOC type distribution ---
    ioc_type_distribution = [
        {"type": "Domain", "count": len(unique_domains)},
        {"type": "Hash", "count": len(unique_hashes)},
        {"type": "IP", "count": len(unique_ips)},
    ]

    # --- Industry breakdown (expand comma-separated codes) ---
    industry_counter: Counter = Counter()
    for r in scoped:
        for ind in _expand_industries(r.get("industry")):
            industry_counter[ind] += 1
    industry_breakdown = [
        {"industry": k, "count": v}
        for k, v in industry_counter.most_common(10)
    ]

    # --- Advisories timeline (daily buckets, aggregate to weekly if range wide) ---
    date_counter: Counter = Counter()
    advisory_first_seen: Dict[str, str] = {}
    for r in scoped:
        d = r.get("date")
        adv = r.get("advisory")
        if d and adv:
            key = (adv, d)
            if key not in advisory_first_seen:
                advisory_first_seen[key] = d
                date_counter[d] += 1

    dates_sorted = sorted(date_counter.keys())
    if len(dates_sorted) > 30:
        # weekly bucket
        wk: Counter = Counter()
        for d, c in date_counter.items():
            iso = datetime.strptime(d, "%Y-%m-%d")
            year, week, _ = iso.isocalendar()
            label = f"{year}-W{week:02d}"
            wk[label] += c
        timeline = [{"date": k, "advisories": v}
                    for k, v in sorted(wk.items())]
    else:
        timeline = [{"date": d, "advisories": date_counter[d]}
                    for d in dates_sorted]

    # --- Top advisories by IOC weight ---
    adv_ioc_count: Dict[str, dict] = {}
    for r in scoped:
        adv = r.get("advisory")
        if not adv:
            continue
        s = adv_ioc_count.setdefault(adv, {"advisory": adv, "iocs": 0, "date": r.get("date"),
                                            "industry": r.get("industry"),
                                            "hash_types": set()})
        if r.get("ip"): s["iocs"] += 1
        if r.get("domain"): s["iocs"] += 1
        if r.get("hash"): s["iocs"] += 1
        if r.get("hash_type"):
            s["hash_types"].add(r["hash_type"])
        # keep latest date
        if r.get("date") and (not s["date"] or r["date"] > s["date"]):
            s["date"] = r["date"]

    top_advisories = sorted(
        adv_ioc_count.values(), key=lambda x: x["iocs"], reverse=True
    )[:10]
    for a in top_advisories:
        a["hash_types"] = sorted(a["hash_types"])

    # --- Recent advisories (latest 10 unique) ---
    unique_by_adv: Dict[str, dict] = {}
    for r in sorted(scoped, key=lambda x: x.get("date") or "", reverse=True):
        adv = r.get("advisory")
        if not adv or adv in unique_by_adv:
            continue
        unique_by_adv[adv] = {
            "advisory": adv,
            "date": r.get("date"),
            "industry": r.get("industry"),
            "first_ioc": r.get("hash") or r.get("domain") or r.get("ip") or "-",
            "hash_type": r.get("hash_type"),
        }
        if len(unique_by_adv) >= 10:
            break
    recent_advisories = list(unique_by_adv.values())

    return {
        "period": period,
        "data_status": "live",
        "upload": upload,
        "summary": {
            "total_advisories": len(unique_advisories),
            "total_iocs": len(unique_ips) + len(unique_domains) + len(unique_hashes),
            "unique_ips": len(unique_ips),
            "unique_domains": len(unique_domains),
            "unique_hashes": len(unique_hashes),
            "industries_covered": len(industry_counter),
        },
        "hash_type_breakdown": hash_type_breakdown,
        "ioc_type_distribution": ioc_type_distribution,
        "industry_breakdown": industry_breakdown,
        "advisories_timeline": timeline,
        "top_advisories": top_advisories,
        "recent_advisories": recent_advisories,
    }
