"""MSSP SOC Dashboard - Backend API pytest suite.

Covers:
  - Auth (login, /me, invalid creds, unauthorized access)
  - Dashboard endpoints for all 6 personas x 3 time periods
  - CSV / Excel upload with all valid sources + invalid source
  - Data-shape assertions (KPIs, charts, tables, recommendations)
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for pytest environment where frontend env vars aren't loaded
    from dotenv import load_dotenv
    load_dotenv("/app/frontend/.env")
    BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Admin@2026!"

PERSONA_CREDS = [
    ("soc.manager@mssp-soc.io", "SocManager@2026!", "soc_manager"),
    ("client@mssp-soc.io", "Client@2026!", "client"),
    ("detection@mssp-soc.io", "Detection@2026!", "detection_engineer"),
    ("ti.analyst@mssp-soc.io", "TiAnalyst@2026!", "ti_analyst"),
    ("automation@mssp-soc.io", "Automation@2026!", "automation_engineer"),
]

PERIODS = ["weekly", "monthly", "quarterly"]

DASH_ENDPOINTS = [
    "/dashboard/executive",
    "/dashboard/soc-manager",
    "/dashboard/client",
    "/dashboard/detection-engineering",
    "/dashboard/threat-intel",
    "/dashboard/soar-automation",
]


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api_client):
    r = api_client.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- Health ----------
class TestHealth:
    def test_root(self, api_client):
        r = api_client.get(f"{API}/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["service"] == "mssp-soc-dashboard"


# ---------- Auth ----------
class TestAuth:
    def test_admin_login_success(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        d = r.json()
        assert "access_token" in d and isinstance(d["access_token"], str) and len(d["access_token"]) > 20
        assert d["email"] == ADMIN_EMAIL
        assert d["role"] == "admin"

    def test_invalid_credentials(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_unknown_email(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={"email": "nope@x.io", "password": "whatever"})
        assert r.status_code == 401

    def test_me_with_bearer(self, api_client, auth_headers):
        r = api_client.get(f"{API}/auth/me", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN_EMAIL
        assert d["role"] == "admin"
        assert "password_hash" not in d
        assert "_id" not in d
        assert "id" in d

    def test_me_without_token(self, api_client):
        # Use bare requests, not the session (which may retain cookies)
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_dashboard_requires_auth(self):
        for ep in DASH_ENDPOINTS:
            r = requests.get(f"{API}{ep}")
            assert r.status_code == 401, f"{ep} should require auth"

    @pytest.mark.parametrize("email,password,role", PERSONA_CREDS)
    def test_persona_login(self, api_client, email, password, role):
        r = api_client.post(f"{API}/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, f"Persona {email} login failed: {r.text}"
        d = r.json()
        assert d["role"] == role
        assert "access_token" in d


# ---------- Dashboards ----------
class TestDashboards:
    @pytest.mark.parametrize("endpoint", DASH_ENDPOINTS)
    @pytest.mark.parametrize("period", PERIODS)
    def test_endpoint_period(self, api_client, auth_headers, endpoint, period):
        r = api_client.get(f"{API}{endpoint}?period={period}", headers=auth_headers)
        assert r.status_code == 200, f"{endpoint}?period={period} -> {r.status_code} {r.text[:200]}"
        d = r.json()
        assert isinstance(d, dict)
        assert len(d) > 0

    def test_invalid_period(self, api_client, auth_headers):
        r = api_client.get(f"{API}/dashboard/executive?period=daily", headers=auth_headers)
        assert r.status_code == 400

    def test_executive_shape(self, api_client, auth_headers):
        r = api_client.get(f"{API}/dashboard/executive?period=monthly", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        # Core executive fields
        for k in ["sla_compliance", "mttr_hours", "detection_coverage", "automation_rate",
                  "health_score", "risk_score", "recommendations"]:
            assert k in d, f"missing key {k}"
        # Recommendations shape
        recs = d["recommendations"]
        assert isinstance(recs, list) and len(recs) > 0
        rec = recs[0]
        for k in ["priority", "tag", "area", "title", "insight", "action"]:
            assert k in rec
        assert rec["priority"] in {"P1", "P2", "P3", "P4"}

    def test_soc_manager_shape(self, api_client, auth_headers):
        r = api_client.get(f"{API}/dashboard/soc-manager?period=monthly", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        # Endpoint is XSOAR-upload driven: empty payload OR full sla/speed_metrics shape
        if d.get("data_status") == "empty":
            assert "upload" in d
        else:
            assert "sla" in d and "speed_metrics" in d and "detection_health" in d

    def test_detection_engineering_shape(self, api_client, auth_headers):
        r = api_client.get(f"{API}/dashboard/detection-engineering?period=monthly", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert "gap_analysis" in d

    def test_threat_intel_shape(self, api_client, auth_headers):
        r = api_client.get(f"{API}/dashboard/threat-intel?period=monthly", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        # Upload-driven: accept empty or full-landscape shape
        if d.get("data_status") == "empty" or (d.get("summary", {}).get("total_advisories") == 0):
            assert "summary" in d
        else:
            assert "landscape" in d and "effectiveness" in d

    def test_soar_shape(self, api_client, auth_headers):
        r = api_client.get(f"{API}/dashboard/soar-automation?period=monthly", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        if d.get("data_status") == "empty":
            assert "upload" in d
        else:
            assert "efficiency" in d

    def test_client_shape(self, api_client, auth_headers):
        r = api_client.get(f"{API}/dashboard/client?period=monthly", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict) and len(d) > 0

    def test_period_variation(self, api_client, auth_headers):
        """Weekly, monthly, quarterly should produce distinct numbers."""
        results = {}
        for p in PERIODS:
            r = api_client.get(f"{API}/dashboard/executive?period={p}", headers=auth_headers)
            assert r.status_code == 200
            results[p] = r.json().get("sla_compliance")
        # At least two out of three should differ (deterministic per-period hash)
        distinct = len(set(results.values()))
        assert distinct >= 2, f"Period variation weak: {results}"

    def test_no_mongo_objectid_leaks(self, api_client, auth_headers):
        for ep in DASH_ENDPOINTS:
            r = api_client.get(f"{API}{ep}?period=monthly", headers=auth_headers)
            d = r.json()
            # Recursively check no "_id" key exists in response
            def _check(obj):
                if isinstance(obj, dict):
                    assert "_id" not in obj, f"MongoDB _id leaked in {ep}"
                    for v in obj.values():
                        _check(v)
                elif isinstance(obj, list):
                    for v in obj:
                        _check(v)
            _check(d)


# ---------- Upload ----------
class TestUpload:
    CSV_SAMPLE = (
        "offense_id,severity,rule,description\n"
        "1001,High,Impossible Travel Login,Login from two countries\n"
        "1002,Medium,PowerShell Encoded,Encoded PS command\n"
        "1003,Critical,Data Exfil,Outbound >100MB\n"
    )

    @pytest.mark.parametrize("source", ["qradar", "xsoar", "threat_intel"])
    def test_upload_csv_all_sources(self, admin_token, source):
        files = {"file": ("test.csv", io.BytesIO(self.CSV_SAMPLE.encode()), "text/csv")}
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/upload/data?source={source}", files=files, headers=headers)
        assert r.status_code == 200, f"{source}: {r.status_code} {r.text}"
        d = r.json()
        assert d["source"] == source
        assert d["rows"] == 3
        assert len(d["columns"]) == 4
        assert "offense_id" in d["columns"]

    def test_upload_invalid_source(self, admin_token):
        files = {"file": ("test.csv", io.BytesIO(self.CSV_SAMPLE.encode()), "text/csv")}
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/upload/data?source=badsrc", files=files, headers=headers)
        assert r.status_code == 400

    def test_upload_unsupported_file(self, admin_token):
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{API}/upload/data?source=qradar", files=files, headers=headers)
        assert r.status_code == 400

    def test_upload_requires_auth(self):
        files = {"file": ("test.csv", io.BytesIO(self.CSV_SAMPLE.encode()), "text/csv")}
        r = requests.post(f"{API}/upload/data?source=qradar", files=files)
        assert r.status_code == 401

    def test_upload_history(self, api_client, auth_headers):
        r = api_client.get(f"{API}/upload/history", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, list)
        # After previous upload tests, at least one record should exist
        assert len(d) >= 1
        # Ensure MongoDB "_id" object key is not leaked (record has no _id key)
        assert all("_id" not in rec for rec in d)
