"""Deterministic mock KPI data generator for QRadar / XSOAR / TI sources.

Produces realistic-looking data slices per time period (weekly/monthly/quarterly)
with consistent hashes so repeat calls yield stable numbers.
"""
import random
import hashlib
from datetime import datetime, timezone, timedelta

PERIODS = ("weekly", "monthly", "quarterly")

MITRE_TACTICS = [
    "Initial Access", "Execution", "Persistence", "Privilege Escalation",
    "Defense Evasion", "Credential Access", "Discovery", "Lateral Movement",
    "Collection", "Exfiltration", "Command & Control", "Impact",
]

MITRE_TECHNIQUES = {
    "Initial Access": ["Phishing", "Valid Accounts", "Exploit Public App", "Supply Chain"],
    "Execution": ["Command Line", "PowerShell", "Scheduled Task", "WMI"],
    "Persistence": ["Registry Run", "Scheduled Task", "Startup Folder", "Service"],
    "Privilege Escalation": ["Token Manipulation", "UAC Bypass", "DLL Sideload", "Sudo"],
    "Defense Evasion": ["Obfuscation", "Masquerading", "Rootkit", "Signed Binary"],
    "Credential Access": ["Brute Force", "Kerberoasting", "LSASS Dump", "Password Spray"],
    "Discovery": ["System Info", "Network Scan", "Account Discovery", "File Discovery"],
    "Lateral Movement": ["RDP", "SMB Admin Shares", "SSH", "Pass-the-Hash"],
    "Collection": ["Screen Capture", "Clipboard", "Keylogging", "Archive"],
    "Exfiltration": ["Over C2", "Web Service", "DNS Tunneling", "Removable Media"],
    "Command & Control": ["HTTP/S", "DNS", "Proxy", "Encrypted Channel"],
    "Impact": ["Ransomware", "Data Wipe", "Defacement", "Resource Hijack"],
}

THREAT_ACTORS = [
    ("Lazarus Group", "North Korea", 42),
    ("APT29 (Cozy Bear)", "Russia", 38),
    ("FIN7", "Financial", 31),
    ("Scattered Spider", "Cybercrime", 28),
    ("APT41", "China", 24),
    ("Kimsuky", "North Korea", 19),
    ("Lockbit", "Ransomware", 47),
    ("BlackCat/ALPHV", "Ransomware", 33),
]

MALWARE_FAMILIES = [
    ("Emotet", 89), ("Cobalt Strike", 76), ("QakBot", 64), ("IcedID", 52),
    ("Mimikatz", 45), ("Lockbit 3.0", 41), ("Rhysida", 28), ("Akira", 22),
]

RULE_NAMES = [
    "Suspicious PowerShell Encoded Command", "Impossible Travel Login",
    "Multiple Failed Logins From Same IP", "Kerberoast Attempt Detected",
    "Rare Process Execution", "Outbound Data Exfil > 100MB",
    "Malicious IOC Match (Threat Feed)", "New Admin Account Created",
    "Cleartext Credential in Process Args", "Sensitive File Access After Hours",
    "DNS Tunneling Pattern", "LSASS Memory Access",
    "Service Installed With Unusual Path", "Ransomware Extension Rename",
    "Beacon-like Periodic Callout", "Web Shell Upload Detected",
]

PLAYBOOKS = [
    ("Phishing Triage & Enrichment", 421, 0.94, 42),
    ("Suspicious Login Auto-Contain", 318, 0.97, 18),
    ("Ransomware Isolate Host", 87, 0.91, 210),
    ("IOC Enrichment (VT + AbuseIPDB)", 612, 0.99, 8),
    ("Malware Sample Detonation", 54, 0.83, 320),
    ("SLA Breach Notify", 205, 0.99, 4),
    ("Failed Login Cooldown", 501, 0.96, 12),
]

ANALYSTS = [
    ("Priya Patel", "L2", 187, 4.2, "Shift-A"),
    ("Marcus Chen", "L3", 142, 4.6, "Shift-B"),
    ("Sofia Alvarez", "L1", 312, 3.8, "Shift-A"),
    ("Diego Rossi", "L2", 224, 4.1, "Shift-C"),
    ("Amara Okafor", "L3", 118, 4.7, "Shift-B"),
    ("Yuki Tanaka", "L1", 289, 3.9, "Shift-C"),
    ("Fatima Khan", "L2", 201, 4.3, "Shift-A"),
]


def _seed(period: str, salt: str = "") -> random.Random:
    h = hashlib.sha256(f"{period}:{salt}".encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def _scale(period: str) -> float:
    return {"weekly": 1.0, "monthly": 4.2, "quarterly": 12.8}[period]


def _trend(period: str, key: str, points: int = 12, base: float = 100, jitter: float = 0.25):
    r = _seed(period, key)
    now = datetime.now(timezone.utc)
    step = {"weekly": timedelta(days=1), "monthly": timedelta(days=3), "quarterly": timedelta(days=8)}[period]
    out = []
    val = base
    for i in range(points, 0, -1):
        val = max(1, val * (1 + r.uniform(-jitter, jitter)))
        out.append({
            "date": (now - step * i).strftime("%Y-%m-%d"),
            "value": round(val, 1),
        })
    return out


def executive_overview(period: str):
    r = _seed(period, "exec")
    scale = _scale(period)
    incidents = int(280 * scale + r.randint(-30, 40))
    offenses = int(incidents * 3.4 + r.randint(-40, 60))
    sla = round(r.uniform(93.5, 98.7), 1)
    mttr = round(r.uniform(38, 74), 1)
    det_cov = round(r.uniform(71, 86), 1)
    automation = round(r.uniform(58, 79), 1)
    advisories = int(48 * scale / 4.2 + r.randint(0, 12))
    health = round(
        (sla * 0.30) + ((100 - mttr) * 0.20) + (det_cov * 0.25) + (automation * 0.15) + (r.uniform(70, 90) * 0.10),
        1,
    )
    risk = round(100 - health + r.uniform(-5, 5), 1)
    return {
        "period": period,
        "health_score": health,
        "risk_score": risk,
        "incidents": incidents,
        "offenses": offenses,
        "sla_compliance": sla,
        "mttr_hours": mttr,
        "detection_coverage": det_cov,
        "automation_rate": automation,
        "advisories": advisories,
        "top_threat_actor": THREAT_ACTORS[r.randint(0, len(THREAT_ACTORS) - 1)][0],
        "top_targeted_asset": r.choice(["srv-finance-01", "dc-primary-eu", "vpn-gw-uae", "erp-oracle-prod", "email-relay-05"]),
        "incident_trend": _trend(period, "inc_exec", base=incidents / 6, jitter=0.20),
        "sla_trend": _trend(period, "sla_exec", base=sla, jitter=0.03),
    }


def soc_manager(period: str):
    r = _seed(period, "soc_mgr")
    scale = _scale(period)
    incidents = int(280 * scale + r.randint(-30, 40))
    offenses = int(incidents * 3.4 + r.randint(-40, 60))
    return {
        "period": period,
        "incident_ops": {
            "total_offenses": offenses,
            "total_incidents": incidents,
            "conversion_rate": round(incidents / offenses * 100, 1),
            "new_incidents": int(incidents * r.uniform(0.85, 1.0)),
            "backlog_eow": int(r.uniform(38, 96)),
            "backlog_aging_days": round(r.uniform(3.1, 6.4), 1),
            "repeat_rate": round(r.uniform(4.5, 11.2), 1),
            "escalation_rate": round(r.uniform(8.2, 17.8), 1),
        },
        "speed_metrics": {
            "mttd_min": round(r.uniform(4.2, 12.8), 1),
            "mtta_min": round(r.uniform(6.8, 18.5), 1),
            "mttc_hours": round(r.uniform(2.4, 8.6), 1),
            "mttr_hours": round(r.uniform(38, 74), 1),
            "queue_time_min": round(r.uniform(3.2, 14.6), 1),
            "investigation_time_hours": round(r.uniform(1.8, 5.4), 1),
        },
        "sla": {
            "response_sla": round(r.uniform(94, 99), 1),
            "resolution_sla": round(r.uniform(88, 96), 1),
            "compliance_pct": round(r.uniform(93.5, 98.7), 1),
            "breaches": int(r.uniform(4, 21)),
            "breach_causes": [
                {"cause": "Analyst Unavailable", "count": r.randint(2, 11)},
                {"cause": "Playbook Failure", "count": r.randint(1, 6)},
                {"cause": "Escalation Delay", "count": r.randint(2, 8)},
                {"cause": "Client Communication", "count": r.randint(1, 5)},
            ],
        },
        "analyst_performance": [
            {
                "name": n, "level": lvl, "closed": int(closed * scale / 4.2),
                "avg_handle_time_min": round(r.uniform(18, 62), 1),
                "utilization": round(rating * 20 + r.uniform(-5, 3), 1),
                "reopened": r.randint(0, 6),
                "shift": shift,
            }
            for (n, lvl, closed, rating, shift) in ANALYSTS
        ],
        "detection_health": {
            "false_positive_rate": round(r.uniform(18, 34), 1),
            "true_positive_rate": round(r.uniform(66, 82), 1),
            "top_rules": [
                {"rule": name, "triggers": r.randint(120, 1400), "fp_rate": round(r.uniform(8, 62), 1)}
                for name in RULE_NAMES[:10]
            ],
            "severity_distribution": [
                {"severity": "Critical", "count": int(r.uniform(8, 24) * scale / 4.2)},
                {"severity": "High", "count": int(r.uniform(40, 90) * scale / 4.2)},
                {"severity": "Medium", "count": int(r.uniform(120, 240) * scale / 4.2)},
                {"severity": "Low", "count": int(r.uniform(180, 380) * scale / 4.2)},
            ],
            "wow_severity_delta": round(r.uniform(-12, 15), 1),
        },
        "trends": {
            "incidents": _trend(period, "inc_mgr", base=incidents / 6, jitter=0.22),
            "sla": _trend(period, "sla_mgr", base=95, jitter=0.03),
            "mttr": _trend(period, "mttr_mgr", base=54, jitter=0.15),
        },
    }


def client_executive(period: str):
    r = _seed(period, "client")
    scale = _scale(period)
    return {
        "period": period,
        "scorecard": {
            "composite_risk_score": round(r.uniform(22, 46), 1),
            "client_risk_rank": r.randint(2, 8),
            "quarterly_sla": round(r.uniform(94.2, 98.1), 1),
            "major_p1_p2_incidents": r.randint(2, 12),
            "yoy_incident_delta": round(r.uniform(-18, 8), 1),
            "yoy_mttr_delta": round(r.uniform(-22, 5), 1),
            "yoy_sla_delta": round(r.uniform(-2, 6), 1),
        },
        "business_risk": {
            "top_assets": [
                {"asset": a, "hits": r.randint(20, 160)}
                for a in ["srv-finance-01", "dc-primary-eu", "vpn-gw-uae", "erp-oracle-prod", "email-relay-05", "ad-fs-primary"]
            ],
            "top_sources": [
                {"country": c, "count": r.randint(80, 620)}
                for c in ["Russia", "China", "Iran", "North Korea", "Brazil", "USA", "Netherlands"]
            ],
            "phishing_incidents": int(r.uniform(38, 128) * scale / 4.2),
            "avg_dwell_hours": round(r.uniform(4.2, 22.8), 1),
            "repeat_incidents": int(r.uniform(6, 24) * scale / 4.2),
            "open_critical": r.randint(0, 8),
        },
        "threat_exposure": {
            "total_advisories": int(48 * scale / 4.2),
            "ioc_volume": int(r.uniform(1800, 6400) * scale / 4.2),
            "high_critical_cves": int(r.uniform(28, 82) * scale / 4.2),
            "threat_actors": [{"name": n, "activity": act} for (n, _, act) in THREAT_ACTORS[:6]],
            "malware": [{"family": m, "count": c} for (m, c) in MALWARE_FAMILIES],
            "advisory_trend": _trend(period, "adv_client", base=12, jitter=0.30),
        },
        "trends": {
            "monthly_incidents": _trend(period, "inc_client", base=48, jitter=0.20),
            "sla": _trend(period, "sla_client", base=95, jitter=0.02),
            "fp": _trend(period, "fp_client", base=25, jitter=0.15),
            "automation": _trend(period, "auto_client", base=68, jitter=0.08),
            "coverage": _trend(period, "cov_client", base=78, jitter=0.05),
        },
    }


def detection_engineering(period: str):
    r = _seed(period, "det_eng")
    tactic_cov = {t: r.randint(28, 92) for t in MITRE_TACTICS}
    return {
        "period": period,
        "quality": {
            "detection_coverage": round(r.uniform(72, 87), 1),
            "use_case_coverage": round(r.uniform(64, 84), 1),
            "mitre_coverage": round(sum(tactic_cov.values()) / len(tactic_cov), 1),
            "atlas_coverage": round(r.uniform(28, 58), 1),
            "quality_score": round(r.uniform(68, 88), 1),
        },
        "rules": [
            {
                "name": name,
                "triggers": r.randint(120, 1400),
                "fp_rate": round(r.uniform(6, 62), 1),
                "precision": round(r.uniform(0.42, 0.94), 2),
                "recall": round(r.uniform(0.55, 0.96), 2),
                "true_positives": r.randint(20, 320),
                "status": r.choice(["active", "active", "active", "tuning", "disabled"]),
            }
            for name in RULE_NAMES
        ],
        "unused_rules": r.randint(12, 42),
        "mitre_heatmap": [
            {
                "tactic": t,
                "coverage": tactic_cov[t],
                "techniques": [
                    {"name": tech, "covered": r.random() < (tactic_cov[t] / 100), "hits": r.randint(0, 42)}
                    for tech in MITRE_TECHNIQUES[t]
                ],
            }
            for t in MITRE_TACTICS
        ],
        "gap_analysis": {
            "techniques_covered": r.randint(140, 210),
            "techniques_missing": r.randint(60, 140),
            "atlas_covered": r.randint(6, 22),
            "new_opportunities": [
                "T1566.002 - Spearphishing Link (Cross-tenant)",
                "T1078.004 - Cloud Accounts Persistence",
                "T1055.012 - Process Hollowing",
                "T1595.002 - Vulnerability Scanning",
                "T1027.010 - Command Obfuscation",
            ],
        },
        "trends": {
            "new_rules": _trend(period, "newrules", base=8, jitter=0.30),
            "rules_tuned": _trend(period, "tuned", base=14, jitter=0.28),
            "fp_reduction": _trend(period, "fpred", base=28, jitter=0.18),
            "coverage_qoq": _trend(period, "cov_qoq", base=78, jitter=0.04),
        },
    }


def threat_intelligence(period: str):
    r = _seed(period, "ti")
    scale = _scale(period)
    return {
        "period": period,
        "landscape": {
            "total_advisories": int(48 * scale / 4.2),
            "ioc_volume": int(r.uniform(1800, 6400) * scale / 4.2),
            "new_cves": int(r.uniform(120, 380) * scale / 4.2),
            "critical_cves": int(r.uniform(28, 82) * scale / 4.2),
            "threat_actors": [{"name": n, "origin": o, "activity": a} for (n, o, a) in THREAT_ACTORS],
            "malware_families": [{"family": m, "count": c} for (m, c) in MALWARE_FAMILIES],
            "campaigns": r.randint(14, 42),
            "industries": [
                {"industry": i, "targeted": r.randint(8, 62)}
                for i in ["Finance", "Healthcare", "Energy", "Government", "Retail", "Manufacturing", "Telecom"]
            ],
        },
        "effectiveness": {
            "advisory_to_alert": round(r.uniform(38, 72), 1),
            "advisory_to_incident": round(r.uniform(12, 34), 1),
            "ioc_match_rate": round(r.uniform(6.2, 18.4), 1),
            "ioc_hit_count": int(r.uniform(120, 620) * scale / 4.2),
            "ioc_type_distribution": [
                {"type": "IP", "count": r.randint(320, 1200)},
                {"type": "Domain", "count": r.randint(280, 940)},
                {"type": "URL", "count": r.randint(180, 720)},
                {"type": "Hash (SHA256)", "count": r.randint(220, 640)},
                {"type": "Email", "count": r.randint(40, 180)},
            ],
        },
        "coverage": {
            "tactic_distribution": [
                {"tactic": t, "count": r.randint(4, 42)} for t in MITRE_TACTICS
            ],
            "initial_access": r.randint(24, 68),
            "credential_access": r.randint(18, 52),
            "persistence": r.randint(14, 44),
        },
        "quality": {
            "advisories_reviewed": int(45 * scale / 4.2),
            "advisories_actioned": int(28 * scale / 4.2),
            "detections_created": r.randint(6, 24),
            "hunting_cases": r.randint(4, 18),
            "intel_to_detection_rate": round(r.uniform(38, 68), 1),
        },
        "recent_advisories": [
            {
                "id": f"TIA-{2026}-{r.randint(1000, 9999)}",
                "title": t,
                "severity": r.choice(["Critical", "High", "Medium"]),
                "actor": r.choice([a[0] for a in THREAT_ACTORS]),
                "published": (datetime.now(timezone.utc) - timedelta(days=r.randint(0, 28))).strftime("%Y-%m-%d"),
            }
            for t in [
                "Lockbit 3.0 targeting Middle East financial sector",
                "APT29 exploiting Exchange 0-day (CVE-2026-1183)",
                "Scattered Spider social engineering wave against helpdesks",
                "New Rhysida ransomware variant with double extortion",
                "Supply chain compromise via popular npm package",
                "Kimsuky credential harvesting campaign targeting energy",
            ]
        ],
    }


def soar_automation(period: str):
    r = _seed(period, "soar")
    scale = _scale(period)
    return {
        "period": period,
        "health": {
            "automation_rate": round(r.uniform(58, 79), 1),
            "success_rate": round(r.uniform(92.5, 98.4), 1),
            "failed_automations": int(r.uniform(14, 68) * scale / 4.2),
            "playbooks_executed": int(r.uniform(1800, 4200) * scale / 4.2),
            "growth_pct": round(r.uniform(3.2, 14.8), 1),
            "qoq_growth": round(r.uniform(6.4, 22.5), 1),
        },
        "playbooks": [
            {
                "name": name, "executions": int(execs * scale / 4.2),
                "success_rate": round(succ * 100, 1),
                "avg_runtime_sec": runtime + r.randint(-8, 12),
                "failed": r.randint(0, 12),
                "manual_intervention_pct": round(r.uniform(2, 22), 1),
            }
            for (name, execs, succ, runtime) in PLAYBOOKS
        ],
        "efficiency": {
            "mean_manual_touch_min": round(r.uniform(2.4, 8.6), 1),
            "hours_saved": int(r.uniform(420, 1280) * scale / 4.2),
            "auto_closures": int(r.uniform(320, 980) * scale / 4.2),
            "manual_closures": int(r.uniform(120, 380) * scale / 4.2),
            "automation_roi_pct": round(r.uniform(180, 480), 1),
        },
        "trends": {
            "automation": _trend(period, "auto_soar", base=68, jitter=0.06),
            "success": _trend(period, "succ_soar", base=95, jitter=0.02),
            "executions": _trend(period, "exec_soar", base=420, jitter=0.20),
        },
    }
