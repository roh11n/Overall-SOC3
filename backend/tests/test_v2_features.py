"""MSSP SOC v2 feature tests: tenants, AI/LLM, PPTX export, email delivery.

Extends /app/backend/tests/backend_test.py with iteration-2 endpoints.
"""
import io
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
# Heavy endpoints (PPTX+LLM) take 60-70s per call. Cloudflare ingress has ~100s
# timeout and returns 502 under any burst. We hit localhost for those endpoints
# so the backend logic is validated even when the public ingress is slow. The
# ingress issue is documented in the test report as a HIGH priority action item.
LOCAL_API = "http://localhost:8001/api"

ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Admin@2026!"


@pytest.fixture(scope="module")
def token():
    # Try public API first, fall back to localhost on Cloudflare 502 (heavy parallel load)
    last_exc = None
    for base in (API, LOCAL_API):
        for _ in range(3):
            try:
                r = requests.post(f"{base}/auth/login",
                                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                                  timeout=30)
                if r.status_code == 200:
                    return r.json()["access_token"]
                last_exc = AssertionError(f"login {base} -> {r.status_code}: {r.text[:100]}")
            except Exception as e:
                last_exc = e
            time.sleep(2)
    raise last_exc or AssertionError("Could not obtain admin token")


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Tenants ----------
class TestTenants:
    def test_list_tenants_requires_auth(self):
        # Use localhost to avoid intermittent Cloudflare 502 that masks 401
        r = requests.get(f"{LOCAL_API}/tenants")
        assert r.status_code == 401

    def test_list_default_tenants(self, h):
        r = requests.get(f"{API}/tenants", headers=h)
        assert r.status_code == 200
        docs = r.json()
        assert isinstance(docs, list)
        ids = {d["id"] for d in docs}
        assert {"all", "acme-corp", "globalbank"}.issubset(ids), f"Missing seeded tenants: {ids}"
        for d in docs:
            assert "primary_color" in d
            assert "domain" in d
            assert "_id" not in d

    def test_create_tenant(self, h):
        payload = {"domain": "TEST_DOMAIN_1", "name": "TEST Tenant One",
                   "description": "unit", "primary_color": "#123456"}
        r = requests.post(f"{API}/tenants", json=payload, headers=h)
        if r.status_code == 400:
            # Already exists from prior run — verify via GET instead
            lst = requests.get(f"{API}/tenants", headers=h).json()
            found = [x for x in lst if x["id"] == "test-tenant-one"]
            assert found, "test-tenant-one should exist"
            assert found[0]["domain"] == "TEST_DOMAIN_1"
            return
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] == "test-tenant-one"
        assert d["domain"] == "TEST_DOMAIN_1"
        assert d["primary_color"] == "#123456"
        assert "_id" not in d
        # verify persistence
        lst = requests.get(f"{API}/tenants", headers=h).json()
        assert any(x["id"] == "test-tenant-one" for x in lst)

    def test_create_tenant_duplicate(self, h):
        payload = {"domain": "DUP", "name": "TEST Tenant One"}
        r = requests.post(f"{API}/tenants", json=payload, headers=h)
        assert r.status_code == 400

    def test_patch_tenant_updates_branding(self, h):
        r = requests.patch(f"{API}/tenants/test-tenant-one",
                           json={"primary_color": "#ABCDEF"}, headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["primary_color"] == "#ABCDEF"
        # verify persisted
        lst = requests.get(f"{API}/tenants", headers=h).json()
        found = [x for x in lst if x["id"] == "test-tenant-one"][0]
        assert found["primary_color"] == "#ABCDEF"

    def test_upload_logo(self, h):
        # 1x1 PNG
        png = bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
            "0000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
        )
        files = {"file": ("logo.png", io.BytesIO(png), "image/png")}
        r = requests.post(f"{API}/tenants/test-tenant-one/logo",
                          files=files,
                          headers={"Authorization": h["Authorization"]})
        assert r.status_code == 200, r.text
        assert "logo_url" in r.json()

    def test_upload_logo_rejects_non_image(self, h):
        files = {"file": ("logo.txt", io.BytesIO(b"not an image"), "text/plain")}
        r = requests.post(f"{API}/tenants/test-tenant-one/logo", files=files,
                          headers={"Authorization": h["Authorization"]})
        assert r.status_code == 400

    def test_upload_tenants_csv(self, h):
        csv = "domain,name,description,primary_color\nTEST_D1,TEST Bulk A,desc a,#111111\nTEST_D2,TEST Bulk B,desc b,#222222\n"
        files = {"file": ("tenants.csv", io.BytesIO(csv.encode()), "text/csv")}
        r = requests.post(f"{API}/tenants/upload-csv", files=files,
                          headers={"Authorization": h["Authorization"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_rows"] == 2
        # depending on prior runs added may be 0 (both already exist) — assert either added > 0 OR both exist now
        lst = requests.get(f"{API}/tenants", headers=h).json()
        ids = {x["id"] for x in lst}
        assert d["added"] >= 0
        assert "test-bulk-a" in ids and "test-bulk-b" in ids

    def test_upload_tenants_csv_missing_columns(self, h):
        csv = "foo,bar\n1,2\n"
        files = {"file": ("x.csv", io.BytesIO(csv.encode()), "text/csv")}
        r = requests.post(f"{API}/tenants/upload-csv", files=files,
                          headers={"Authorization": h["Authorization"]})
        assert r.status_code == 400


# ---------- Tenant-scoped dashboards ----------
class TestTenantScopedDashboards:
    def test_executive_all_vs_acme_differ(self, h):
        r_all = requests.get(f"{API}/dashboard/executive?period=monthly&tenant_id=all", headers=h).json()
        r_acme = requests.get(f"{API}/dashboard/executive?period=monthly&tenant_id=acme-corp", headers=h).json()
        assert r_all["incidents"] != r_acme["incidents"] or r_all["offenses"] != r_acme["offenses"], \
            "acme-corp should differ from All Tenants"
        assert r_acme.get("tenant", {}).get("id") == "acme-corp"

    def test_executive_acme_vs_globalbank_differ(self, h):
        r_a = requests.get(f"{API}/dashboard/executive?period=monthly&tenant_id=acme-corp", headers=h).json()
        r_g = requests.get(f"{API}/dashboard/executive?period=monthly&tenant_id=globalbank", headers=h).json()
        assert (r_a["incidents"], r_a["risk_score"]) != (r_g["incidents"], r_g["risk_score"])

    def test_unknown_tenant_falls_back_to_all(self, h):
        r = requests.get(f"{API}/dashboard/executive?period=monthly&tenant_id=nope-xyz", headers=h)
        assert r.status_code == 200  # graceful fallback


# ---------- AI / HuggingFace LLM ----------
class TestAI:
    def test_ai_status(self, h):
        r = requests.get(f"{API}/ai/status", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["model"] == "HuggingFaceTB/SmolLM2-360M-Instruct"
        assert "loaded" in d
        assert isinstance(d["loaded"], bool)

    def test_ai_status_requires_auth(self):
        r = requests.get(f"{API}/ai/status")
        assert r.status_code == 401

    def test_ai_insights_returns_reasoning(self, h):
        # Model may take 15-30s per justification, and 3 by default. Route to
        # localhost to avoid the ~100s ingress timeout on the public URL.
        r = requests.get(f"{LOCAL_API}/ai/insights?period=monthly&tenant_id=acme-corp",
                         headers=h, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "recommendations" in d
        assert "llm" in d
        recs = d["recommendations"]
        assert isinstance(recs, list) and len(recs) > 0
        for rec in recs:
            assert "reasoning" in rec
            assert "reasoning_source" in rec
            assert rec["reasoning_source"] in {"hf-llm", "rule"}
        # If model is loaded, at least one should be hf-llm
        if d["llm"].get("loaded"):
            hf_count = sum(1 for r in recs if r["reasoning_source"] == "hf-llm")
            assert hf_count >= 1, "Expected at least one hf-llm reasoning when model is loaded"


# ---------- PPTX Export ----------
class TestPPTX:
    def test_export_pptx_all_tenants(self, h):
        r = requests.get(f"{LOCAL_API}/export/pptx?period=monthly&tenant_id=all",
                         headers={"Authorization": h["Authorization"]}, timeout=180)
        assert r.status_code == 200, r.text[:200]
        ctype = r.headers.get("content-type", "")
        assert "presentationml" in ctype, f"Wrong content-type: {ctype}"
        content = r.content
        assert len(content) > 50 * 1024, f"PPTX too small: {len(content)} bytes"
        # Valid ZIP -> starts with PK
        assert content[:2] == b"PK", "PPTX file is not a valid ZIP"
        # Contains slide XML
        assert b"ppt/slides/slide" in content

    def test_export_pptx_acme_branding(self, h):
        r = requests.get(f"{LOCAL_API}/export/pptx?period=monthly&tenant_id=acme-corp",
                         headers={"Authorization": h["Authorization"]}, timeout=180)
        assert r.status_code == 200
        content = r.content
        assert content[:2] == b"PK"
        assert len(content) > 50 * 1024
        # Verify slide count using zipfile
        import zipfile
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            slides = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            assert len(slides) >= 5, f"Expected >5 slides, got {len(slides)}"

    def test_export_pptx_filename(self, h):
        r = requests.get(f"{LOCAL_API}/export/pptx?period=weekly&tenant_id=globalbank",
                         headers={"Authorization": h["Authorization"]}, timeout=180)
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "MSSP_SOC_globalbank_weekly_" in cd, f"Bad filename: {cd}"
        assert cd.endswith('.pptx"')

    def test_export_pptx_requires_auth(self):
        r = requests.get(f"{API}/export/pptx?period=monthly&tenant_id=all")
        assert r.status_code == 401


# ---------- Email ----------
class TestEmail:
    def test_send_email_console_mode(self, h):
        body = {
            "to": ["test-recipient@example.com"],
            "subject": "TEST_Monthly SOC Report",
            "html": "<p>Body content</p>",
            "tenant_id": "acme-corp",
            "period": "monthly",
            "attach_pptx": True,
        }
        r = requests.post(f"{LOCAL_API}/email/send", json=body, headers=h, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["mode"] == "console"  # SMTP not configured
        assert d["delivered"] is False
        assert d["to"] == body["to"]
        assert d["subject"] == body["subject"]
        assert isinstance(d["attachments"], list) and len(d["attachments"]) == 1
        att = d["attachments"][0]
        assert att["filename"].endswith(".pptx")
        assert att["size"] > 50 * 1024

    def test_send_email_no_attachment(self, h):
        body = {
            "to": ["a@b.io"],
            "subject": "TEST_no attach",
            "html": "<p>hi</p>",
            "attach_pptx": False,
        }
        r = requests.post(f"{LOCAL_API}/email/send", json=body, headers=h, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["attachments"] == []

    def test_email_history_returns_records(self, h):
        r = requests.get(f"{API}/email/history", headers=h)
        assert r.status_code == 200
        docs = r.json()
        assert isinstance(docs, list)
        assert len(docs) >= 1
        # Should have prior TEST_ emails
        subjects = [d.get("subject", "") for d in docs]
        assert any("TEST_" in s for s in subjects)
        # attachments should be metadata-only (content_b64 stripped)
        for d in docs:
            for att in d.get("attachments", []):
                assert "content_b64" not in att, "content_b64 should be excluded from history"

    def test_email_send_requires_auth(self):
        r = requests.post(f"{API}/email/send",
                          json={"to": ["a@b.io"], "subject": "s", "html": "h"})
        assert r.status_code == 401
