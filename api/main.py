import asyncio
import sys
import os
import json
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Request, BackgroundTasks
# pyrefly: ignore [missing-import]
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

from api.settings_manager import load_settings, save_settings, check_schedule_action
from api.email_sender import send_email_with_pdf, generate_pdf

PIPELINE_DIR = Path(__file__).resolve().parent.parent
import tempfile

if os.environ.get("VERCEL"):
    TMP_DIR = tempfile.gettempdir()
    os.environ["DOWNLOAD_FOLDER"] = TMP_DIR
    os.environ["OUTPUT_JSON_FILE"] = f"{TMP_DIR}/all_files_extracted_data.json"
    os.environ["INPUT_FILE"] = f"{TMP_DIR}/all_files_extracted_data.json"
    os.environ["OUTPUT_FILE"] = f"{TMP_DIR}/workforce_analysis_output.json"
    REPORT_HTML = Path(TMP_DIR) / "workforce_report.html"
    os.environ["REPORT_HTML"] = str(REPORT_HTML)
    REPORT_PDF = Path(TMP_DIR) / "workforce_report.pdf"
else:
    REPORT_HTML = PIPELINE_DIR / "reports" / "workforce_report.html"
    REPORT_PDF = PIPELINE_DIR / "reports" / "workforce_report.pdf"

import io
from contextlib import redirect_stdout, redirect_stderr

def _run_pipeline_sync():
    """Run the Python pipeline directly."""
    # Ensure PIPELINE_DIR is in sys.path
    if str(PIPELINE_DIR) not in sys.path:
        sys.path.insert(0, str(PIPELINE_DIR))
        
    try:
        from drive_extract import run_extraction
        from llm_analysis import run_audit
        from report_service import generate_report
    except ImportError as e:
        return False, "", str(e)

    f_out = io.StringIO()
    f_err = io.StringIO()
    ok = False

    with redirect_stdout(f_out), redirect_stderr(f_err):
        try:
            run_extraction()
            run_audit()
            generate_report()
            ok = True
        except SystemExit:
            # llm_analysis.py calls sys.exit(1) on errors - catch it
            ok = False
        except Exception as e:
            import traceback
            traceback.print_exc(file=f_err)
            ok = False

    return ok, f_out.getvalue(), f_err.getvalue()


def _generate_report_pdf():
    if not REPORT_HTML.exists():
        ok, _, _ = _run_pipeline_sync()
        if not ok:
            return False
    if not REPORT_HTML.exists():
        return False
    ok = generate_pdf(str(REPORT_HTML), str(REPORT_PDF))
    return ok


def _scheduled_job():
    settings = load_settings()
    if not check_schedule_action(settings):
        return

    # Generation Phase
    ok = _generate_report_pdf()
    if not ok:
        return

    # Sending Phase
    recipients = settings.get("recipients", [])
    if not recipients:
        return

    send_email_with_pdf(
        recipients=recipients,
        subject=settings.get("subject", "Company report"),
        body_line=settings.get("body_line", "Please find the attached company workforce report."),
        html_path=str(REPORT_HTML),
        pdf_path=str(REPORT_PDF),
    )
        
    # Reset state after sending
    settings["last_run"] = datetime.now().isoformat()

    # Calculate next_run
    if settings.get("continuous"):
        cron_expr = settings.get("cron_expression")
        if cron_expr:
            try:
                from croniter import croniter
                now_local = datetime.now()
                cron = croniter(cron_expr, now_local)
                next_t = cron.get_next(datetime)
                settings["next_run"] = next_t.isoformat()
            except Exception:
                pass
        else:
            interval = settings.get("interval_hours", 24)
            next_run = settings.get("next_run")
            if next_run:
                try:
                    dt = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
                    settings["next_run"] = (dt + timedelta(hours=interval)).isoformat()
                except Exception:
                    pass
    else:
        settings["active"] = False

    save_settings(settings)

# Removed BackgroundScheduler for Vercel Serverless
app = FastAPI(title="Pipeline API")

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://pipeline-three-flame.vercel.app",
    "https://*.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================
# Cron
# ===========================
CRON_SECRET = os.environ.get("CRON_SECRET", "")

@app.get("/api/cron")
async def handle_cron(request: Request):
    # Verify secret token if configured
    if CRON_SECRET:
        auth = request.headers.get("Authorization", "")
        token = request.query_params.get("token", "")
        if auth != f"Bearer {CRON_SECRET}" and token != CRON_SECRET:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    _scheduled_job()
    return JSONResponse({"status": "cron completed"})

# ===========================
# Health
# ===========================
@app.get("/health")
def health():
    return {"status": "ok"}


# ===========================
# Pipeline Runner (SSE)
# ===========================
@app.post("/api/run-pipeline")
async def run_pipeline(request: Request, background_tasks: BackgroundTasks):
    async def event_stream():
        stages = [
            ("drive_extract", "Fetching Excel from Google Drive"),
            ("llm_analysis", "LLM Analysis"),
            ("report_service", "Generating HTML Report"),
        ]

        for stage_id, stage_name in stages:
            yield f"data: {json.dumps({'stage': stage_id, 'status': 'running', 'message': stage_name})}\n\n"
            await asyncio.sleep(0.2)

        ok, stdout, stderr = _run_pipeline_sync()

        if not ok:
            yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'failed', 'message': stderr or stdout})}\n\n"
            return

        # try to read generated html
        html_content = ""
        if REPORT_HTML.exists():
            with open(REPORT_HTML, "r", encoding="utf-8") as f:
                html_content = f.read()

        yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'success', 'html': html_content})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ===========================
# Report Serving
# ===========================
@app.get("/api/report")
def get_report():
    if not REPORT_HTML.exists():
        return JSONResponse({"detail": "Report not found. Run pipeline first."}, status_code=404)
    with open(REPORT_HTML, "r", encoding="utf-8") as f:
        content = f.read()
    return JSONResponse({"html": content})


@app.get("/api/report/download")
def download_report():
    if not REPORT_HTML.exists():
        return JSONResponse({"detail": "Report not found"}, status_code=404)
    return FileResponse(str(REPORT_HTML), media_type="text/html", filename="workforce_report.html")


# ===========================
# PDF
# ===========================
@app.post("/api/generate-pdf")
def generate_report_pdf_endpoint():
    ok = _generate_report_pdf()
    if ok:
        return {"success": True, "pdf_path": str(REPORT_PDF)}
    return JSONResponse({"success": False, "detail": "PDF generation failed"}, status_code=500)


@app.get("/api/pdf")
def download_pdf():
    if not REPORT_PDF.exists():
        return JSONResponse({"detail": "PDF not found"}, status_code=404)
    return FileResponse(str(REPORT_PDF), media_type="application/pdf", filename="workforce_report.pdf")


# ===========================
# Settings
# ===========================
class SettingsPayload(BaseModel):
    recipients: list[str] = []
    next_run: Optional[str] = None
    stop_run: Optional[str] = None
    continuous: bool = False
    active: bool = False
    subject: str = "Company report"
    body_line: str = "Please find the attached company workforce report."
    interval_hours: int = 24
    cron_expression: str = ""
    generation_done: bool = False


@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def update_settings(payload: SettingsPayload):
    old_settings = load_settings()
    was_active = old_settings.get("active", False)
    
    settings = payload.dict()
    # Keep existing last_run
    settings["last_run"] = old_settings.get("last_run")
    
    if payload.active and not was_active:
        # Force immediate run
        settings["last_run"] = None
        
    save_settings(settings)
    return {"status": "ok"}


# ===========================
# Send Email
# ===========================
class SendEmailPayload(BaseModel):
    recipients: list[str] = []
    subject: str = "Company report"
    body_line: str = "Please find the attached company workforce report."


@app.post("/api/send-email")
def send_email_endpoint(payload: SendEmailPayload):
    if not _generate_report_pdf():
        return JSONResponse({"success": False, "detail": "PDF generation failed"}, status_code=500)
    result = send_email_with_pdf(
        recipients=payload.recipients,
        subject=payload.subject,
        body_line=payload.body_line,
        html_path=str(REPORT_HTML),
        pdf_path=str(REPORT_PDF),
    )
    return result


# ===========================
# Static Report View
# ===========================
@app.get("/")
def root():
    if REPORT_HTML.exists():
        return FileResponse(str(REPORT_HTML))
    return {"message": "Pipeline API is running. Use /api/run-pipeline to generate report."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
