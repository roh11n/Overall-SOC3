"""Detection rule-catalog ingest (rules-testing.xlsx style).

Columns: S.No, Rule Name, Rule ID, Rule UUID, Rule Description,
Applicable Domain, Applicable Log Sources, Excluded Domains,
ATT&CK Tactic, ATT&CK Technique.  Tactics/techniques may be ';'-separated.

Drives Detection Engineering: MITRE coverage heat-map, coverage KPIs, and
rule effectiveness (triggers matched from XSOAR incidents vs the catalog with
an average threshold split).
"""
import io
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger("mssp-soc.rules")

MITRE_TACTICS = [
    "Reconnaissance", "Resource Development", "Initial Access", "Execution",
    "Persistence", "Privilege Escalation", "Defense Evasion", "Credential Access",
    "Discovery", "Lateral Movement", "Collection", "Command and Control",
    "Exfiltration", "Impact",
]
_TACTIC_LOOKUP = {t.lower(): t for t in MITRE_TACTICS}


def _norm_col(c: str) -> str:
    return str(c).strip().lower().replace("att&ck", "attack").replace("  ", " ")


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _split(v) -> List[str]:
    s = _clean(v)
    if not s:
        return []
    parts = [p.strip() for p in s.replace("\n", ";").split(";")]
    return [p for p in parts if p]


def _norm_tactic(t: str) -> str:
    return _TACTIC_LOOKUP.get(t.strip().lower(), t.strip())


def _tech_name(t: str) -> str:
    t = t.strip()
    if " - " in t:
        t = t.split(" - ", 1)[1]
    return t[:44]


def _norm_key(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def parse_rows(contents: bytes, filename: str) -> List[Dict[str, Any]]:
    """Parse the catalog sheet (the one with Rule Name + ATT&CK columns)."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        frames = [pd.read_csv(io.BytesIO(contents))]
    else:
        sheets = pd.read_excel(io.BytesIO(contents), sheet_name=None)
        frames = list(sheets.values())

    for df in frames:
        cols = {_norm_col(c): c for c in df.columns}
        if "rule name" in cols and any(k in cols for k in ("attack tactic", "attack technique")):
            return _rows_from_df(df, cols)
    # Fallback: first frame that has a "rule name" column
    for df in frames:
        cols = {_norm_col(c): c for c in df.columns}
        if "rule name" in cols:
            return _rows_from_df(df, cols)
    return []


def _rows_from_df(df, cols) -> List[Dict[str, Any]]:
    out = []
    for _, r in df.iterrows():
        rule_name = _clean(r.get(cols.get("rule name")))
        if not rule_name:
            continue
        tactics = [_norm_tactic(t) for t in _split(r.get(cols.get("attack tactic")))]
        techniques = [_tech_name(t) for t in _split(r.get(cols.get("attack technique")))]
        out.append({
            "rule_name": rule_name,
            "rule_id": _clean(r.get(cols.get("rule id"))),
            "rule_uuid": _clean(r.get(cols.get("rule uuid"))),
            "description": _clean(r.get(cols.get("rule description"))),
            "applicable_domain": _clean(r.get(cols.get("applicable domain"))),
            "log_sources": _clean(r.get(cols.get("applicable log sources"))),
            "tactics": tactics,
            "techniques": techniques,
        })
    return out


async def save_upload(db, tenant_id: str, filename: str, rows: List[Dict[str, Any]]):
    tid = tenant_id or "all"
    await db.rules_rows.delete_many({"tenant_id": tid})
    if rows:
        await db.rules_rows.insert_many([{**r, "tenant_id": tid} for r in rows])
    await db.rules_uploads.update_one(
        {"tenant_id": tid},
        {"$set": {"tenant_id": tid, "filename": filename, "row_count": len(rows),
                  "uploaded_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return len(rows)


async def latest_upload(db, tenant_id: str):
    return await db.rules_uploads.find_one({"tenant_id": tenant_id or "all"}, {"_id": 0})


async def delete_data(db, tenant_id: str):
    tid = tenant_id or "all"
    await db.rules_rows.delete_many({"tenant_id": tid})
    await db.rules_uploads.delete_many({"tenant_id": tid})


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


async def compute_detection(db, tenant_id: str, xsoar_rows: List[Dict]) -> Dict[str, Any]:
    rows = await db.rules_rows.find({"tenant_id": tenant_id or "all"}, {"_id": 0}).to_list(5000)
    if not rows:
        return {"data_status": "empty"}
    upload = await latest_upload(db, tenant_id)

    # --- Trigger counts: match XSOAR incident rule/name against catalog Rule
    #     Name, Rule ID or Rule UUID (whichever the XSOAR export references).
    trig = Counter()
    for x in xsoar_rows or []:
        seen = set()
        for field in ("rule_name", "name"):
            ident = x.get(field)
            if ident:
                k = _norm_key(ident)
                if k and k not in seen:
                    trig[k] += 1
                    seen.add(k)

    # --- MITRE heat-map + coverage from catalog tactics/techniques
    tactic_rules = Counter()
    tactic_techs: Dict[str, Counter] = {}
    with_attack = with_logsrc = with_desc = 0
    for r in rows:
        if r["tactics"]:
            with_attack += 1
        if r["log_sources"]:
            with_logsrc += 1
        if r["description"]:
            with_desc += 1
        for t in set(r["tactics"]):
            tactic_rules[t] += 1
            tc = tactic_techs.setdefault(t, Counter())
            for tech in r["techniques"]:
                tc[tech] += 1

    max_rules = max(tactic_rules.values()) if tactic_rules else 1

    # Live technique activity from XSOAR incidents → dynamic heat-map hit counts
    # (previously "hits" was a static count of catalog rules per technique).
    live_tech_hits = Counter()
    for x in xsoar_rows or []:
        tech = x.get("mitre_technique")
        if tech:
            live_tech_hits[_norm_key(_tech_name(tech))] += 1

    heatmap = []
    for t in MITRE_TACTICS:
        if t in tactic_rules:
            techs = [{"name": n, "covered": True, "hits": live_tech_hits.get(_norm_key(n), 0)}
                     for n, _ in tactic_techs.get(t, Counter()).most_common(8)]
            heatmap.append({"tactic": t, "coverage": round(100.0 * tactic_rules[t] / max_rules),
                            "techniques": techs})
    distinct_tactics = sum(1 for t in MITRE_TACTICS if t in tactic_rules)
    distinct_techs = len({tech for r in rows for tech in r["techniques"]})

    total = len(rows)
    quality = {
        "detection_coverage": _pct(with_attack, total),
        "use_case_coverage": _pct(with_logsrc, total),
        "mitre_coverage": round(100.0 * distinct_tactics / len(MITRE_TACTICS), 1),
        "atlas_coverage": None,  # ATLAS mapping not present in catalog
        "quality_score": round((_pct(with_desc, total) + _pct(with_attack, total) + _pct(with_logsrc, total)) / 3, 1),
    }

    # --- Rule effectiveness vs average threshold
    per_rule = []
    for r in rows:
        keys = {_norm_key(v) for v in (r["rule_name"], r.get("rule_id"), r.get("rule_uuid")) if v}
        t = max((trig.get(k, 0) for k in keys), default=0)
        per_rule.append({"name": r["rule_name"][:80], "rule_id": r["rule_id"],
                         "triggers": t, "tactics": r["tactics"][:3]})
    triggered = [x for x in per_rule if x["triggers"] > 0]
    avg = round(sum(x["triggers"] for x in triggered) / len(triggered), 1) if triggered else 0.0
    for x in per_rule:
        t = x["triggers"]
        if t == 0:
            x["band"] = "not_triggered"
        elif t > 1.25 * avg:
            x["band"] = "above_avg"
        elif t >= 0.75 * avg:
            x["band"] = "near_avg"
        else:
            x["band"] = "below_avg"
    bands = Counter(x["band"] for x in per_rule)
    per_rule.sort(key=lambda x: -x["triggers"])

    rule_effectiveness = {
        "total_rules": total,
        "triggered_rules": len(triggered),
        "not_triggered_rules": bands.get("not_triggered", 0),
        "avg_triggers": avg,
        "bands": {"above_avg": bands.get("above_avg", 0), "near_avg": bands.get("near_avg", 0),
                  "below_avg": bands.get("below_avg", 0), "not_triggered": bands.get("not_triggered", 0)},
        "rules": per_rule[:60],
    }

    return {
        "data_status": "live",
        "upload": upload,
        "mitre_heatmap": heatmap,
        "quality": quality,
        "techniques_covered": distinct_techs,
        "techniques_missing": 0,
        "rule_effectiveness": rule_effectiveness,
    }
