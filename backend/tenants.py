"""Tenant-aware mock data adapter.

Applies deterministic per-tenant modifiers to the base mock_data functions so
each QRadar domain shows its own KPI profile.
"""
import hashlib
import random
from datetime import datetime, timezone

import mock_data


DEFAULT_TENANTS = [
    {
        "id": "all",
        "domain": "ALL",
        "name": "All Tenants",
        "description": "Aggregated across every QRadar domain",
        "primary_color": "#3B82F6",
        "logo_url": None,
        "created_at": None,
        "risk_modifier": 1.0,
        "volume_modifier": 1.0,
        "seed": False,
    },
    {
        "id": "acme-corp",
        "domain": "ACME_CORP",
        "name": "Acme Corporation",
        "description": "Enterprise manufacturing · QRadar Domain 12",
        "primary_color": "#EA580C",
        "logo_url": None,
        "created_at": None,
        "risk_modifier": 1.15,
        "volume_modifier": 1.3,
        "seed": True,
    },
    {
        "id": "globalbank",
        "domain": "GLOBALBANK_FIN",
        "name": "GlobalBank Financial",
        "description": "Tier-1 bank · QRadar Domain 07",
        "primary_color": "#0EA5E9",
        "logo_url": None,
        "created_at": None,
        "risk_modifier": 0.85,
        "volume_modifier": 0.75,
        "seed": True,
    },
]


def _tenant_factor(tenant: dict, key: str) -> float:
    if not tenant or tenant.get("id") in (None, "all"):
        return 1.0
    h = hashlib.md5(f"{tenant['id']}:{key}".encode()).hexdigest()
    jitter = (int(h[:6], 16) % 200 - 100) / 1000.0  # ±10%
    return tenant.get("volume_modifier", 1.0) * (1 + jitter)


def _apply_num(v, factor):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return max(0, int(round(v * factor)))
    if isinstance(v, float):
        return round(v * factor, 2)
    return v


def _scale_dict(d: dict, factor: float, skip_keys=("period", "top_threat_actor", "top_targeted_asset")):
    out = {}
    for k, v in d.items():
        if k in skip_keys:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = _scale_dict(v, factor, skip_keys)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = _apply_num(v, factor)
        else:
            out[k] = v
    return out


def _blank(o):
    """Deep-zero a structure: numbers→0, strings→'', lists→[], dict keys kept.
    Used so dashboards carry NO fabricated data — only live uploads populate them."""
    if isinstance(o, bool):
        return False
    if isinstance(o, (int, float)):
        return 0
    if isinstance(o, str):
        return ""
    if isinstance(o, list):
        return []
    if isinstance(o, dict):
        return {k: _blank(v) for k, v in o.items()}
    return None


def _blank_like(period: str, mock_fn):
    b = _blank(mock_fn(period))
    if isinstance(b, dict):
        b["period"] = period
        b["data_status"] = "empty"
    return b


def executive_overview(period: str, tenant: dict):
    return _blank_like(period, mock_data.executive_overview)


def soc_manager(period: str, tenant: dict):
    return _blank_like(period, mock_data.soc_manager)


def client_executive(period: str, tenant: dict):
    return _blank_like(period, mock_data.client_executive)


def detection_engineering(period: str, tenant: dict):
    return _blank_like(period, mock_data.detection_engineering)


def threat_intelligence(period: str, tenant: dict):
    return _blank_like(period, mock_data.threat_intelligence)


def soar_automation(period: str, tenant: dict):
    return _blank_like(period, mock_data.soar_automation)


def all_dashboards(period: str, tenant: dict):
    """Return every dashboard payload for PPTX / email generation."""
    return {
        "executive": executive_overview(period, tenant),
        "soc_manager": soc_manager(period, tenant),
        "client": client_executive(period, tenant),
        "detection": detection_engineering(period, tenant),
        "threat_intel": threat_intelligence(period, tenant),
        "soar": soar_automation(period, tenant),
    }
