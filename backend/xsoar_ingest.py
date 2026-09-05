"""XSOAR incident ingestion + KPI derivation.

Persists uploaded XSOAR CSV/XLSX rows to `db.xsoar_rows` (one document per
incident, keyed by tenant + upload_id) and computes SOC Manager / SOAR /
Executive dashboard KPIs directly from that data.

Design mirrors ti_ingest.py:
- Uploading replaces prior rows for the tenant (batch semantics)
- When no data has been uploaded, dashboards report `data_status: "empty"`
- Column names may vary between XSOAR exports; we normalise a curated set
"""
from __future__ import annotations

import io
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# --- column normalisation ------------------------------------------------

_CANONICAL_COLS = {
    "id": "id", "event id": "event_id", "name": "name",
    "type": "type", "severity": "severity",
    "analystseverity": "analyst_severity", "analyst severity": "analyst_severity",
    "finalseverity": "final_severity", "initialseverity": "initial_severity",
    "status": "status", "owner": "owner",
    "playbookid": "playbook_id", "playbook id": "playbook_id",
    "occurred": "occurred", "closed": "closed", "closereason": "close_reason",
    "created": "created", "created date": "created", "created time": "created",
    "creation date": "created", "incident created date": "created",
    "detected": "detected", "detected date": "detected",
    "detection date": "detected", "detection time": "detected",
    "final severity": "final_severity", "initial severity": "initial_severity",
    "close reason": "close_reason", "closenotes": "close_notes",
    "actual time taken": "time_taken_sec",
    "ticket number": "ticket_number", "ticket opened date": "ticket_opened",
    "ticket acknowledged date": "ticket_acknowledged",
    "ticket resolution date": "ticket_resolved",
    "ticket closed date": "ticket_closed",
    "tenant name": "tenant_name", "log source": "log_source",
    "rule name": "rule_name",
    "mitre tactic name": "mitre_tactic",
    "mitre technique name": "mitre_technique",
    "sla breached": "sla_breached",
    "time to acknowledge": "time_to_ack",
    "time to assignment": "time_to_assign",
    "category": "category", "alert category": "alert_category",
    "auto close": "auto_close",
    "completed task count": "tasks_completed",
    "remaining task count": "tasks_remaining",
    "playbooks failed commands": "failed_commands",
    "playbook names with failed tasks": "failed_playbooks",
    "openduration": "open_duration_sec", "open duration": "open_duration_sec",
    "threat actor": "threat_actor",
    "malware family": "malware_family",
    "malware name": "malware_name",
    "threat family name": "threat_family",
    "cve": "cve", "cve id": "cve_id", "cve list": "cve_list",
    "source ip": "source_ip", "destination ip": "destination_ip",
    "assignment group": "assignment_group",
    "part of campaign": "part_of_campaign",
    "campaign name": "campaign_name",
}


def _norm_col(c: str) -> str:
    key = re.sub(r"\s+", " ", str(c).strip().lower())
    return _CANONICAL_COLS.get(key, "extra_" + re.sub(r"[^a-z0-9_]+", "_", key))


def _clean(v):
    if v is None: return None
    if isinstance(v, float) and pd.isna(v): return None
    s = str(v).strip()
    return s or None


def _parse_dt(v) -> Optional[str]:
    """Parse dates in RFC 2822 or ISO format → ISO string."""
    if not v or (isinstance(v, float) and pd.isna(v)): return None
    try:
        ts = pd.to_datetime(v, errors="coerce", utc=True)
        if pd.isna(ts): return None
        return ts.isoformat()
    except Exception:
        return None


def _to_seconds(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _bool_ish(v) -> Optional[bool]:
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in {"true", "1", "1.0", "yes", "y", "t"}: return True
    if s in {"false", "0", "0.0", "no", "n", "f"}: return False
    return None


def parse_rows(contents: bytes, filename: str) -> List[Dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents), low_memory=False)
    else:
        df = pd.read_excel(io.BytesIO(contents))

    df.columns = [_norm_col(c) for c in df.columns]
    # Drop duplicate normalized columns (keep first) so row.get(col) always
    # returns a scalar — duplicate labels otherwise return a Series and break
    # boolean/date handling (ValueError: truth value of a Series is ambiguous).
    df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        raw_occurred = _parse_dt(r.get("occurred"))
        raw_ticket_opened = _parse_dt(r.get("ticket_opened"))
        occurred_iso = raw_occurred or raw_ticket_opened
        closed_iso = _parse_dt(r.get("closed") or r.get("ticket_closed"))
        ack_iso = _parse_dt(r.get("ticket_acknowledged"))
        resolved_iso = _parse_dt(r.get("ticket_resolved"))
        # Detection/creation timestamp for MTTD (never falls back to occurred)
        detect_iso = _parse_dt(r.get("created") or r.get("detected")) or raw_ticket_opened

        # MTTR seconds — prefer the explicit "Actual Time Taken" handling-time
        # column (real work time) over wall-clock occurred→closed, which
        # otherwise inflates MTTR with nights/weekends the incident sat idle.
        mttr_sec = _to_seconds(r.get("time_taken_sec"))
        if mttr_sec is not None and mttr_sec < 0:
            mttr_sec = None
        if mttr_sec is None and occurred_iso and closed_iso:
            try:
                mttr_sec = (pd.to_datetime(closed_iso) - pd.to_datetime(occurred_iso)).total_seconds()
                if mttr_sec < 0: mttr_sec = None
            except Exception: pass
        # MTTD seconds — time from event occurrence to detection/incident creation
        mttd_sec = None
        if raw_occurred and detect_iso:
            try:
                d = (pd.to_datetime(detect_iso) - pd.to_datetime(raw_occurred)).total_seconds()
                if d >= 0: mttd_sec = d
            except Exception: pass
        # MTTA seconds (kept for compatibility)
        mtta_sec = None
        if occurred_iso and ack_iso:
            try:
                mtta_sec = (pd.to_datetime(ack_iso) - pd.to_datetime(occurred_iso)).total_seconds()
                if mtta_sec < 0: mtta_sec = None
            except Exception: pass

        rec = {
            "incident_id": _clean(r.get("id")),
            "name": _clean(r.get("name")),
            "type": _clean(r.get("type")),
            "severity": _clean(r.get("severity")),
            "analyst_severity": _clean(r.get("analyst_severity")),
            "final_severity": _clean(r.get("final_severity")),
            "initial_severity": _clean(r.get("initial_severity")),
            "status": _clean(r.get("status")),
            "owner": _clean(r.get("owner")),
            "playbook_id": _clean(r.get("playbook_id")),
            "occurred": occurred_iso,
            "closed": closed_iso,
            "close_reason": _clean(r.get("close_reason")),
            "time_taken_sec": _to_seconds(r.get("time_taken_sec")),
            "open_duration_sec": _to_seconds(r.get("open_duration_sec")),
            "mttr_sec": mttr_sec,
            "mttd_sec": mttd_sec,
            "mtta_sec": mtta_sec,
            "tenant_name": _clean(r.get("tenant_name")),
            "log_source": _clean(r.get("log_source")),
            "rule_name": _clean(r.get("rule_name")) or _clean(r.get("name")),
            "mitre_tactic": _clean(r.get("mitre_tactic")),
            "mitre_technique": _clean(r.get("mitre_technique")),
            "sla_breached": _bool_ish(r.get("sla_breached")),
            "auto_close": _bool_ish(r.get("auto_close")),
            "category": _clean(r.get("category")) or _clean(r.get("alert_category")),
            "source_ip": _clean(r.get("source_ip")),
            "destination_ip": _clean(r.get("destination_ip")),
            "assignment_group": _clean(r.get("assignment_group")),
            "threat_actor": _clean(r.get("threat_actor")),
            "malware_family": _clean(r.get("malware_family")) or _clean(r.get("malware_name")) or _clean(r.get("threat_family")),
        }
        # Skip rows with no incident id AND no name — likely header/blank
        if not rec["incident_id"] and not rec["name"]: continue
        rows.append(rec)
    return rows


# --- persistence ---------------------------------------------------------

async def save_upload(db, tenant_id: str, uploaded_by: str, filename: str,
                       rows: List[Dict[str, Any]]) -> str:
    upload_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.xsoar_rows.delete_many({"tenant_id": tenant_id})
    if rows:
        docs = [{**r, "tenant_id": tenant_id, "upload_id": upload_id, "uploaded_at": now} for r in rows]
        # Split into chunks to keep single insert under mongo 16MB doc-batch limit
        for i in range(0, len(docs), 1000):
            await db.xsoar_rows.insert_many(docs[i:i+1000])
    await db.xsoar_uploads.insert_one({
        "upload_id": upload_id, "tenant_id": tenant_id, "filename": filename,
        "row_count": len(rows), "uploaded_by": uploaded_by, "uploaded_at": now,
    })
    return upload_id


async def latest_upload(db, tenant_id: str) -> Optional[dict]:
    return await db.xsoar_uploads.find_one(
        {"tenant_id": tenant_id}, sort=[("uploaded_at", -1)], projection={"_id": 0},
    )


async def _rows(db, tenant_id: str) -> List[dict]:
    return await db.xsoar_rows.find(
        {"tenant_id": tenant_id}, projection={"_id": 0, "tenant_id": 0}
    ).to_list(200000)


# --- KPI helpers ---------------------------------------------------------

def _severity_norm(s: Optional[str]) -> str:
    if not s: return "Unknown"
    s2 = s.strip().lower()
    if s2 in {"critical", "sev-1", "1"}: return "Critical"
    if s2 in {"high", "sev-2", "2"}: return "High"
    if s2 in {"medium", "med", "sev-3", "3"}: return "Medium"
    if s2 in {"low", "sev-4", "4"}: return "Low"
    if s2 in {"informational", "info", "sev-5", "5"}: return "Informational"
    return s.title()


def _avg(values: List[float]) -> float:
    vals = [v for v in values if v is not None]
    if not vals: return 0.0
    return round(sum(vals) / len(vals), 1)


def _median(values: List[float]) -> float:
    """Robust central value for time metrics (MTTR/MTTD/MTTA). The plain mean
    is dominated by a small tail of extreme outliers — incidents whose event
    time predates detection by weeks, or that stay open for days — so we report
    the median, which reflects the typical incident."""
    vals = sorted(v for v in values if v is not None and v >= 0)
    n = len(vals)
    if n == 0: return 0.0
    mid = n // 2
    if n % 2: return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def _pct(num: int, den: int) -> float:
    if den <= 0: return 0.0
    return round(100.0 * num / den, 1)


# Close-reason classification — robust to real-world XSOAR label variants.
_FP_TOKENS = ("false positive", "false-positive", "falsepositive",
              "benign", "not malicious", "no threat", "non-malicious")
_TP_TOKENS = ("true positive", "true-positive", "truepositive",
              "malicious", "confirmed")


def _is_fp(reason) -> bool:
    r = (reason or "").strip().lower()
    if not r:
        return False
    return r in {"fp"} or any(t in r for t in _FP_TOKENS)


def _is_tp(reason) -> bool:
    r = (reason or "").strip().lower()
    if not r:
        return False
    return r in {"tp"} or any(t in r for t in _TP_TOKENS)


def _time_bins(dates: List[str], bucket: str = "day") -> List[Tuple[str, int]]:
    """Return list of (label, count) sorted by label."""
    c: Counter = Counter()
    for d in dates:
        if not d: continue
        try:
            ts = pd.to_datetime(d)
            if bucket == "week":
                y, w, _ = ts.isocalendar()
                label = f"{y}-W{w:02d}"
            elif bucket == "month":
                label = ts.strftime("%Y-%m")
            else:
                label = ts.strftime("%Y-%m-%d")
            c[label] += 1
        except Exception:
            continue
    return sorted(c.items())


# --- SOC Manager dashboard ----------------------------------------------

async def compute_soc_manager(db, tenant_id: str) -> Dict[str, Any]:
    rows = await _rows(db, tenant_id)
    upload = await latest_upload(db, tenant_id)
    if not rows:
        return {"data_status": "empty", "upload": None}

    total = len(rows)
    closed = [r for r in rows if r.get("status") and r["status"].lower() == "closed"]
    open_now = total - len(closed)
    fp = sum(1 for r in rows if _is_fp(r.get("close_reason")))
    tp = sum(1 for r in rows if _is_tp(r.get("close_reason")))
    sla_breached = sum(1 for r in rows if r.get("sla_breached") is True)

    # MTTR/MTTD/MTTA use the median (robust) — the arithmetic mean is skewed
    # by a small tail of extreme-duration incidents. Means kept for reference.
    mttr_hours = round(_median([r.get("mttr_sec") for r in rows]) / 3600.0, 2)
    mttd_min = round(_median([r.get("mttd_sec") for r in rows]) / 60.0, 1)
    mtta_min = round(_median([r.get("mtta_sec") for r in rows]) / 60.0, 1)
    mttr_mean_hours = round(_avg([r.get("mttr_sec") for r in rows]) / 3600.0, 2)
    mttd_mean_min = round(_avg([r.get("mttd_sec") for r in rows]) / 60.0, 1)
    time_taken_min = round(_avg([r.get("time_taken_sec") for r in rows]) / 60.0, 1)
    open_duration_h = round(_avg([r.get("open_duration_sec") for r in rows if (r.get("status") or "").lower() != "closed"]) / 3600.0, 1)

    # Severity mix — read the best-available severity field and keep every
    # standard bucket that has data (Critical was previously dropped).
    def _sev_of(r):
        return _severity_norm(
            r.get("severity") or r.get("final_severity")
            or r.get("analyst_severity") or r.get("initial_severity")
        )
    sev_c: Counter = Counter(_sev_of(r) for r in rows)
    severity_distribution = [
        {"severity": k, "count": sev_c.get(k, 0)}
        for k in ("Critical", "High", "Medium", "Low", "Informational")
        if sev_c.get(k, 0) > 0
    ]

    # Close reason mix
    cr_c: Counter = Counter((r.get("close_reason") or "Unresolved") for r in closed)
    close_reason_mix = [{"reason": k, "count": v} for k, v in cr_c.most_common()]

    # Top rules
    rule_c: Counter = Counter(r.get("rule_name") for r in rows if r.get("rule_name"))
    top_rules = [{"rule": r[:80], "triggers": c} for r, c in rule_c.most_common(10)]

    # Top rules by FP rate (rules with >=5 incidents)
    rule_fp_stats: Dict[str, Dict[str, int]] = {}
    for r in rows:
        rn = r.get("rule_name")
        if not rn: continue
        s = rule_fp_stats.setdefault(rn, {"total": 0, "fp": 0})
        s["total"] += 1
        if _is_fp(r.get("close_reason")):
            s["fp"] += 1
    noisy_rules = sorted(
        [{"rule": k[:80], "total": v["total"], "fp": v["fp"], "fp_pct": _pct(v["fp"], v["total"])}
         for k, v in rule_fp_stats.items() if v["total"] >= 3],
        key=lambda x: (-x["fp_pct"], -x["total"]),
    )[:10]

    # Categories
    cat_c: Counter = Counter(r.get("category") for r in rows if r.get("category"))
    categories = [{"category": k[:60], "count": v} for k, v in cat_c.most_common(8)]

    # Analyst load
    an_c: Counter = Counter(r.get("owner") for r in rows if r.get("owner"))
    analyst_load = [{"analyst": k, "incidents": v} for k, v in an_c.most_common(10)]

    # Incidents timeline (from occurred date)
    tl = _time_bins([r.get("occurred") for r in rows], "day")
    if len(tl) > 45:
        tl = _time_bins([r.get("occurred") for r in rows], "week")
    incidents_timeline = [{"date": d, "value": c} for d, c in tl]

    # MTTR timeline (avg MTTR per day)
    mttr_by_day: Dict[str, List[float]] = {}
    for r in rows:
        occ = r.get("occurred")
        m = r.get("mttr_sec")
        if not occ or m is None: continue
        try:
            key = pd.to_datetime(occ).strftime("%Y-%m-%d")
            mttr_by_day.setdefault(key, []).append(m)
        except Exception: pass
    mttr_trend = [{"date": k, "value": round(sum(v) / len(v) / 3600.0, 2)}
                  for k, v in sorted(mttr_by_day.items())]
    if len(mttr_trend) > 45:
        mttr_trend = mttr_trend[-45:]

    return {
        "data_status": "live",
        "upload": upload,
        "summary": {
            "total_incidents": total,
            "closed": len(closed),
            "open": open_now,
            "false_positive_rate": _pct(fp, len(closed)),
            "true_positive_rate": _pct(tp, len(closed)),
            "sla_breach_rate": _pct(sla_breached, total),
            "sla_compliance_pct": round(100.0 - _pct(sla_breached, total), 1),
            "mttr_hours": mttr_hours,
            "mttd_minutes": mttd_min,
            "mtta_minutes": mtta_min,
            "mttr_mean_hours": mttr_mean_hours,
            "mttd_mean_minutes": mttd_mean_min,
            "avg_time_taken_min": time_taken_min,
            "backlog_open": open_now,
            "backlog_aging_hours": open_duration_h,
        },
        "severity_distribution": severity_distribution,
        "close_reason_mix": close_reason_mix,
        "top_rules": top_rules,
        "noisy_rules": noisy_rules,
        "categories": categories,
        "analyst_load": analyst_load,
        "incidents_timeline": incidents_timeline,
        "mttr_trend": mttr_trend,
    }


# --- SOAR / Automation dashboard ----------------------------------------

async def compute_soar(db, tenant_id: str, avg_manual_min: float = 30.0) -> Dict[str, Any]:
    rows = await _rows(db, tenant_id)
    upload = await latest_upload(db, tenant_id)
    if not rows:
        return {"data_status": "empty", "upload": None}

    total = len(rows)
    with_pb = [r for r in rows if r.get("playbook_id")]
    auto_closed = [r for r in rows if r.get("auto_close") is True]
    closed_rows = [r for r in rows if (r.get("status") or "").lower() == "closed"]

    pb_c: Counter = Counter(r["playbook_id"] for r in with_pb)
    # Per-playbook stats: total runs, closed, auto-closed, avg runtime
    pb_stats: Dict[str, Dict[str, Any]] = {}
    for r in with_pb:
        pid = r["playbook_id"]
        s = pb_stats.setdefault(pid, {"name": pid, "executions": 0, "closed": 0, "auto": 0, "runtimes": []})
        s["executions"] += 1
        if (r.get("status") or "").lower() == "closed": s["closed"] += 1
        if r.get("auto_close") is True: s["auto"] += 1
        if r.get("time_taken_sec") is not None:
            s["runtimes"].append(r["time_taken_sec"])

    playbooks = []
    for pid, s in pb_stats.items():
        avg_rt = round(sum(s["runtimes"]) / len(s["runtimes"]), 1) if s["runtimes"] else 0.0
        playbooks.append({
            "name": pid[:70],
            "executions": s["executions"],
            "closed": s["closed"],
            "auto_closed": s["auto"],
            "success_rate": _pct(s["closed"], s["executions"]),
            "auto_close_rate": _pct(s["auto"], s["executions"]),
            "avg_runtime_sec": avg_rt,
        })
    playbooks.sort(key=lambda x: x["executions"], reverse=True)

    # Executions timeline
    ex_tl = _time_bins([r.get("occurred") for r in with_pb], "day")
    if len(ex_tl) > 45: ex_tl = _time_bins([r.get("occurred") for r in with_pb], "week")
    executions_timeline = [{"date": d, "value": c} for d, c in ex_tl]

    # Automation rate timeline (daily)
    per_day_total: Counter = Counter()
    per_day_auto: Counter = Counter()
    for r in rows:
        occ = r.get("occurred")
        if not occ: continue
        try: key = pd.to_datetime(occ).strftime("%Y-%m-%d")
        except Exception: continue
        per_day_total[key] += 1
        if r.get("auto_close") is True: per_day_auto[key] += 1
    auto_trend = [{"date": k, "value": _pct(per_day_auto.get(k, 0), per_day_total[k])}
                  for k in sorted(per_day_total.keys())]
    if len(auto_trend) > 45: auto_trend = auto_trend[-45:]

    hours_saved = round(len(auto_closed) * avg_manual_min / 60.0, 1)
    automation_rate = _pct(len(auto_closed), total)
    success_rate = _pct(len(closed_rows), total)

    return {
        "data_status": "live",
        "upload": upload,
        "health": {
            "automation_rate": automation_rate,
            "success_rate": success_rate,
            "playbooks_executed": len(with_pb),
            "unique_playbooks": len(pb_stats),
            "failed_automations": len(with_pb) - sum(s["closed"] for s in pb_stats.values()),
            "avg_manual_min_baseline": avg_manual_min,
        },
        "efficiency": {
            "auto_closures": len(auto_closed),
            "manual_closures": len(closed_rows) - len(auto_closed),
            "hours_saved": hours_saved,
            "automation_roi_pct": round(hours_saved / max(1, total * avg_manual_min / 60.0) * 100.0, 1),
        },
        "playbooks": playbooks[:15],
        "automation_trend": auto_trend,
        "executions_timeline": executions_timeline,
    }


# --- Executive Overview roll-up -----------------------------------------

async def compute_executive_rollup(db, tenant_id: str) -> Dict[str, Any]:
    """Roll up MTTR / SLA / Automation / Incidents / top-rule from XSOAR.

    Returns partial exec KPIs that the caller can merge with mock/other
    persona data (Threat Intel, MITRE coverage, etc.).
    """
    rows = await _rows(db, tenant_id)
    upload = await latest_upload(db, tenant_id)
    if not rows:
        return {"data_status": "empty"}

    total = len(rows)
    closed = [r for r in rows if (r.get("status") or "").lower() == "closed"]
    fp = sum(1 for r in rows if _is_fp(r.get("close_reason")))
    sla_breached = sum(1 for r in rows if r.get("sla_breached") is True)
    auto_closed = sum(1 for r in rows if r.get("auto_close") is True)

    mttr_h = round(_avg([r.get("mttr_sec") for r in rows]) / 3600.0, 2)
    sla_compliance = round(100.0 - _pct(sla_breached, total), 1)
    automation_rate = _pct(auto_closed, total)

    rule_c: Counter = Counter(r.get("rule_name") for r in rows if r.get("rule_name"))
    top_rule = rule_c.most_common(1)
    top_rule_name = top_rule[0][0][:80] if top_rule else None

    tactic_c: Counter = Counter(r.get("mitre_tactic") for r in rows if r.get("mitre_tactic"))
    top_tactic = tactic_c.most_common(1)[0][0] if tactic_c else None

    # Incident volume trend (last 30 buckets)
    tl = _time_bins([r.get("occurred") for r in rows], "day")
    if len(tl) > 30: tl = tl[-30:]
    incident_trend = [{"date": d, "value": c} for d, c in tl]

    sla_by_day: Dict[str, Dict[str, int]] = {}
    for r in rows:
        occ = r.get("occurred")
        if not occ: continue
        try: key = pd.to_datetime(occ).strftime("%Y-%m-%d")
        except Exception: continue
        s = sla_by_day.setdefault(key, {"total": 0, "ok": 0})
        s["total"] += 1
        if r.get("sla_breached") is not True: s["ok"] += 1
    sla_trend = [{"date": k, "value": _pct(v["ok"], v["total"])}
                 for k, v in sorted(sla_by_day.items())][-30:]

    return {
        "data_status": "live",
        "upload": upload,
        "incidents": total,
        "mttr_hours": mttr_h,
        "sla_compliance": sla_compliance,
        "automation_rate": automation_rate,
        "false_positive_rate": _pct(fp, len(closed)),
        "top_rule": top_rule_name,
        "top_mitre_tactic": top_tactic,
        "incident_trend": incident_trend,
        "sla_trend": sla_trend,
    }



# --- Detection Engineering overlay (MITRE heatmap + rule effectiveness) --

# 14 MITRE ATT&CK Enterprise tactics — used to express live tactic coverage %.
_MITRE_TACTICS_TOTAL = 14


async def compute_detection_overlay(db, tenant_id: str) -> Dict[str, Any]:
    """Derive the MITRE ATT&CK heat-map and rule-effectiveness KPIs directly
    from uploaded XSOAR incidents (MITRE Tactic Name / MITRE Technique Name +
    rule name + close reason). Returns data_status='empty' when nothing useful
    can be built so the caller keeps the mock payload."""
    rows = await _rows(db, tenant_id)
    upload = await latest_upload(db, tenant_id)
    if not rows:
        return {"data_status": "empty"}

    # ---- Heat-map: tactic -> technique -> hit count ----
    tactic_map: Dict[str, Counter] = {}
    for r in rows:
        tac = r.get("mitre_tactic")
        if not tac:
            continue
        tech = r.get("mitre_technique") or "Unspecified technique"
        tactic_map.setdefault(tac, Counter())[tech] += 1

    mitre_heatmap: List[Dict[str, Any]] = []
    if tactic_map:
        tactic_totals = {t: sum(c.values()) for t, c in tactic_map.items()}
        max_total = max(tactic_totals.values()) or 1
        for tac, techc in sorted(tactic_map.items(), key=lambda kv: -tactic_totals[kv[0]]):
            techniques = [
                {"name": (name or "Unspecified")[:42], "covered": True, "hits": hits}
                for name, hits in techc.most_common(8)
            ]
            mitre_heatmap.append({
                "tactic": tac[:34],
                "coverage": round(100.0 * tactic_totals[tac] / max_total),
                "techniques": techniques,
            })

    distinct_techniques = len({r.get("mitre_technique") for r in rows if r.get("mitre_technique")})
    distinct_tactics = len(tactic_map)

    # ---- Rule effectiveness from rule_name + close_reason ----
    rule_stats: Dict[str, Dict[str, int]] = {}
    for r in rows:
        rn = r.get("rule_name")
        if not rn:
            continue
        s = rule_stats.setdefault(rn, {"total": 0, "fp": 0, "tp": 0})
        s["total"] += 1
        cr = r.get("close_reason")
        if _is_fp(cr):
            s["fp"] += 1
        elif _is_tp(cr):
            s["tp"] += 1

    rules: List[Dict[str, Any]] = []
    for rn, s in rule_stats.items():
        fp_rate = _pct(s["fp"], s["total"])
        tp_fp = s["tp"] + s["fp"]
        precision = round(s["tp"] / tp_fp, 2) if tp_fp > 0 else None
        recall = round(s["tp"] / s["total"], 2) if s["total"] > 0 else None
        status = "tuning" if fp_rate >= 40 else ("active" if s["total"] >= 3 else "monitoring")
        rules.append({
            "name": rn[:80], "status": status, "triggers": s["total"],
            "true_positives": s["tp"], "fp_rate": fp_rate,
            "precision": precision, "recall": recall,
        })
    rules.sort(key=lambda x: -x["triggers"])
    rules = rules[:16]

    # Rules ranked by FP rate (min 3 incidents) — reused by IRIS.
    noisy_rules = sorted(
        [{"rule": r["name"], "total": r["triggers"], "fp": int(round(r["fp_rate"] * r["triggers"] / 100.0)),
          "fp_pct": r["fp_rate"]} for r in rules if r["triggers"] >= 3],
        key=lambda x: (-x["fp_pct"], -x["total"]),
    )[:10]

    return {
        "data_status": "live",
        "upload": upload,
        "mitre_heatmap": mitre_heatmap,
        "rules": rules,
        "noisy_rules": noisy_rules,
        "techniques_covered": distinct_techniques,
        "distinct_tactics": distinct_tactics,
        "mitre_coverage": round(100.0 * distinct_tactics / _MITRE_TACTICS_TOTAL, 1),
    }



# --- Client Executive dashboard (live from XSOAR) -----------------------

async def compute_client(db, tenant_id: str) -> Dict[str, Any]:
    """Client-facing business-risk view derived from XSOAR incidents."""
    rows = await _rows(db, tenant_id)
    upload = await latest_upload(db, tenant_id)
    if not rows:
        return {"data_status": "empty", "upload": None}

    total = len(rows)
    closed = [r for r in rows if (r.get("status") or "").lower() == "closed"]
    fp = sum(1 for r in rows if _is_fp(r.get("close_reason")))
    sla_breached = sum(1 for r in rows if r.get("sla_breached") is True)
    major = sum(1 for r in rows if _severity_norm(r.get("severity")) in ("Critical", "High"))
    open_critical = sum(1 for r in rows if (r.get("status") or "").lower() != "closed"
                        and _severity_norm(r.get("severity")) == "Critical")
    mttr_h = round(_avg([r.get("mttr_sec") for r in rows]) / 3600.0, 2)
    sla = round(100.0 - _pct(sla_breached, total), 1)
    fp_rate = _pct(fp, len(closed))
    breach_rate = _pct(sla_breached, total)
    composite = round(min(100.0, fp_rate * 0.4 + breach_rate * 0.6), 1)

    dest = Counter(r.get("destination_ip") for r in rows if r.get("destination_ip"))
    top_assets = [{"asset": (k or "")[:24], "hits": v} for k, v in dest.most_common(6)]
    src = Counter(r.get("source_ip") for r in rows if r.get("source_ip"))
    top_sources = [{"country": (k or ""), "count": v} for k, v in src.most_common(7)]
    phishing = sum(1 for r in rows if "phish" in (r.get("category") or "").lower())

    # Daily trend buckets
    by_day: Dict[str, Dict[str, int]] = {}
    for r in rows:
        occ = r.get("occurred")
        if not occ:
            continue
        try:
            key = pd.to_datetime(occ).strftime("%Y-%m-%d")
        except Exception:
            continue
        s = by_day.setdefault(key, {"total": 0, "ok": 0, "auto": 0, "fp": 0})
        s["total"] += 1
        if r.get("sla_breached") is not True:
            s["ok"] += 1
        if r.get("auto_close") is True:
            s["auto"] += 1
        if _is_fp(r.get("close_reason")):
            s["fp"] += 1
    days = sorted(by_day.keys())[-30:]
    sla_trend = [{"date": d, "value": _pct(by_day[d]["ok"], by_day[d]["total"])} for d in days]
    auto_trend = [{"date": d, "value": _pct(by_day[d]["auto"], by_day[d]["total"])} for d in days]
    fp_trend = [{"date": d, "value": _pct(by_day[d]["fp"], by_day[d]["total"])} for d in days]

    # Repeat incidents = duplicate occurrences of the same incident name/rule
    name_counts = Counter(
        (r.get("name") or r.get("rule_name") or "").strip().lower()
        for r in rows if (r.get("name") or r.get("rule_name"))
    )
    repeat_incidents = sum(c - 1 for c in name_counts.values() if c > 1)

    # Period-over-period deltas (latest vs previous month present in the data)
    by_month: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        occ = r.get("occurred")
        if not occ:
            continue
        try:
            mk = pd.to_datetime(occ).strftime("%Y-%m")
        except Exception:
            continue
        m = by_month.setdefault(mk, {"count": 0, "mttr": [], "ok": 0})
        m["count"] += 1
        if r.get("mttr_sec") is not None:
            m["mttr"].append(r.get("mttr_sec"))
        if r.get("sla_breached") is not True:
            m["ok"] += 1
    yoy_inc = yoy_mttr = yoy_sla = 0.0
    months = sorted(by_month.keys())
    if len(months) >= 2:
        cur, prev = by_month[months[-1]], by_month[months[-2]]
        yoy_inc = _pct(cur["count"] - prev["count"], prev["count"]) if prev["count"] else 0.0
        cur_m = round(_avg(cur["mttr"]) / 3600.0, 2)
        prev_m = round(_avg(prev["mttr"]) / 3600.0, 2)
        yoy_mttr = _pct(cur_m - prev_m, prev_m) if prev_m else 0.0
        cur_sla = _pct(cur["ok"], cur["count"])
        prev_sla = _pct(prev["ok"], prev["count"])
        yoy_sla = round(cur_sla - prev_sla, 1)

    return {
        "data_status": "live",
        "upload": upload,
        "scorecard": {
            "composite_risk_score": composite,
            "client_risk_rank": 1,
            "quarterly_sla": sla,
            "major_p1_p2_incidents": major,
            "yoy_incident_delta": yoy_inc,
            "yoy_mttr_delta": yoy_mttr,
            "yoy_sla_delta": yoy_sla,
        },
        "business_risk": {
            "top_assets": top_assets,
            "top_sources": top_sources,
            "phishing_incidents": phishing,
            "avg_dwell_hours": mttr_h,
            "repeat_incidents": repeat_incidents,
            "open_critical": open_critical,
        },
        "trends": {"sla": sla_trend, "automation": auto_trend, "coverage": [], "fp": fp_trend},
    }


# --- QBR (quarterly business review) aggregates -------------------------

async def compute_qbr(db, tenant_id: str) -> Dict[str, Any]:
    """Aggregates for the QBR-style PPTX: log-source share, alerts-by-month x
    severity, MITRE tactic volumes, and mean-time-to-report by month."""
    rows = await _rows(db, tenant_id)
    if not rows:
        return {"data_status": "empty"}
    total = len(rows)

    def _sev(r):
        return _severity_norm(
            r.get("severity") or r.get("final_severity")
            or r.get("analyst_severity") or r.get("initial_severity")
        )

    # Log-source share of incidents. The XSOAR export often stores log_source
    # as a JSON-array string (e.g. '["Check Point @ x","Custom Rule Engine-3"]');
    # take the primary (first) source per incident so shares sum to ~100%.
    def _primary_source(val):
        if not val:
            return None
        s = str(val).strip()
        if s.startswith("["):
            try:
                import json
                arr = json.loads(s)
                if isinstance(arr, list) and arr:
                    s = str(arr[0])
            except Exception:
                s = s.lstrip("[").split(",")[0].strip().strip('"').strip("'")
        return s.strip().strip('"').strip("'") or None

    ls: Counter = Counter(_primary_source(r.get("log_source")) for r in rows if r.get("log_source"))
    ls.pop(None, None)
    log_sources = [
        {"name": (k or "")[:34], "count": v, "pct": round(100.0 * v / total, 1)}
        for k, v in ls.most_common(10)
    ]

    # Alerts by month x severity + MTTR (minutes) by month
    def _mk(occ):
        try:
            return pd.to_datetime(occ)
        except Exception:
            return None
    month_sev: Dict[str, Counter] = {}
    month_mttr: Dict[str, List[float]] = {}
    for r in rows:
        ts = _mk(r.get("occurred"))
        if ts is None:
            continue
        key = ts.strftime("%b %Y")
        month_sev.setdefault(key, Counter())[_sev(r)] += 1
        if r.get("mttr_sec") is not None:
            month_mttr.setdefault(key, []).append(r["mttr_sec"])
    ordered = sorted(month_sev.keys(), key=lambda m: pd.to_datetime("01 " + m))
    sev_order = ["Critical", "High", "Medium", "Low"]
    alerts_by_month = {
        "months": ordered,
        "series": {s: [month_sev[m].get(s, 0) for m in ordered] for s in sev_order},
    }
    mttr_by_month = [
        {"month": m, "value": round(_median(month_mttr.get(m, [])) / 3600.0, 1)}
        for m in ordered if month_mttr.get(m)
    ]

    # MITRE tactic volumes
    tc: Counter = Counter(r.get("mitre_tactic") for r in rows if r.get("mitre_tactic"))
    tactics = [{"tactic": (k or "")[:28], "count": v} for k, v in tc.most_common(12)]

    mttr_median_hours = round(_median([r.get("mttr_sec") for r in rows]) / 3600.0, 1)
    mttd_median_min = round(_median([r.get("mttd_sec") for r in rows]) / 60.0, 1)

    # Distinct counts for exec tiles
    unique_log_sources = len(ls)
    unique_detections = len({r.get("rule_name") for r in rows if r.get("rule_name")})

    # Tactic x month matrix (for the MITRE heat-map table)
    tactic_month: Dict[str, Counter] = {}
    for r in rows:
        ts = _mk(r.get("occurred"))
        tac = r.get("mitre_tactic")
        if ts is None or not tac:
            continue
        tactic_month.setdefault(tac, Counter())[ts.strftime("%b %Y")] += 1
    tac_totals = sorted(
        ((t, sum(c.values())) for t, c in tactic_month.items()),
        key=lambda x: -x[1],
    )
    table_months = ordered[-6:]
    tactic_table = [
        {"tactic": t,
         "months": {m: tactic_month[t].get(m, 0) for m in table_months},
         "total": sum(tactic_month[t].get(m, 0) for m in table_months)}
        for t, _ in tac_totals[:14]
    ]

    return {
        "data_status": "live",
        "total": total,
        "log_sources": log_sources,
        "alerts_by_month": alerts_by_month,
        "mttr_by_month": mttr_by_month,
        "mttr_median_hours": mttr_median_hours,
        "mttd_median_min": mttd_median_min,
        "tactics": tactics,
        "unique_log_sources": unique_log_sources,
        "unique_detections": unique_detections,
        "table_months": table_months,
        "tactic_table": tactic_table,
    }
