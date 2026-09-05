"""Cybersecurity-focused recommendation engine.

Analyzes KPI signals and produces contextual, actionable recommendations
for MSSP SOC leadership. Rule-based intelligence engine designed as a drop-in
for a HuggingFace cybersecurity LLM (e.g. CySecBERT/SecureBERT).
"""
from typing import List, Dict


def _tag(priority: str) -> Dict:
    return {
        "P1": {"label": "Critical", "color": "danger"},
        "P2": {"label": "High", "color": "warning"},
        "P3": {"label": "Medium", "color": "primary"},
        "P4": {"label": "Advisory", "color": "success"},
    }[priority]


def generate(exec_data: dict, soc: dict = None, det: dict = None, ti: dict = None, soar: dict = None) -> List[Dict]:
    """Live-data-driven recommendations. Reads only the executive payload so it
    never depends on fabricated mock structures. Returns [] when there is no
    live data to reason over."""
    recs: List[Dict] = []
    if not exec_data or exec_data.get("data_status") != "live":
        return recs

    sla = exec_data.get("sla_compliance") or 0
    mttr = exec_data.get("mttr_hours") or 0
    det_cov = exec_data.get("detection_coverage") or 0
    auto = exec_data.get("automation_rate") or 0
    fp = exec_data.get("false_positive_rate") or 0
    risk = exec_data.get("risk_score") or 0
    inc = exec_data.get("incidents") or 0
    top_rule = exec_data.get("top_rule")
    top_tactic = exec_data.get("top_mitre_tactic")

    # SOC operational recs only make sense when there are incidents in scope.
    if inc and sla < 95:
        recs.append({
            "priority": "P1", "tag": _tag("P1"), "area": "SLA",
            "title": f"SLA compliance at {sla}% — below 95% target",
            "insight": f"Live XSOAR SLA compliance is {sla}%. Breaches are eroding the contractual target.",
            "action": "Re-balance L1 shift coverage and enable auto-escalation after 15 min queue time.",
        })

    if inc and mttr > 60:
        recs.append({
            "priority": "P2", "tag": _tag("P2"), "area": "Speed",
            "title": f"MTTR trending high at {mttr}h",
            "insight": "Mean time to resolve is above the 60h watch-line based on live incident data.",
            "action": "Deploy enrichment playbook (IOC + Asset + Identity) at incident create-time to shave investigation.",
        })

    if fp and fp > 25:
        recs.append({
            "priority": "P2", "tag": _tag("P2"), "area": "Detection",
            "title": f"False-positive rate at {fp}% — tune noisy rules",
            "insight": (f"Noisiest rule: {top_rule}." if top_rule else "Several rules show high false-positive rates."),
            "action": "Tune top high-FP rules with allowlist enrichment; expected 30–40% noise reduction.",
        })

    if det_cov and det_cov < 80:
        recs.append({
            "priority": "P3", "tag": _tag("P3"), "area": "Coverage",
            "title": f"MITRE ATT&CK coverage at {det_cov}% — expand detection surface",
            "insight": (f"Most-active tactic in live data: {top_tactic}." if top_tactic else "Several ATT&CK tactics have no detections yet."),
            "action": "Prioritize the uncovered tactics; ship new detections this sprint.",
        })

    if auto and auto < 70:
        recs.append({
            "priority": "P3", "tag": _tag("P3"), "area": "Automation",
            "title": f"Automation rate at {auto}% — automate top manual flows",
            "insight": "A large share of incidents are still closed manually.",
            "action": "Convert 'Phishing Triage' and 'Failed Login Cooldown' to full auto-remediation.",
        })

    if risk and risk > 40:
        recs.append({
            "priority": "P1", "tag": _tag("P1"), "area": "Risk",
            "title": f"Composite risk elevated ({risk})",
            "insight": f"Health score at {exec_data.get('health_score')}. Driven by FP/SLA/MTTR signals.",
            "action": "Convene weekly risk review; freeze non-critical changes on top assets.",
        })

    if sla >= 97 and auto >= 70:
        recs.append({
            "priority": "P4", "tag": _tag("P4"), "area": "Health",
            "title": "SOC operating within all executive KPIs",
            "insight": f"SLA {sla}% · Automation {auto}% · Coverage {det_cov}%.",
            "action": "Maintain cadence. Reallocate 10% capacity to proactive threat hunting.",
        })

    return recs
