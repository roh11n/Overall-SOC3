"""IRIS — Intelligent Response & Insight System.

A grounded conversational co-pilot for the MSSP SOC dashboard. Every user
message is answered by a local HuggingFace SmolLM instance with the current
tenant's live KPI snapshot injected as grounding context — the model never
answers on unbacked knowledge.

Design principles:
- Grounded: every prompt carries a compact JSON KPI snapshot for the tenant.
- Bounded: the LLM is instructed to say "I don't have that in the current
  snapshot" when a question falls outside the available data.
- Fast fallback: if the HF model isn't loaded (e.g., cold start), we fall back
  to a deterministic KPI-lookup answer so the copilot always responds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import llm as llm_mod
import tenants as tenants_mod

logger = logging.getLogger("mssp-soc.iris")


IRIS_SYSTEM_PROMPT = (
    "You are IRIS (Intelligent Response & Insight System), the AI co-pilot "
    "for a managed security service provider's SOC KPI dashboard. You answer "
    "the analyst's questions ONLY from the JSON KPI snapshot provided below. "
    "Rules:\n"
    "1. Never invent numbers not present in the snapshot.\n"
    "2. Be concise — 2 to 4 sentences, plain language, no markdown headers.\n"
    "3. Reference specific KPI values when you can (e.g., 'MTTR is 60.7h').\n"
    "4. If the answer isn't in the snapshot, say so and suggest which "
    "dashboard tab would show it.\n"
    "5. When helpful, add one MITRE ATT&CK tactic reference.\n"
    "You are speaking to a SOC manager / executive — be crisp, operationally "
    "useful, cybersecurity-fluent."
)


# ---------------------------------------------------------------------------
# Snapshot builders
# ---------------------------------------------------------------------------

def build_snapshot(period: str, tenant: dict, live_xsoar: Optional[dict] = None) -> dict:
    """Compact KPI snapshot the LLM is grounded on — small, dense, high-signal."""
    ex = tenants_mod.executive_overview(period, tenant)
    soc = tenants_mod.soc_manager(period, tenant)
    det = tenants_mod.detection_engineering(period, tenant)
    ti = tenants_mod.threat_intelligence(period, tenant)
    soar = tenants_mod.soar_automation(period, tenant)
    cli = tenants_mod.client_executive(period, tenant)

    top_actors = [a["name"] for a in ti["landscape"]["threat_actors"][:5]]
    top_malware = [m["family"] for m in ti["landscape"]["malware_families"][:5]]
    top_playbooks = [
        {"name": p["name"], "runs": p["executions"], "success": p["success_rate"]}
        for p in soar["playbooks"][:5]
    ]
    severity = {s["severity"]: s["count"] for s in soc["detection_health"]["severity_distribution"]}
    coverage_by_tactic = {t["tactic"]: t["coverage"] for t in det["mitre_heatmap"]}

    return {
        "tenant": {
            "id": tenant.get("id", "all"),
            "name": tenant.get("name", "All Tenants"),
            "domain": tenant.get("domain", "ALL"),
        },
        "period": period,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "executive": {
            "health_score": ex["health_score"],
            "risk_score": ex["risk_score"],
            "sla_compliance_pct": ex["sla_compliance"],
            "mttr_hours": ex["mttr_hours"],
            "detection_coverage_pct": ex["detection_coverage"],
            "automation_rate_pct": ex["automation_rate"],
            "top_threat_actor": ex.get("top_threat_actor"),
            "advisories": ex.get("advisories"),
            "incidents": ex.get("incidents"),
            "offenses": ex.get("offenses"),
        },
        "speed": soc["speed_metrics"],
        "incident_ops": soc["incident_ops"],
        "severity_distribution": severity,
        "mitre_coverage_by_tactic": coverage_by_tactic,
        "mitre_gap": det["gap_analysis"],
        "threat_landscape": {
            "top_actors": top_actors,
            "top_malware_families": top_malware,
            "total_advisories": ti["landscape"]["total_advisories"],
            "critical_cves": ti["landscape"]["critical_cves"],
            "new_cves": ti["landscape"]["new_cves"],
            "ioc_volume": ti["landscape"]["ioc_volume"],
        },
        "soar": {
            "hours_saved": soar["efficiency"]["hours_saved"],
            "automation_rate_pct": soar["health"]["automation_rate"],
            "automation_roi_pct": soar["efficiency"]["automation_roi_pct"],
            "top_playbooks": top_playbooks,
        },
        "client_scorecard": cli.get("scorecard", {}),
        "live_xsoar": live_xsoar or {"data_status": "empty"},
    }


# ---------------------------------------------------------------------------
# Fallback (rule-based) answers — used when the HF model isn't ready yet
# ---------------------------------------------------------------------------

def _fallback_answer(question: str, snap: dict) -> str:
    """Deterministic keyword-driven answer built directly from the snapshot."""
    q = (question or "").lower()
    ex = snap["executive"]
    soc = snap["speed"]

    # Live XSOAR questions (rule FP rates / noisiest rules) take priority.
    live = snap.get("live_xsoar") or {}
    if live.get("data_status") == "live":
        nr = live.get("noisy_rules_by_fp") or []
        if nr and any(k in q for k in ("fp", "false positive", "false-positive", "noisy", "noisiest", "highest fp")):
            t = nr[0]
            extra = ", ".join(f"{x['rule']} {x['fp_pct']}%" for x in nr[1:3])
            tail = f" Next: {extra}." if extra else ""
            return (
                f"Highest false-positive rate (live XSOAR): '{t['rule']}' at {t['fp_pct']}% "
                f"({t['fp']} FPs of {t['total']} incidents).{tail} Consider tuning or suppression — "
                f"noisy rules erode analyst trust (maps to detection engineering hygiene)."
            )
        tr = live.get("top_rules") or []
        if tr and any(k in q for k in ("rule", "trigger", "most fired", "top rule")):
            t = tr[0]
            return (
                f"Most-triggered rule (live XSOAR): '{t['rule']}' with {t['triggers']} incidents. "
                f"Review it against MITRE ATT&CK mapping to confirm it is high-fidelity."
            )

    def _pct(v):
        return f"{v}%"

    if any(k in q for k in ("mttr", "resolve", "resolution time")):
        return (
            f"MTTR is {ex['mttr_hours']}h this cycle for {snap['tenant']['name']}. "
            f"Queue time ({soc.get('queue_time_min')} min) is the biggest sub-driver — "
            f"auto-enrichment at incident creation typically compresses MTTR 15-25%."
        )
    if any(k in q for k in ("mttd", "detect", "detection time")):
        return (
            f"MTTD is {soc.get('mttd_min')} min. Peer benchmark is ~12 min, so "
            f"detection is {'inside' if soc.get('mttd_min', 0) <= 12 else 'above'} target."
        )
    if any(k in q for k in ("sla", "compliance")):
        return (
            f"SLA compliance is {_pct(ex['sla_compliance_pct'])} against the 95% contractual target — "
            f"{'above' if ex['sla_compliance_pct'] >= 95 else 'below'} target this cycle."
        )
    if any(k in q for k in ("coverage", "mitre", "att&ck", "attack")):
        gap = snap["mitre_gap"]
        return (
            f"MITRE ATT&CK coverage is {_pct(ex['detection_coverage_pct'])} — "
            f"{gap['techniques_covered']} covered, {gap['techniques_missing']} missing. "
            f"Top opportunity: {gap['new_opportunities'][0] if gap['new_opportunities'] else 'n/a'}."
        )
    if any(k in q for k in ("automation", "playbook", "soar")):
        return (
            f"Automation rate is {_pct(snap['soar']['automation_rate_pct'])} with "
            f"{snap['soar']['hours_saved']} analyst hours saved and "
            f"{_pct(snap['soar']['automation_roi_pct'])} ROI. Top playbook: "
            f"{snap['soar']['top_playbooks'][0]['name'] if snap['soar']['top_playbooks'] else 'n/a'}."
        )
    if any(k in q for k in ("actor", "threat", "adversary", "apt", "ransomware")):
        actors = ", ".join(snap["threat_landscape"]["top_actors"][:3])
        return (
            f"Top active actors this cycle: {actors}. "
            f"Ransomware-heavy malware mix — Critical CVEs: {snap['threat_landscape']['critical_cves']}."
        )
    if any(k in q for k in ("risk", "score", "posture")):
        return (
            f"Composite risk score is {ex['risk_score']} (lower is better). "
            f"SOC health score is {ex['health_score']}. "
            f"Watch on {ex['top_threat_actor']} activity."
        )
    if any(k in q for k in ("incident", "offense", "volume")):
        io = snap["incident_ops"]
        return (
            f"This cycle: {io.get('total_offenses')} QRadar offenses converting to "
            f"{io.get('total_incidents')} XSOAR incidents ({io.get('conversion_rate')}%). "
            f"Backlog aging: {io.get('backlog_aging_days')}d."
        )
    if any(k in q for k in ("severity", "critical", "high")):
        sev = snap["severity_distribution"]
        return (
            "Severity mix — "
            + ", ".join(f"{k}: {v}" for k, v in sev.items())
            + "."
        )
    # Default: give the executive snapshot
    return (
        f"Snapshot for {snap['tenant']['name']} ({snap['period']}): "
        f"health {ex['health_score']}, risk {ex['risk_score']}, "
        f"SLA {ex['sla_compliance_pct']}%, MTTR {ex['mttr_hours']}h, "
        f"coverage {ex['detection_coverage_pct']}%, automation {ex['automation_rate_pct']}%. "
        f"Ask about MTTR, MITRE coverage, automation, or a specific threat actor."
    )


# ---------------------------------------------------------------------------
# LLM answer with grounded snapshot
# ---------------------------------------------------------------------------

def _llm_answer(question: str, snap: dict, history: list) -> Optional[str]:
    import json as _json

    if not llm_mod.is_ready():
        return None
    try:
        snapshot_json = _json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
        # Trim very long snapshots to keep the prompt compact.
        if len(snapshot_json) > 6000:
            snapshot_json = snapshot_json[:6000] + "…}"

        messages = [
            {"role": "system", "content": IRIS_SYSTEM_PROMPT},
            {
                "role": "system",
                "content": f"CURRENT KPI SNAPSHOT (JSON):\n{snapshot_json}",
            },
        ]
        # last 4 turns of history for continuity
        for h in history[-8:]:
            role = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": question})

        return llm_mod.chat(messages, max_new_tokens=220, temperature=0.5)
    except Exception:
        logger.exception("IRIS LLM answer failed")
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def answer(question: str, period: str, tenant: dict, history: list, live_xsoar: Optional[dict] = None) -> dict:
    """Answer a user question grounded on the tenant's live KPI snapshot."""
    snap = build_snapshot(period, tenant, live_xsoar)
    llm_status = llm_mod.status()

    llm_text = _llm_answer(question, snap, history) if llm_status["loaded"] else None
    if llm_text and len(llm_text) > 3:
        return {
            "answer": llm_text,
            "source": "hf-llm",
            "model": llm_status["model"],
            "snapshot_period": period,
            "tenant_name": snap["tenant"]["name"],
        }
    # Fallback keeps the copilot useful even during model warm-up.
    return {
        "answer": _fallback_answer(question, snap),
        "source": "rule",
        "model": llm_status["model"],
        "snapshot_period": period,
        "tenant_name": snap["tenant"]["name"],
    }


SUGGESTED_QUESTIONS = [
    "How is our MTTR trending this cycle?",
    "Which rule has the highest false-positive rate?",
    "Where are the biggest MITRE ATT&CK coverage gaps?",
    "Which threat actors are most active right now?",
    "What's driving the SLA breach risk?",
    "Which playbooks give us the best automation ROI?",
]
