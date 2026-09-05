"""Detection Engineering: rule catalog + xsoar rule-match + log validation upload flow.

Covers acme-corp tenant end-to-end:
  1. Upload /tmp/rules.xlsx (source=rules) → dashboard goes live, coverage KPIs,
     MITRE heat-map, rule_effectiveness with total_rules > 0.
  2. Upload /tmp/xsoar_rules_match.csv (source=xsoar) → rule_effectiveness triggered_rules=8,
     avg_triggers ≈ 11.2, bands.above_avg=3.
  3. Upload /tmp/logval.xlsx (source=log_validation) → priority_breakdown + logval_total.
  4. Empty-state tenant returns data_status=empty.
  5. Cleanup DELETE endpoints.
"""
import os
import pytest
import requests

def _base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    # Fallback: read from frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE = _base_url()
TENANT = "acme-corp"
EMPTY_TENANT = "globalbank"
RULES_ONLY_TENANT = "rulesonly-co"
CLEANUP_TENANTS = [TENANT, EMPTY_TENANT, RULES_ONLY_TENANT, "all"]

RULES_FILE = "/tmp/rules.xlsx"
XSOAR_FILE = "/tmp/xsoar_rules_match.csv"
XSOAR_ID_FILE = "/tmp/xsoar_id_match.csv"
LOGVAL_FILE = "/tmp/logval.xlsx"


@pytest.fixture(scope="module")
def headers():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "admin@mssp-soc.io", "password": "Admin@2026!"}, timeout=30)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module", autouse=True)
def _clean(headers):
    for tenant in CLEANUP_TENANTS:
        for path in ("dashboard/detection/rules-data", "dashboard/detection/logval-data",
                     "dashboard/soc-manager/data"):
            headers.delete(f"{BASE}/api/{path}", params={"tenant_id": tenant})
    yield
    for tenant in CLEANUP_TENANTS:
        for path in ("dashboard/detection/rules-data", "dashboard/detection/logval-data",
                     "dashboard/soc-manager/data"):
            headers.delete(f"{BASE}/api/{path}", params={"tenant_id": tenant})


def _upload(client, source, filepath, tenant_id=TENANT):
    with open(filepath, "rb") as f:
        return client.post(
            f"{BASE}/api/upload/data",
            params={"source": source, "tenant_id": tenant_id},
            files={"file": (os.path.basename(filepath), f)},
        )


def test_01_empty_tenant_returns_empty(headers):
    r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                     params={"tenant_id": EMPTY_TENANT})
    assert r.status_code == 200
    assert r.json().get("data_status") == "empty"


def test_02_upload_rules_catalog(headers):
    r = _upload(headers, "rules", RULES_FILE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rules_row_count"] > 0
    assert body["bound_rows"] > 0
    assert body["bound_rows"] == body["rules_row_count"]
    # Fixture is ~1526 rules; be lenient
    assert body["bound_rows"] > 1000
    assert body.get("warning") is None or "0 rows" not in body.get("warning", "")


def test_03_detection_live_after_rules(headers):
    r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                     params={"tenant_id": TENANT})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["data_status"] == "live"
    q = d["quality"]
    for k in ("detection_coverage", "use_case_coverage", "mitre_coverage", "quality_score"):
        assert isinstance(q[k], (int, float)), f"{k}={q[k]!r}"
    assert q["atlas_coverage"] is None, "ATLAS must be null (not derivable from catalog)"
    assert isinstance(d.get("mitre_heatmap"), list) and len(d["mitre_heatmap"]) > 0
    re_eff = d["rule_effectiveness"]
    assert re_eff["total_rules"] > 1000
    # No xsoar yet → no triggered rules
    assert re_eff["triggered_rules"] == 0


def test_04_upload_xsoar_match(headers):
    r = _upload(headers, "xsoar", XSOAR_FILE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("xsoar_row_count", 0) > 0
    assert body["bound_rows"] > 0


def test_05_rule_effectiveness_populated(headers):
    r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                     params={"tenant_id": TENANT})
    d = r.json()
    re_eff = d["rule_effectiveness"]
    assert re_eff["triggered_rules"] == 8, f"expected 8 triggered, got {re_eff['triggered_rules']}"
    assert 10.5 <= re_eff["avg_triggers"] <= 12.0, f"avg={re_eff['avg_triggers']}"
    assert re_eff["bands"]["above_avg"] == 3
    # rules array capped at 60
    assert len(re_eff["rules"]) <= 60
    # Top rule should have >0 triggers
    assert re_eff["rules"][0]["triggers"] > 0


def test_06_upload_logval(headers):
    r = _upload(headers, "log_validation", LOGVAL_FILE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("logval_row_count", 0) > 0
    assert body["bound_rows"] > 0


def test_07_priority_pie_present(headers):
    r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                     params={"tenant_id": TENANT})
    d = r.json()
    assert d.get("logval_total", 0) > 0
    pb = d["priority_breakdown"]
    assert isinstance(pb, list) and len(pb) > 0
    names = {p["name"] for p in pb}
    # At least one of the canonical priorities
    assert names & {"Essential", "Selective", "Redundant", "Undefined"}
    for p in pb:
        assert isinstance(p["value"], int) and p["value"] > 0


def test_08_delete_endpoints_clean(headers):
    r1 = headers.delete(f"{BASE}/api/dashboard/detection/rules-data",
                         params={"tenant_id": TENANT})
    r2 = headers.delete(f"{BASE}/api/dashboard/detection/logval-data",
                         params={"tenant_id": TENANT})
    assert r1.status_code == 200 and r1.json().get("cleared") is True
    assert r2.status_code == 200 and r2.json().get("cleared") is True
    # xsoar clear
    r3 = headers.delete(f"{BASE}/api/dashboard/soc-manager/data",
                         params={"tenant_id": TENANT})
    assert r3.status_code == 200
    # dashboard should be empty now
    r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                     params={"tenant_id": TENANT})
    assert r.json().get("data_status") == "empty"


# --- Rule ID matching (new feature) ------------------------------------------
def test_09_upload_rules_and_id_xsoar_globalbank(headers):
    # Ensure globalbank is clean, then upload rules + xsoar_id_match.csv
    for path in ("dashboard/detection/rules-data", "dashboard/detection/logval-data",
                 "dashboard/soc-manager/data"):
        headers.delete(f"{BASE}/api/{path}", params={"tenant_id": EMPTY_TENANT})

    r = _upload(headers, "rules", RULES_FILE, tenant_id=EMPTY_TENANT)
    assert r.status_code == 200, r.text
    assert r.json()["bound_rows"] > 1000

    r = _upload(headers, "xsoar", XSOAR_ID_FILE, tenant_id=EMPTY_TENANT)
    assert r.status_code == 200, r.text
    assert r.json().get("xsoar_row_count", 0) >= 27


def test_10_rule_id_matching_populated(headers):
    r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                     params={"tenant_id": EMPTY_TENANT})
    d = r.json()
    re_eff = d["rule_effectiveness"]
    assert re_eff["triggered_rules"] == 5, (
        f"expected 5 triggered by rule_id, got {re_eff['triggered_rules']}")
    top = re_eff["rules"][:3]
    top_ids = [str(x.get("rule_id")) for x in top]
    top_trigs = [x["triggers"] for x in top]
    assert "145611" in top_ids, f"top rule_ids={top_ids}"
    assert "102198" in top_ids, f"top rule_ids={top_ids}"
    assert "102201" in top_ids, f"top rule_ids={top_ids}"
    # Triggers by id (order-independent lookup)
    by_id = {str(x.get("rule_id")): x["triggers"] for x in re_eff["rules"]}
    assert by_id.get("145611") == 12
    assert by_id.get("102198") == 8
    assert by_id.get("102201") == 4


# --- Rules-only tenant (no XSOAR) --------------------------------------------
def test_11_rules_only_tenant(headers):
    for path in ("dashboard/detection/rules-data", "dashboard/detection/logval-data",
                 "dashboard/soc-manager/data"):
        headers.delete(f"{BASE}/api/{path}", params={"tenant_id": RULES_ONLY_TENANT})

    r = _upload(headers, "rules", RULES_FILE, tenant_id=RULES_ONLY_TENANT)
    assert r.status_code == 200, r.text

    r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                     params={"tenant_id": RULES_ONLY_TENANT})
    d = r.json()
    assert d["data_status"] == "live"
    re_eff = d["rule_effectiveness"]
    assert re_eff["total_rules"] > 1000
    assert re_eff["triggered_rules"] == 0
    assert re_eff["bands"]["above_avg"] == 0
    assert re_eff["bands"]["near_avg"] == 0
    assert re_eff["bands"]["below_avg"] == 0
    assert re_eff["bands"]["not_triggered"] == re_eff["total_rules"]
    # Every rule in returned array should be band=not_triggered
    for x in re_eff["rules"]:
        assert x["band"] == "not_triggered"


def test_12_final_cleanup_all_tenants(headers):
    for tenant in CLEANUP_TENANTS:
        for path in ("dashboard/detection/rules-data",
                     "dashboard/detection/logval-data",
                     "dashboard/soc-manager/data"):
            headers.delete(f"{BASE}/api/{path}", params={"tenant_id": tenant})
        r = headers.get(f"{BASE}/api/dashboard/detection-engineering",
                         params={"tenant_id": tenant})
        assert r.json().get("data_status") == "empty", (
            f"tenant {tenant} not empty after cleanup")
