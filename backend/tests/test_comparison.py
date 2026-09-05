"""Backend tests for the Comparison / Snapshot feature."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mssp-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Admin@2026!"

EXPECTED_KPI_KEYS = {
    "incidents", "sla_compliance", "mttr_hours", "automation_rate",
    "risk_score", "health_score", "false_positive_rate", "advisories",
    "mitre_coverage", "detection_coverage", "quality_score",
    "rules_triggered", "total_rules",
}

created_snapshot_ids = []


@pytest.fixture(scope="module")
def auth_headers():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    assert token, f"no token in response: {r.json()}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def cleanup(auth_headers):
    yield
    # teardown: delete any snapshots we made
    for sid in created_snapshot_ids:
        try:
            requests.delete(f"{BASE_URL}/api/comparison/snapshot/{sid}",
                            headers=auth_headers, timeout=15)
        except Exception:
            pass


def _create(period, headers):
    r = requests.post(f"{BASE_URL}/api/comparison/snapshot",
                      params={"period": period, "tenant_id": "all"},
                      headers=headers, timeout=60)
    assert r.status_code == 200, f"{period} snapshot failed: {r.status_code} {r.text}"
    j = r.json()
    assert "id" in j and j["period"] == period
    assert "kpis" in j and set(j["kpis"].keys()) == EXPECTED_KPI_KEYS, \
        f"KPI keys mismatch: {set(j['kpis'].keys()) ^ EXPECTED_KPI_KEYS}"
    created_snapshot_ids.append(j["id"])
    return j


def test_1_snapshot_weekly_first(auth_headers):
    snap = _create("weekly", auth_headers)
    # Some KPI should be non-zero (tenant 'all' has data loaded)
    non_zero = [v for v in snap["kpis"].values() if v]
    assert len(non_zero) > 0, f"All KPIs are zero: {snap['kpis']}"


def test_2_compare_baseline(auth_headers):
    r = requests.get(f"{BASE_URL}/api/comparison/compare",
                     params={"period": "weekly", "tenant_id": "all"},
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["current"] is not None
    # After 1 snapshot: previous should be None => baseline
    # (There may already be prior snapshots from other testers; tolerate both.)
    assert isinstance(j["deltas"], dict)


def test_3_snapshot_weekly_second_and_compare(auth_headers):
    time.sleep(1)  # ensure distinct created_at
    _create("weekly", auth_headers)
    r = requests.get(f"{BASE_URL}/api/comparison/compare",
                     params={"period": "weekly", "tenant_id": "all"},
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["current"] is not None and j["previous"] is not None, \
        f"Expected two snapshots comparison: {j}"
    # deltas should have all 13 keys with delta computed (may be 0)
    assert set(j["deltas"].keys()) == EXPECTED_KPI_KEYS
    for k, d in j["deltas"].items():
        assert "delta" in d and "pct" in d and "current" in d and "previous" in d
        assert d["delta"] is not None, f"delta is None for {k} despite 2 snapshots"


def test_4_list_snapshots_weekly(auth_headers):
    r = requests.get(f"{BASE_URL}/api/comparison/snapshots",
                     params={"period": "weekly", "tenant_id": "all"},
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    lst = r.json()
    assert isinstance(lst, list) and len(lst) >= 2
    # newest-first
    ts = [x["created_at"] for x in lst]
    assert ts == sorted(ts, reverse=True), "snapshots not sorted newest-first"
    # no _id leak
    assert all("_id" not in x for x in lst)


def test_5_period_isolation_monthly(auth_headers):
    m = _create("monthly", auth_headers)
    rw = requests.get(f"{BASE_URL}/api/comparison/snapshots",
                      params={"period": "weekly", "tenant_id": "all"},
                      headers=auth_headers, timeout=30).json()
    rm = requests.get(f"{BASE_URL}/api/comparison/snapshots",
                      params={"period": "monthly", "tenant_id": "all"},
                      headers=auth_headers, timeout=30).json()
    assert m["id"] in [x["id"] for x in rm]
    assert m["id"] not in [x["id"] for x in rw], "monthly snapshot leaked into weekly list"


def test_6_quarterly_snapshot(auth_headers):
    q = _create("quarterly", auth_headers)
    assert q["period"] == "quarterly"


def test_7_delete_snapshot(auth_headers):
    # create one to delete
    snap = _create("weekly", auth_headers)
    sid = snap["id"]
    r = requests.delete(f"{BASE_URL}/api/comparison/snapshot/{sid}",
                        headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert r.json().get("deleted") is True
    # verify not in list
    lst = requests.get(f"{BASE_URL}/api/comparison/snapshots",
                       params={"period": "weekly", "tenant_id": "all"},
                       headers=auth_headers, timeout=30).json()
    assert sid not in [x["id"] for x in lst]
    if sid in created_snapshot_ids:
        created_snapshot_ids.remove(sid)


def test_8_invalid_period_rejected(auth_headers):
    # FIX 1: server should now reject invalid period with 400 (not store record)
    r = requests.post(f"{BASE_URL}/api/comparison/snapshot",
                      params={"period": "yearly", "tenant_id": "all"},
                      headers=auth_headers, timeout=60)
    assert r.status_code == 400, f"expected 400 for invalid period, got {r.status_code} {r.text}"
    # verify no 'yearly' record leaked into any list
    for p in ("weekly", "monthly", "quarterly"):
        lst = requests.get(f"{BASE_URL}/api/comparison/snapshots",
                           params={"period": p, "tenant_id": "all"},
                           headers=auth_headers, timeout=30).json()
        assert all(x.get("period") != "yearly" for x in lst)


def test_9_valid_periods_accepted(auth_headers):
    for p in ("weekly", "monthly", "quarterly"):
        r = requests.post(f"{BASE_URL}/api/comparison/snapshot",
                          params={"period": p, "tenant_id": "all"},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"{p} should be 200, got {r.status_code}"
        created_snapshot_ids.append(r.json()["id"])
