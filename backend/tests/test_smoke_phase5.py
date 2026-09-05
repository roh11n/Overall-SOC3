"""Phase-5 smoke tests: copilot, AI insights, PPTX export, tenants."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    from dotenv import load_dotenv
    load_dotenv("/app/frontend/.env")
    BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Admin@2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestTenants:
    def test_list_tenants(self, headers):
        r = requests.get(f"{API}/tenants", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        assert "id" in data[0] and "name" in data[0]
        # No _id leak
        assert all("_id" not in t for t in data)

    def test_tenants_requires_auth(self):
        r = requests.get(f"{API}/tenants")
        assert r.status_code == 401


class TestCopilot:
    def test_status(self, headers):
        r = requests.get(f"{API}/copilot/status", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "suggestions" in d
        assert isinstance(d["suggestions"], list) and len(d["suggestions"]) > 0

    def test_chat(self, headers):
        r = requests.post(
            f"{API}/copilot/chat",
            headers={**headers, "Content-Type": "application/json"},
            json={"message": "What is our current SLA compliance?"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # Response might have 'answer' or 'response' — check either
        assert any(k in d for k in ("answer", "response", "message", "reply")), f"No answer field: {d}"
        # 'source' may be 'rule' fallback (acceptable per PS)
        if "source" in d:
            assert d["source"] in ("rule", "llm", "hf", "model")


class TestAIInsights:
    def test_insights(self, headers):
        r = requests.get(f"{API}/ai/insights", headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # Should have recommendations or insights list
        assert isinstance(d, (list, dict))
        if isinstance(d, dict):
            has_data = any(isinstance(v, list) and len(v) > 0 for v in d.values())
            assert has_data, f"No insights payload: {d}"


class TestPPTXExport:
    def test_pptx_download(self, headers):
        r = requests.get(f"{API}/export/pptx", headers=headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        ctype = r.headers.get("content-type", "")
        assert "presentation" in ctype or "octet-stream" in ctype, f"unexpected ctype {ctype}"
        # PPTX = ZIP (starts with PK)
        assert r.content[:2] == b"PK", "Not a valid PPTX (missing PK header)"
        assert len(r.content) > 5000, f"PPTX too small ({len(r.content)} bytes)"
