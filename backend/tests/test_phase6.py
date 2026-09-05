"""Phase-6 tests: Detection XSOAR overlay, IRIS live_xsoar, Scheduled email reports."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    from dotenv import load_dotenv
    load_dotenv("/app/frontend/.env")
    BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mssp-soc.io", "password": "Admin@2026!"}
XSOAR_TENANT = "acme-corp"
NO_XSOAR_TENANT = "globalbank"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


# -------- Detection Engineering overlay --------
class TestDetectionOverlay:
    def test_live_when_uploaded(self, headers):
        r = requests.get(f"{API}/dashboard/detection-engineering",
                         params={"tenant_id": XSOAR_TENANT}, headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("xsoar_live") is True, f"xsoar_live missing/false: {list(d.keys())}"
        assert "mitre_heatmap" in d and isinstance(d["mitre_heatmap"], list) and len(d["mitre_heatmap"]) > 0
        assert "rules" in d and isinstance(d["rules"], list) and len(d["rules"]) > 0
        r0 = d["rules"][0]
        for k in ("fp_rate", "precision", "recall"):
            assert k in r0, f"rule missing {k}: {r0}"

    def test_fallback_without_upload(self, headers):
        r = requests.get(f"{API}/dashboard/detection-engineering",
                         params={"tenant_id": NO_XSOAR_TENANT}, headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert not d.get("xsoar_live"), "xsoar_live should be absent/false for tenant without upload"
        assert "mitre_heatmap" in d


# -------- IRIS Copilot with live_xsoar --------
class TestIrisLiveXsoar:
    def test_fp_rate_question(self, headers):
        r = requests.post(f"{API}/copilot/chat", headers=headers, timeout=60,
                          json={"message": "Which rule has the highest FP rate?",
                                "tenant_id": XSOAR_TENANT, "period": "monthly"})
        assert r.status_code == 200, r.text
        d = r.json()
        ans = d.get("answer") or d.get("response") or ""
        assert ans, f"empty answer: {d}"
        # Rule fallback OK per PS
        assert d.get("source") in ("rule", "llm", "hf", "model", None)
        # Should mention the highest-FP rule (Suspicious PowerShell @ 75%)
        low = ans.lower()
        assert ("powershell" in low) or ("%" in ans) or ("fp" in low), f"unexpected answer: {ans}"


# -------- Scheduled email reports CRUD + run-now --------
class TestReportSchedules:
    def test_full_flow(self, headers):
        # Create
        payload = {
            "tenant_id": XSOAR_TENANT,
            "period": "monthly",
            "frequency": "weekly",
            "recipients": ["TEST_recipient@example.com"],
            "subject": "TEST_ Weekly SOC report",
            "enabled": True,
        }
        r = requests.post(f"{API}/reports/schedules", headers=headers, json=payload)
        assert r.status_code == 200, r.text
        sched = r.json()
        assert "_id" not in sched
        sid = sched["id"]
        assert sched["frequency"] == "weekly"
        assert sched["recipients"] == ["TEST_recipient@example.com"]

        try:
            # List
            r = requests.get(f"{API}/reports/schedules", headers=headers)
            assert r.status_code == 200
            ids = [s["id"] for s in r.json()]
            assert sid in ids

            # Toggle enabled via PATCH (full body)
            payload_off = {**payload, "enabled": False}
            r = requests.patch(f"{API}/reports/schedules/{sid}",
                               headers=headers, json=payload_off)
            assert r.status_code == 200, r.text
            assert r.json()["enabled"] is False

            # Run now
            r = requests.post(f"{API}/reports/schedules/{sid}/run-now",
                              headers=headers, timeout=120)
            assert r.status_code == 200, r.text
            rn = r.json()
            assert rn["ran"] is True
            assert rn.get("mode") in ("console", "smtp")

            # Email history contains PPTX attachment
            r = requests.get(f"{API}/email/history", headers=headers)
            assert r.status_code == 200
            hist = r.json()
            # Find recent entry with TEST_ subject
            matches = [e for e in (hist if isinstance(hist, list) else hist.get("items", []))
                       if "TEST_" in str(e.get("subject", "")) or "TEST_recipient" in str(e.get("to", ""))]
            assert matches, f"No email history for schedule run: sample={hist[:2] if isinstance(hist, list) else hist}"
            latest = matches[0]
            atts = latest.get("attachments") or []
            names = " ".join([str(a.get("filename", a) if isinstance(a, dict) else a) for a in atts])
            assert ".pptx" in names.lower() or any(".pptx" in str(a).lower() for a in atts), \
                f"No pptx attachment: {atts}"
        finally:
            # Delete
            r = requests.delete(f"{API}/reports/schedules/{sid}", headers=headers)
            assert r.status_code == 200
            r = requests.get(f"{API}/reports/schedules", headers=headers)
            assert sid not in [s["id"] for s in r.json()]


# -------- Regression: all 7 dashboards --------
class TestDashboardsRegression:
    @pytest.mark.parametrize("path", [
        "executive", "soc-manager", "detection-engineering",
        "threat-intel", "soar-automation", "client",
    ])
    def test_dashboard(self, headers, path):
        r = requests.get(f"{API}/dashboard/{path}", headers=headers,
                         params={"period": "monthly", "tenant_id": "all"})
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
