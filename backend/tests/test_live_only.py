"""
Phase-7 verification: dummy-data removal.

Tests:
1. Persona logins removed — only admin works.
2. Empty-state contracts for all dashboards + AI insights + threat intel.
3. Live path after XSOAR upload for acme-corp (executive/client/detection).
4. PPTX export returns 200 with empty tenant and with live tenant.
5. Report schedule CRUD + run-now (console mode) + email history.
6. IRIS copilot rule fallback (no crash) with no data.
Cleans up: deletes acme-corp XSOAR upload and any schedules it created.
"""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@mssp-soc.io", "password": "Admin@2026!"}
XSOAR_CSV = "/tmp/xsoar_sample.csv"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module", autouse=True)
def _cleanup_after(admin_headers):
    """Ensure acme-corp is clean at start and end."""
    requests.delete(f"{API}/dashboard/soc-manager/data",
                    params={"tenant_id": "acme-corp"},
                    headers=admin_headers, timeout=15)
    yield
    requests.delete(f"{API}/dashboard/soc-manager/data",
                    params={"tenant_id": "acme-corp"},
                    headers=admin_headers, timeout=15)


# ---------------- 1. auth ----------------
class TestAuthPersonasRemoved:
    def test_admin_login_ok(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("access_token") or body.get("token")

    @pytest.mark.parametrize("persona", [
        {"email": "soc.manager@mssp-soc.io", "password": "SocManager@2026!"},
        {"email": "analyst@mssp-soc.io", "password": "Analyst@2026!"},
        {"email": "ciso@mssp-soc.io", "password": "Ciso@2026!"},
    ])
    def test_persona_login_rejected(self, persona):
        r = requests.post(f"{API}/auth/login", json=persona, timeout=15)
        assert r.status_code in (400, 401, 403), (
            f"persona {persona['email']} should be rejected, got {r.status_code}: {r.text[:200]}"
        )


# ---------------- 2. empty state ----------------
class TestEmptyStateContracts:
    @pytest.mark.parametrize("path", [
        "/dashboard/executive",
        "/dashboard/client",
        "/dashboard/detection-engineering",
        "/dashboard/soc-manager",
        "/dashboard/soar-automation",
    ])
    @pytest.mark.parametrize("tenant", ["all", "globalbank"])
    def test_dashboard_empty(self, admin_headers, path, tenant):
        r = requests.get(f"{API}{path}", params={"tenant_id": tenant},
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("data_status") == "empty", (
            f"{path}?tenant={tenant} expected data_status=empty, got {data.get('data_status')}"
        )

    def test_executive_recommendations_empty(self, admin_headers):
        r = requests.get(f"{API}/dashboard/executive",
                         params={"tenant_id": "globalbank"},
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert r.json().get("recommendations") == []

    def test_ai_insights_empty(self, admin_headers):
        r = requests.get(f"{API}/ai/insights",
                         params={"tenant_id": "globalbank"},
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert r.json().get("recommendations") == []

    def test_threat_intel_zero(self, admin_headers):
        r = requests.get(f"{API}/dashboard/threat-intel",
                         params={"tenant_id": "globalbank"},
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200
        body = r.json()
        # Endpoint may return total_advisories directly or nested
        total = body.get("total_advisories")
        if total is None and isinstance(body.get("summary"), dict):
            total = body["summary"].get("total_advisories")
        assert total == 0, f"expected 0 advisories, got {total}; body keys={list(body.keys())}"


# ---------------- 3. live path ----------------
class TestLivePathAfterUpload:
    def test_upload_xsoar_and_live_dashboards(self, admin_headers):
        assert os.path.exists(XSOAR_CSV), f"missing {XSOAR_CSV}"
        with open(XSOAR_CSV, "rb") as f:
            files = {"file": ("xsoar_sample.csv", f, "text/csv")}
            r = requests.post(
                f"{API}/upload/data",
                params={"source": "xsoar", "tenant_id": "acme-corp"},
                files=files, headers=admin_headers, timeout=30,
            )
        assert r.status_code == 200, r.text[:300]

        # Executive live
        r = requests.get(f"{API}/dashboard/executive",
                         params={"tenant_id": "acme-corp"},
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200
        exec_data = r.json()
        assert exec_data.get("data_status") == "live"
        assert isinstance(exec_data.get("recommendations"), list) and len(exec_data["recommendations"]) > 0
        # sanity: incidents/sla/detection_coverage should be populated
        assert exec_data.get("incidents") or exec_data.get("kpis")

        # Client live
        r = requests.get(f"{API}/dashboard/client",
                         params={"tenant_id": "acme-corp"},
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200
        client_data = r.json()
        assert client_data.get("data_status") == "live"
        # scorecard present under some key
        has_scorecard = any(k in client_data for k in ("scorecard", "client_scorecard", "kpis"))
        assert has_scorecard, f"expected scorecard-like structure; keys={list(client_data.keys())}"

        # Detection live
        r = requests.get(f"{API}/dashboard/detection-engineering",
                         params={"tenant_id": "acme-corp"},
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200
        det = r.json()
        assert det.get("data_status") == "live"
        assert det.get("mitre_heatmap") or det.get("mitre_coverage")
        rules = det.get("rules") or det.get("rule_effectiveness") or []
        assert any("powershell" in (str(rule).lower()) for rule in rules), (
            f"expected Suspicious PowerShell rule; got {rules}"
        )


# ---------------- 4. pptx export ----------------
class TestPPTXExport:
    def test_pptx_empty_tenant(self, admin_headers):
        r = requests.get(f"{API}/export/pptx",
                         params={"tenant_id": "all"},
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.content[:2] == b"PK", "not a valid pptx (zip) file"
        assert len(r.content) > 5000

    def test_pptx_live_tenant(self, admin_headers):
        # ensure acme-corp has data from previous test — re-upload just in case
        with open(XSOAR_CSV, "rb") as f:
            requests.post(f"{API}/upload/data",
                          params={"source": "xsoar", "tenant_id": "acme-corp"},
                          files={"file": ("xsoar_sample.csv", f, "text/csv")},
                          headers=admin_headers, timeout=30)
        r = requests.get(f"{API}/export/pptx",
                         params={"tenant_id": "acme-corp"},
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.content[:2] == b"PK"


# ---------------- 5. scheduled reports ----------------
class TestScheduledReports:
    def test_create_run_delete(self, admin_headers):
        payload = {
            "name": "TEST_live_only_sched",
            "frequency": "weekly",
            "recipients": ["TEST_livesched@example.com"],
            "tenant_id": "all",
            "enabled": True,
        }
        r = requests.post(f"{API}/reports/schedules", json=payload,
                          headers=admin_headers, timeout=15)
        assert r.status_code in (200, 201), r.text[:300]
        sched = r.json()
        sid = sched.get("id") or sched.get("_id") or sched.get("schedule_id")
        assert sid

        try:
            r = requests.post(f"{API}/reports/schedules/{sid}/run-now",
                              headers=admin_headers, timeout=45)
            assert r.status_code == 200, r.text[:300]
            body = r.json()
            assert body.get("ran") is True or body.get("ok") is True
            # console mode
            mode = body.get("mode") or body.get("delivery_mode")
            if mode is not None:
                assert mode == "console"

            # email history should have a .pptx attachment for this recipient
            r = requests.get(f"{API}/email/history",
                             headers=admin_headers, timeout=15)
            assert r.status_code == 200
            hist = r.json()
            items = hist if isinstance(hist, list) else hist.get("items", [])
            match = [
                h for h in items
                if "TEST_livesched@example.com" in str(h.get("to", h.get("recipients", "")))
            ]
            assert match, "no email history entry for TEST_livesched@example.com"
            attachments = match[0].get("attachments") or match[0].get("attachment_names") or []
            assert any(".pptx" in str(a).lower() for a in attachments), (
                f"expected pptx attachment, got {attachments}"
            )
        finally:
            requests.delete(f"{API}/reports/schedules/{sid}",
                            headers=admin_headers, timeout=15)


# ---------------- 6. IRIS copilot fallback ----------------
class TestIRISCopilotFallback:
    def test_iris_no_data_no_crash(self, admin_headers):
        # Use globalbank which has no data
        payload = {"tenant_id": "globalbank",
                   "message": "What is the highest false positive rate rule?"}
        r = requests.post(f"{API}/copilot/chat", json=payload,
                          headers=admin_headers, timeout=45)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("source") == "rule"
        assert isinstance(body.get("answer") or body.get("reply") or body.get("message"), str)
