"""Tests for BUG1-4 fixes and regressions - iteration 8."""
import os
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Iris-df02a9d88045!Aa9"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# BUG1 - PPTX export
def test_pptx_export(headers):
    r = requests.get(f"{BASE_URL}/api/export/pptx",
                     params={"period": "monthly", "tenant_id": "all"},
                     headers=headers, timeout=120)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    assert len(r.content) > 5000
    # pptx zip magic
    assert r.content[:2] == b"PK"


# BUG2/3/4 - Executive endpoint
def test_executive_endpoint(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/executive",
                     params={"tenant_id": "all"}, headers=headers, timeout=60)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    print("EXEC:", {k: data.get(k) for k in
                    ["offenses", "qradar_false_positives", "mttr_hours",
                     "detection_coverage", "incidents"]})
    # BUG2 offenses > 0
    assert data.get("offenses", 0) > 0, f"offenses={data.get('offenses')}"
    assert data.get("qradar_false_positives", 0) > 0
    # BUG3 mttr sane (median expect ~12, definitely not 150)
    mttr = data.get("mttr_hours")
    assert mttr is not None
    assert 0 < mttr < 50, f"mttr_hours={mttr} not in sane range"
    # BUG4 detection coverage > 0
    assert data.get("detection_coverage", 0) > 0


# Regression SOC Manager
def test_soc_manager(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/soc-manager",
                     params={"tenant_id": "all"}, headers=headers, timeout=60)
    assert r.status_code == 200
    data = r.json()
    print("SOC:", {k: data.get(k) for k in
                   ["mttr_hours", "qradar_offenses", "qradar_false_positives",
                    "log_sources_enabled", "log_sources_added"]})
    mttr = data.get("mttr_hours")
    if mttr is not None:
        assert 0 < mttr < 50, f"soc-manager mttr={mttr}"


# Regression Detection Engineering
def test_detection_engineering(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/detection-engineering",
                     params={"tenant_id": "all"}, headers=headers, timeout=60)
    assert r.status_code == 200


# Regression IRIS chat
def test_iris_chat(headers):
    r = requests.post(f"{BASE_URL}/api/copilot/chat",
                      json={"message": "What is my current MTTR?"},
                      headers=headers, timeout=120)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    print("CHAT source:", data.get("source"))
    assert data.get("source") == "hf-llm", f"source={data.get('source')}"
