"""Tests for iteration_17: Severity Mix filter, Repeat Incidents count, YoY deltas.

Covers:
  - SOC Manager severity_distribution filtered to only High/Medium/Low with count>0
  - Client business_risk.repeat_incidents = duplicate occurrence count
  - Client scorecard yoy_incident_delta / yoy_mttr_delta / yoy_sla_delta
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TENANT = "globalbank"
FIXTURE = "/tmp/xsoar_sev.csv"
ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Admin@2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def upload_and_cleanup(headers):
    # Clean any prior globalbank xsoar rows
    requests.delete(f"{BASE_URL}/api/dashboard/soc-manager/data",
                    params={"tenant_id": TENANT}, headers=headers, timeout=20)
    with open(FIXTURE, "rb") as f:
        files = {"file": ("xsoar_sev.csv", f, "text/csv")}
        r = requests.post(f"{BASE_URL}/api/upload/data",
                          params={"source": "xsoar", "tenant_id": TENANT},
                          headers=headers, files=files, timeout=60)
    assert r.status_code == 200, r.text
    yield
    # Cleanup
    requests.delete(f"{BASE_URL}/api/dashboard/soc-manager/data",
                    params={"tenant_id": TENANT}, headers=headers, timeout=20)


def test_severity_mix_only_high_medium_low(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/soc-manager",
                     params={"tenant_id": TENANT}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    sev = data.get("severity_distribution", [])
    labels = {b["severity"]: b["count"] for b in sev}
    assert set(labels.keys()) == {"High", "Medium", "Low"}, f"Unexpected buckets: {labels}"
    assert labels["High"] == 5
    assert labels["Medium"] == 2
    assert labels["Low"] == 2
    for k in labels:
        assert labels[k] > 0
    # No numeric/unknown
    assert "10175" not in labels and "Unknown" not in labels and "Critical" not in labels


def test_repeat_incidents_count(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/client",
                     params={"tenant_id": TENANT}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    br = r.json().get("business_risk", {})
    # Brute Force x5 -> 4, Phishing Email x2 -> 1, Port Scan x2 -> 1, Weird x1 -> 0 => 6
    assert br.get("repeat_incidents") == 6, br


def test_yoy_deltas(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/client",
                     params={"tenant_id": TENANT}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    sc = r.json().get("scorecard", {})
    # May=4, June=6 -> yoy_inc = (6-4)/4 = 50%
    assert sc.get("yoy_incident_delta") == 50.0, sc
    # MTTR constant 3600s both months -> delta 0
    assert sc.get("yoy_mttr_delta") == 0.0, sc
    # May SLA ok = 2/4 = 50%, June SLA ok = 6/6 = 100% -> 100-50 = 50.0
    assert sc.get("yoy_sla_delta") == 50.0, sc


def test_empty_tenant_still_ok(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/client",
                     params={"tenant_id": "__nonexistent_tenant__"},
                     headers=headers, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body.get("data_status") == "empty"
