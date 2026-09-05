"""MSSP SOC KPI Dashboard - Backend API."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import base64
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from auth import (
    VALID_ROLES,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    seed_admin,
    set_auth_cookies,
    verify_password,
)
import emailer
import llm as llm_mod
import copilot as iris
import mock_data
import pptx_export
import recommendations
import tenants as tenants_mod
import ti_ingest
import xsoar_ingest
import rules_ingest
import logval_ingest
import scheduler as report_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("mssp-soc")

mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

app = FastAPI(title="MSSP SOC KPI Dashboard")

# CORS BEFORE include_router
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    role: str = "client"


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class TenantBody(BaseModel):
    domain: str
    name: str
    description: Optional[str] = ""
    primary_color: Optional[str] = "#3B82F6"
    logo_url: Optional[str] = None


class BrandingBody(BaseModel):
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class SendEmailBody(BaseModel):
    to: List[EmailStr]
    subject: str
    html: str
    tenant_id: Optional[str] = "all"
    period: Optional[str] = "monthly"
    attach_pptx: Optional[bool] = True


class IrisChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: Optional[str] = None
    tenant_id: Optional[str] = "all"
    period: Optional[str] = "monthly"


class ReportScheduleBody(BaseModel):
    tenant_id: Optional[str] = "all"
    period: Optional[str] = "monthly"
    frequency: str  # "weekly" | "monthly"
    recipients: List[EmailStr]
    subject: Optional[str] = None
    enabled: Optional[bool] = True


async def seed_tenants():
    """Seed the default tenants (idempotent)."""
    for t in tenants_mod.DEFAULT_TENANTS:
        existing = await db.tenants.find_one({"id": t["id"]})
        if not existing:
            doc = {**t, "created_at": datetime.now(timezone.utc).isoformat()}
            await db.tenants.insert_one(doc)


async def get_tenant(tenant_id: Optional[str]) -> dict:
    tid = tenant_id or "all"
    t = await db.tenants.find_one({"id": tid}, {"_id": 0})
    if not t:
        # fallback to default all
        return {"id": "all", "name": "All Tenants", "domain": "ALL", "primary_color": "#3B82F6", "logo_url": None}
    return t


@app.on_event("startup")
async def _startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.tenants.create_index("id", unique=True)
    await db.iris_messages.create_index([("session_id", 1), ("created_at", 1)])
    await db.iris_messages.create_index([("user_id", 1), ("created_at", -1)])
    await db.ti_rows.create_index([("tenant_id", 1), ("date", -1)])
    await db.ti_uploads.create_index([("tenant_id", 1), ("uploaded_at", -1)])
    await db.xsoar_rows.create_index([("tenant_id", 1), ("occurred", -1)])
    await db.xsoar_uploads.create_index([("tenant_id", 1), ("uploaded_at", -1)])
    await seed_admin(db)
    await seed_tenants()

    creds_path = Path("/app/memory/test_credentials.md")
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text(
        "# MSSP SOC Dashboard - Test Credentials\n\n"
        "## Admin\n"
        f"- Email: `{os.environ.get('ADMIN_EMAIL')}`\n"
        f"- Password: `{os.environ.get('ADMIN_PASSWORD')}`\n"
        "- Role: `admin`\n"
    )
    logger.info("Startup complete: admin + tenants seeded.")

    # Kick off local LLM (Ollama) preload/pull in the background.
    llm_mod.preload_async()

    await db.report_schedules.create_index("id", unique=True)
    report_scheduler.start(db)


@app.on_event("shutdown")
async def _shutdown():
    report_scheduler.shutdown()
    mongo_client.close()


# ---------- Auth ----------
async def current_user_dep(request: Request):
    return await get_current_user(request, db)


@api.post("/auth/register")
async def register(body: RegisterBody, response: Response):
    email = body.email.lower()
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {
        "email": email,
        "password_hash": hash_password(body.password),
        "name": body.name,
        "role": body.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.users.insert_one(doc)
    uid = str(result.inserted_id)
    access = create_access_token(uid, email, body.role)
    refresh = create_refresh_token(uid)
    set_auth_cookies(response, access, refresh)
    return {"id": uid, "email": email, "name": body.name, "role": body.role, "access_token": access}


@api.post("/auth/login")
async def login(body: LoginBody, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    uid = str(user["_id"])
    access = create_access_token(uid, email, user["role"])
    refresh = create_refresh_token(uid)
    set_auth_cookies(response, access, refresh)
    return {"id": uid, "email": email, "name": user["name"], "role": user["role"], "access_token": access}


@api.post("/auth/logout")
async def logout(response: Response, user=Depends(current_user_dep)):
    clear_auth_cookies(response)
    return {"ok": True}


@api.get("/auth/me")
async def me(user=Depends(current_user_dep)):
    return user


# ---------- Tenants ----------
@api.get("/tenants")
async def list_tenants(user=Depends(current_user_dep)):
    docs = await db.tenants.find({}, {"_id": 0}).to_list(200)
    return docs


@api.post("/tenants")
async def create_tenant(body: TenantBody, user=Depends(current_user_dep)):
    tid = body.name.lower().replace(" ", "-").replace("_", "-")[:40]
    if await db.tenants.find_one({"id": tid}):
        raise HTTPException(status_code=400, detail="Tenant already exists")
    doc = {
        "id": tid,
        "domain": body.domain.upper(),
        "name": body.name,
        "description": body.description or "",
        "primary_color": body.primary_color or "#3B82F6",
        "logo_url": body.logo_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "risk_modifier": 1.0,
        "volume_modifier": 1.0,
    }
    await db.tenants.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, body: BrandingBody, user=Depends(current_user_dep)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.tenants.update_one({"id": tenant_id}, {"$set": updates})
    return await get_tenant(tenant_id)


@api.post("/tenants/{tenant_id}/logo")
async def upload_logo(tenant_id: str, file: UploadFile = File(...), user=Depends(current_user_dep)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Must be an image file")
    contents = await file.read()
    if len(contents) > 512 * 1024:
        raise HTTPException(status_code=400, detail="Image must be < 512 KB")
    data_url = f"data:{file.content_type};base64,{base64.b64encode(contents).decode()}"
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"logo_url": data_url}})
    return {"logo_url": data_url[:80] + "…"}


@api.post("/tenants/upload-csv")
async def upload_tenants_csv(file: UploadFile = File(...), user=Depends(current_user_dep)):
    """Bulk-load tenants from a CSV export of QRadar domains.

    Expected columns: domain, name, description (optional), primary_color (optional).
    """
    contents = await file.read()
    name = (file.filename or "").lower()
    try:
        df = pd.read_csv(io.BytesIO(contents)) if name.endswith(".csv") else pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)[:120]}")
    df.columns = [c.lower().strip() for c in df.columns]
    if "domain" not in df.columns or "name" not in df.columns:
        raise HTTPException(status_code=400, detail="CSV must have 'domain' and 'name' columns")
    added = 0
    for _, row in df.iterrows():
        tid = str(row["name"]).lower().replace(" ", "-")[:40]
        if not tid or await db.tenants.find_one({"id": tid}):
            continue
        await db.tenants.insert_one({
            "id": tid,
            "domain": str(row["domain"]).upper(),
            "name": str(row["name"]),
            "description": str(row.get("description", "")) if "description" in df.columns else "",
            "primary_color": str(row.get("primary_color", "#3B82F6")) if "primary_color" in df.columns else "#3B82F6",
            "logo_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "risk_modifier": 1.0,
            "volume_modifier": 1.0,
        })
        added += 1
    return {"added": added, "total_rows": len(df)}


# ---------- Dashboards ----------
def _period(period: Optional[str]) -> str:
    p = (period or "monthly").lower()
    if p not in mock_data.PERIODS:
        raise HTTPException(status_code=400, detail="Invalid period")
    return p


async def _live_executive(p: str, tenant_id: str) -> dict:
    """Assemble the Executive Overview purely from live uploads (XSOAR + TI +
    detection overlay). Returns {'data_status': 'empty'} when nothing is uploaded."""
    roll = await xsoar_ingest.compute_executive_rollup(db, tenant_id)
    overlay = await xsoar_ingest.compute_detection_overlay(db, tenant_id)
    ti = await ti_ingest.compute_dashboard(db, tenant_id=tenant_id, period=p)
    has_xsoar = roll.get("data_status") == "live"
    has_ti = ti.get("data_status") == "live"
    if not has_xsoar and not has_ti:
        return {"data_status": "empty", "period": p}

    sla = roll.get("sla_compliance") or 0
    fp = roll.get("false_positive_rate") or 0
    auto = roll.get("automation_rate") or 0
    mttr = roll.get("mttr_hours") or 0
    det_cov = overlay.get("mitre_coverage") if overlay.get("data_status") == "live" else 0
    health = round(max(0.0, min(100.0, 0.5 * sla + 0.3 * auto + 0.2 * det_cov)), 1)
    risk = round(max(0.0, min(100.0, 0.5 * fp + 0.3 * (100 - sla) + 0.2 * min(100, mttr))), 1)

    exec_payload = {
        "data_status": "live",
        "period": p,
        "health_score": health,
        "risk_score": risk,
        "incidents": roll.get("incidents") or 0,
        "offenses": 0,
        "sla_compliance": sla,
        "mttr_hours": mttr,
        "detection_coverage": det_cov,
        "automation_rate": auto,
        "advisories": ti["summary"]["total_advisories"] if has_ti else 0,
        "false_positive_rate": fp,
        "top_threat_actor": roll.get("top_mitre_tactic") or "—",
        "top_targeted_asset": "—",
        "incident_trend": roll.get("incident_trend") or [],
        "sla_trend": roll.get("sla_trend") or [],
        "top_rule": roll.get("top_rule"),
        "top_mitre_tactic": roll.get("top_mitre_tactic"),
    }
    if has_xsoar:
        exec_payload["xsoar_live"] = True
        exec_payload["xsoar_upload"] = roll.get("upload")
    return exec_payload


@api.get("/dashboard/executive")
async def executive(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    p = _period(period)
    exec_d = await _live_executive(p, tenant_id)
    if exec_d.get("data_status") != "live":
        return {"data_status": "empty", "period": p, "recommendations": []}
    recs = recommendations.generate(exec_d)
    return {**exec_d, "recommendations": recs}


@api.get("/dashboard/soc-manager")
async def dashboard_soc(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    return await xsoar_ingest.compute_soc_manager(db, tenant_id=tenant_id)


@api.delete("/dashboard/soc-manager/data")
async def dashboard_soc_clear(tenant_id: str = "all", user=Depends(current_user_dep)):
    await db.xsoar_rows.delete_many({"tenant_id": tenant_id})
    await db.xsoar_uploads.delete_many({"tenant_id": tenant_id})
    return {"cleared": True, "tenant_id": tenant_id}


@api.get("/dashboard/client")
async def dashboard_client(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    cl = await xsoar_ingest.compute_client(db, tenant_id)
    if cl.get("data_status") != "live":
        return {"data_status": "empty", "period": _period(period)}
    ti = await ti_ingest.compute_dashboard(db, tenant_id=tenant_id, period=_period(period))
    has_ti = ti.get("data_status") == "live"
    cl["period"] = _period(period)
    cl["threat_exposure"] = {
        "total_advisories": ti["summary"]["total_advisories"] if has_ti else 0,
        "threat_actors": [],
        "malware": [],
        "advisory_trend": (
            [{"date": x["date"], "value": x["advisories"]} for x in ti.get("advisories_timeline", [])]
            if has_ti else []
        ),
    }
    return cl


@api.get("/dashboard/detection-engineering")
async def dashboard_det(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    p = _period(period)
    xsoar_rows = await xsoar_ingest._rows(db, tenant_id)
    rules_res = await rules_ingest.compute_detection(db, tenant_id, xsoar_rows)
    overlay = await xsoar_ingest.compute_detection_overlay(db, tenant_id)
    logval = await logval_ingest.compute(db, tenant_id)

    has_rules = rules_res.get("data_status") == "live"
    has_overlay = overlay.get("data_status") == "live" and overlay.get("mitre_heatmap")
    has_logval = logval.get("data_status") == "live"
    if not (has_rules or has_overlay or has_logval):
        return {"data_status": "empty", "period": p}

    det = tenants_mod.detection_engineering(p, await get_tenant(tenant_id))
    det["data_status"] = "live"

    if has_rules:
        # Rule catalog drives MITRE coverage + rule effectiveness
        det["mitre_heatmap"] = rules_res["mitre_heatmap"]
        det["quality"] = rules_res["quality"]
        det["gap_analysis"]["techniques_covered"] = rules_res["techniques_covered"]
        det["gap_analysis"]["techniques_missing"] = rules_res["techniques_missing"]
        det["rule_effectiveness"] = rules_res["rule_effectiveness"]
        det["rules_upload"] = rules_res.get("upload")
    elif has_overlay:
        # Fall back to XSOAR-derived heat-map + FP rule table
        det["mitre_heatmap"] = overlay["mitre_heatmap"]
        det["rules"] = overlay["rules"]
        det["quality"]["mitre_coverage"] = overlay["mitre_coverage"]
        det["quality"]["detection_coverage"] = overlay["mitre_coverage"]
        det["gap_analysis"]["techniques_covered"] = overlay["techniques_covered"]

    if has_logval:
        det["priority_breakdown"] = logval["priority_breakdown"]
        det["logval_total"] = logval["total"]

    det["xsoar_live"] = bool(has_overlay)
    return det


@api.get("/dashboard/threat-intel")
async def dashboard_ti(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    return await ti_ingest.compute_dashboard(db, tenant_id=tenant_id, period=_period(period))


@api.get("/dashboard/threat-intel/upload-info")
async def dashboard_ti_upload_info(tenant_id: str = "all", user=Depends(current_user_dep)):
    return {"upload": await ti_ingest.latest_upload(db, tenant_id)}


@api.delete("/dashboard/threat-intel/data")
async def dashboard_ti_clear(tenant_id: str = "all", user=Depends(current_user_dep)):
    """Clear all uploaded threat-intel rows for a tenant (resets the dashboard)."""
    await db.ti_rows.delete_many({"tenant_id": tenant_id})
    await db.ti_uploads.delete_many({"tenant_id": tenant_id})
    return {"cleared": True, "tenant_id": tenant_id}


@api.delete("/dashboard/detection/rules-data")
async def dashboard_rules_clear(tenant_id: str = "all", user=Depends(current_user_dep)):
    """Clear the uploaded rule catalog for a tenant."""
    await rules_ingest.delete_data(db, tenant_id)
    return {"cleared": True, "tenant_id": tenant_id}


@api.delete("/dashboard/detection/logval-data")
async def dashboard_logval_clear(tenant_id: str = "all", user=Depends(current_user_dep)):
    """Clear the uploaded log-validation priority data for a tenant."""
    await logval_ingest.delete_data(db, tenant_id)
    return {"cleared": True, "tenant_id": tenant_id}



@api.get("/dashboard/soar-automation")
async def dashboard_soar(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    return await xsoar_ingest.compute_soar(db, tenant_id=tenant_id)


# ---------- AI / LLM ----------
@api.get("/ai/status")
async def ai_status(user=Depends(current_user_dep)):
    return llm_mod.status()


@api.get("/ai/insights")
async def ai_insights(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    p = _period(period)
    exec_d = await _live_executive(p, tenant_id)
    if exec_d.get("data_status") != "live":
        return {"recommendations": [], "llm": llm_mod.status()}
    recs = recommendations.generate(exec_d)
    enriched = llm_mod.enrich_recommendations(recs, exec_d, max_llm=3)
    return {"recommendations": enriched, "llm": llm_mod.status()}


# ---------- Uploads ----------
@api.post("/upload/data")
async def upload_data(source: str, tenant_id: str = "all", file: UploadFile = File(...), user=Depends(current_user_dep)):
    if source not in {"qradar", "xsoar", "threat_intel", "rules", "log_validation"}:
        raise HTTPException(status_code=400, detail="Invalid source")
    contents = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif name.endswith(".xlsx") or name.endswith(".xls"):
            # Aggregate across ALL sheets so counts/columns reflect the whole workbook.
            sheets = pd.read_excel(io.BytesIO(contents), sheet_name=None)
            frames = [f for f in sheets.values() if f is not None and not f.empty]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        else:
            raise HTTPException(status_code=400, detail="File must be CSV or Excel")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)[:120]}")

    record = {
        "source": source,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "rows": len(df),
        "columns": list(df.columns.astype(str)),
        "uploaded_by": user.get("email"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "sample": df.head(5).fillna("").astype(str).to_dict(orient="records"),
    }
    await db.uploads.insert_one(record)
    record.pop("_id", None)

    # For threat_intel, also persist the normalised rows so they can drive
    # the Threat Intelligence dashboard KPIs directly.
    if source == "threat_intel":
        try:
            rows = ti_ingest.parse_rows(contents, file.filename or "")
            upload_id = await ti_ingest.save_upload(
                db, tenant_id=tenant_id,
                uploaded_by=user.get("email") or "",
                filename=file.filename or "upload",
                rows=rows,
            )
            record["ti_upload_id"] = upload_id
            record["ti_row_count"] = len(rows)
        except Exception as e:
            logger.exception("threat_intel row persistence failed")
            record["ti_ingest_error"] = str(e)[:200]

    # For xsoar, persist normalised incidents to drive SOC Manager /
    # SOAR / Executive dashboards live.
    if source == "xsoar":
        try:
            rows = xsoar_ingest.parse_rows(contents, file.filename or "")
            upload_id = await xsoar_ingest.save_upload(
                db, tenant_id=tenant_id,
                uploaded_by=user.get("email") or "",
                filename=file.filename or "upload",
                rows=rows,
            )
            record["xsoar_upload_id"] = upload_id
            record["xsoar_row_count"] = len(rows)
        except Exception as e:
            logger.exception("xsoar row persistence failed")
            record["xsoar_ingest_error"] = str(e)[:200]

    # Rule catalog → Detection Engineering (MITRE coverage + rule effectiveness)
    if source == "rules":
        try:
            rows = rules_ingest.parse_rows(contents, file.filename or "")
            await rules_ingest.save_upload(db, tenant_id, file.filename or "upload", rows)
            record["rules_row_count"] = len(rows)
        except Exception as e:
            logger.exception("rules row persistence failed")
            record["rules_ingest_error"] = str(e)[:200]

    # Log validation → Detection Engineering priority pie
    if source == "log_validation":
        try:
            rows = logval_ingest.parse_rows(contents, file.filename or "")
            await logval_ingest.save_upload(db, tenant_id, file.filename or "upload", rows)
            record["logval_row_count"] = len(rows)
        except Exception as e:
            logger.exception("log_validation row persistence failed")
            record["logval_ingest_error"] = str(e)[:200]

    # Surface what actually landed in a dashboard so the UI can give honest feedback.
    if source == "threat_intel":
        record["bound_rows"] = record.get("ti_row_count", 0)
        record["dashboard"] = "Threat Intelligence"
    elif source == "xsoar":
        record["bound_rows"] = record.get("xsoar_row_count", 0)
        record["dashboard"] = "SOC Manager / Detection / Executive"
    elif source == "rules":
        record["bound_rows"] = record.get("rules_row_count", 0)
        record["dashboard"] = "Detection Engineering (MITRE + Rule Effectiveness)"
    elif source == "log_validation":
        record["bound_rows"] = record.get("logval_row_count", 0)
        record["dashboard"] = "Detection Engineering (Log Priority)"
    else:  # qradar
        record["bound_rows"] = 0
        record["dashboard"] = None
        record["warning"] = (
            "QRadar files are stored but do not populate dashboards yet. "
            "Upload an XSOAR or Threat Intel export to see live data."
        )
    # If parsing raised, surface a concrete reason instead of a silent 0 rows.
    _ingest_err = next((record.get(k) for k in (
        "xsoar_ingest_error", "ti_ingest_error",
        "rules_ingest_error", "logval_ingest_error") if record.get(k)), None)
    if source in {"xsoar", "threat_intel", "rules", "log_validation"} and record["bound_rows"] == 0 and _ingest_err:
        record["error"] = f"Could not read this file: {_ingest_err}"
        record["warning"] = (
            "The file could not be parsed, so nothing was added to the dashboard. "
            "Please check the file format and try again."
        )
    elif source in {"xsoar", "threat_intel", "rules", "log_validation"} and record["bound_rows"] == 0:
        record["warning"] = (
            "0 rows matched the expected columns — nothing was added to the dashboard. "
            "Check that your file's column headers match the expected format."
        )
    record["bound_tenant_id"] = tenant_id

    return record


@api.get("/upload/history")
async def upload_history(user=Depends(current_user_dep)):
    cursor = db.uploads.find({}, {"_id": 0}).sort("uploaded_at", -1).limit(20)
    docs = await cursor.to_list(20)
    # Defensive: legacy pre-fix records may contain NaN floats in the sample
    # payload which crash the strict JSON encoder. Sanitize on read.
    import math
    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return ""
        if isinstance(v, dict):
            return {k: _clean(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_clean(x) for x in v]
        return v
    return [_clean(d) for d in docs]


# ---------- Export ----------
@api.get("/export/pptx")
async def export_pptx(period: str = "monthly", tenant_id: str = "all", user=Depends(current_user_dep)):
    p = _period(period)
    tenant, all_data, recs = await report_scheduler.build_bundle(db, p, tenant_id)
    buf = pptx_export.build_pptx(tenant, p, all_data, recs)
    filename = f"MSSP_SOC_{tenant.get('id','all')}_{p}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pptx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Email ----------
@api.post("/email/send")
async def send_email(body: SendEmailBody, user=Depends(current_user_dep)):
    p = _period(body.period)
    tenant = await get_tenant(body.tenant_id)
    attachments = []
    if body.attach_pptx:
        _t, all_data, recs = await report_scheduler.build_bundle(db, p, body.tenant_id)
        buf = pptx_export.build_pptx(tenant, p, all_data, recs)
        attachments.append({
            "filename": f"MSSP_SOC_{tenant.get('id','all')}_{p}.pptx",
            "data": buf.getvalue(),
        })

    return await emailer.send_email(
        db,
        to=[str(x) for x in body.to],
        subject=body.subject,
        html=body.html,
        attachments=attachments,
        meta={"tenant_id": body.tenant_id, "period": p, "sent_by": user.get("email")},
    )


@api.get("/email/history")
async def email_history(user=Depends(current_user_dep)):
    cursor = db.emails.find({}, {"attachments.content_b64": 0}).sort("sent_at", -1).limit(50)
    docs = await cursor.to_list(50)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


# ---------- IRIS Copilot (grounded chat) ----------
@api.get("/copilot/status")
async def copilot_status(user=Depends(current_user_dep)):
    st = llm_mod.status()
    return {
        "name": "IRIS",
        "full_name": "Intelligent Response & Insight System",
        "model": st["model"],
        "ready": st["loaded"],
        "loading": st["loading"],
        "suggestions": iris.SUGGESTED_QUESTIONS,
    }


@api.post("/copilot/chat")
async def copilot_chat(body: IrisChatBody, user=Depends(current_user_dep)):
    p = _period(body.period)
    tenant = await get_tenant(body.tenant_id)
    session_id = body.session_id or str(ObjectId())

    # Inject live XSOAR KPIs (rule FP rates, top rules) into IRIS grounding.
    soc_live = await xsoar_ingest.compute_soc_manager(db, tenant_id=body.tenant_id)
    live_xsoar = None
    if soc_live.get("data_status") == "live":
        live_xsoar = {
            "data_status": "live",
            "summary": soc_live.get("summary"),
            "noisy_rules_by_fp": soc_live.get("noisy_rules"),
            "top_rules": soc_live.get("top_rules"),
        }

    # Load recent history for this session (last 10 messages)
    hist_cursor = db.iris_messages.find(
        {"session_id": session_id, "user_id": user["id"]},
        {"_id": 0, "role": 1, "content": 1},
    ).sort("created_at", -1).limit(10)
    history = list(reversed(await hist_cursor.to_list(10)))

    result = iris.answer(body.message, p, tenant, history, live_xsoar)

    now = datetime.now(timezone.utc).isoformat()
    await db.iris_messages.insert_many([
        {
            "session_id": session_id,
            "user_id": user["id"],
            "role": "user",
            "content": body.message,
            "tenant_id": tenant.get("id"),
            "period": p,
            "created_at": now,
        },
        {
            "session_id": session_id,
            "user_id": user["id"],
            "role": "assistant",
            "content": result["answer"],
            "source": result["source"],
            "tenant_id": tenant.get("id"),
            "period": p,
            "created_at": now,
        },
    ])

    return {
        "session_id": session_id,
        "answer": result["answer"],
        "source": result["source"],
        "model": result["model"],
        "tenant_name": result["tenant_name"],
        "created_at": now,
    }


@api.get("/copilot/history")
async def copilot_history(session_id: str = Query(...), user=Depends(current_user_dep)):
    cursor = db.iris_messages.find(
        {"session_id": session_id, "user_id": user["id"]},
        {"_id": 0, "user_id": 0},
    ).sort("created_at", 1).limit(100)
    return await cursor.to_list(100)


@api.get("/copilot/sessions")
async def copilot_sessions(user=Depends(current_user_dep)):
    pipeline = [
        {"$match": {"user_id": user["id"]}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$session_id",
            "last_message": {"$first": "$content"},
            "last_role": {"$first": "$role"},
            "last_at": {"$first": "$created_at"},
            "tenant_id": {"$first": "$tenant_id"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": 20},
    ]
    docs = await db.iris_messages.aggregate(pipeline).to_list(20)
    return [
        {
            "session_id": d["_id"],
            "preview": (d.get("last_message") or "")[:80],
            "last_at": d.get("last_at"),
            "tenant_id": d.get("tenant_id"),
            "messages": d.get("count", 0),
        }
        for d in docs
    ]


# ---------- Scheduled Reports ----------
@api.get("/reports/schedules")
async def list_report_schedules(user=Depends(current_user_dep)):
    return await db.report_schedules.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api.post("/reports/schedules")
async def create_report_schedule(body: ReportScheduleBody, user=Depends(current_user_dep)):
    if body.frequency not in {"weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="frequency must be weekly or monthly")
    _period(body.period)
    if not body.recipients:
        raise HTTPException(status_code=400, detail="At least one recipient required")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": body.tenant_id or "all",
        "period": body.period or "monthly",
        "frequency": body.frequency,
        "recipients": [str(x) for x in body.recipients],
        "subject": body.subject,
        "enabled": bool(body.enabled),
        "created_by": user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "last_status": None,
    }
    await db.report_schedules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/reports/schedules/{schedule_id}")
async def update_report_schedule(schedule_id: str, body: ReportScheduleBody, user=Depends(current_user_dep)):
    if body.frequency not in {"weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="frequency must be weekly or monthly")
    _period(body.period)
    updates = {
        "tenant_id": body.tenant_id or "all",
        "period": body.period or "monthly",
        "frequency": body.frequency,
        "recipients": [str(x) for x in body.recipients],
        "subject": body.subject,
        "enabled": bool(body.enabled),
    }
    r = await db.report_schedules.update_one({"id": schedule_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return await db.report_schedules.find_one({"id": schedule_id}, {"_id": 0})


@api.delete("/reports/schedules/{schedule_id}")
async def delete_report_schedule(schedule_id: str, user=Depends(current_user_dep)):
    await db.report_schedules.delete_many({"id": schedule_id})
    return {"deleted": True, "id": schedule_id}


@api.post("/reports/schedules/{schedule_id}/run-now")
async def run_report_schedule_now(schedule_id: str, user=Depends(current_user_dep)):
    try:
        res = await report_scheduler.run_now(db, schedule_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"ran": True, "mode": res.get("mode"), "delivered": res.get("delivered"),
            "recipients": res.get("to")}


# ---------- Comparison / Snapshots ----------
async def _snapshot_kpis(period: str, tenant_id: str) -> dict:
    """Capture a flat, comparable KPI set across all dashboards (live values)."""
    exec_d = await _live_executive(period, tenant_id)
    xsoar_rows = await xsoar_ingest._rows(db, tenant_id)
    det = await rules_ingest.compute_detection(db, tenant_id, xsoar_rows)
    ti = await ti_ingest.compute_dashboard(db, tenant_id=tenant_id, period=period)
    overlay = await xsoar_ingest.compute_detection_overlay(db, tenant_id)

    q = det.get("quality", {}) if det.get("data_status") == "live" else {}
    re = det.get("rule_effectiveness", {}) if det.get("data_status") == "live" else {}
    exl = exec_d if exec_d.get("data_status") == "live" else {}

    return {
        "incidents": exl.get("incidents", 0),
        "sla_compliance": exl.get("sla_compliance", 0),
        "mttr_hours": exl.get("mttr_hours", 0),
        "automation_rate": exl.get("automation_rate", 0),
        "risk_score": exl.get("risk_score", 0),
        "health_score": exl.get("health_score", 0),
        "false_positive_rate": exl.get("false_positive_rate", 0),
        "advisories": (ti["summary"]["total_advisories"] if ti.get("data_status") == "live" else 0),
        "mitre_coverage": q.get("mitre_coverage", overlay.get("mitre_coverage", 0) if overlay.get("data_status") == "live" else 0),
        "detection_coverage": q.get("detection_coverage", exl.get("detection_coverage", 0)),
        "quality_score": q.get("quality_score", 0),
        "rules_triggered": re.get("triggered_rules", 0),
        "total_rules": re.get("total_rules", 0),
    }


@api.post("/comparison/snapshot")
async def create_snapshot(period: str = "weekly", tenant_id: str = "all", label: Optional[str] = None,
                          user=Depends(current_user_dep)):
    if period not in ("weekly", "monthly", "quarterly"):
        raise HTTPException(status_code=400, detail="period must be weekly, monthly or quarterly")
    p = period
    kpis = await _snapshot_kpis(_period(p), tenant_id)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id or "all",
        "period": p,
        "label": label,
        "kpis": kpis,
        "created_by": user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.snapshots.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/comparison/snapshots")
async def list_snapshots(period: str = "weekly", tenant_id: str = "all", user=Depends(current_user_dep)):
    return await db.snapshots.find(
        {"tenant_id": tenant_id or "all", "period": period}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)


@api.get("/comparison/compare")
async def compare_snapshots(period: str = "weekly", tenant_id: str = "all", user=Depends(current_user_dep)):
    snaps = await db.snapshots.find(
        {"tenant_id": tenant_id or "all", "period": period}, {"_id": 0}
    ).sort("created_at", -1).to_list(2)
    if not snaps:
        return {"period": period, "current": None, "previous": None, "deltas": {}}
    current = snaps[0]
    previous = snaps[1] if len(snaps) > 1 else None
    deltas = {}
    for k, cur in current["kpis"].items():
        prev = (previous["kpis"].get(k) if previous else None)
        delta = round(cur - prev, 2) if prev is not None else None
        pct = (round(100.0 * delta / prev, 1) if (prev not in (None, 0) and delta is not None) else None)
        deltas[k] = {"current": cur, "previous": prev, "delta": delta, "pct": pct}
    return {"period": period, "current": current, "previous": previous, "deltas": deltas}


@api.delete("/comparison/snapshot/{snapshot_id}")
async def delete_snapshot(snapshot_id: str, user=Depends(current_user_dep)):
    await db.snapshots.delete_many({"id": snapshot_id})
    return {"deleted": True, "id": snapshot_id}


# ---------- Health ----------
@api.get("/")
async def root():
    return {"service": "mssp-soc-dashboard", "status": "ok"}


@api.get("/health")
async def health():
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


app.include_router(api)
