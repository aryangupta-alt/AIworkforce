import asyncio
import sys
import os
import json
from queue import Queue
from threading import Thread
from typing import Optional
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

from api.settings_manager import load_settings, save_settings, check_schedule_action
from api.email_sender import send_email_with_pdf, generate_pdf

PIPELINE_DIR = Path(__file__).resolve().parent.parent

if os.environ.get("VERCEL"):
    REPORT_HTML = Path("/tmp/workforce_report.html")
    REPORT_PDF = Path("/tmp/workforce_report.pdf")
else:
    REPORT_HTML = PIPELINE_DIR / "reports" / "workforce_report.html"
    REPORT_PDF = PIPELINE_DIR / "reports" / "workforce_report.pdf"

import io
import sys
from contextlib import redirect_stdout, redirect_stderr

class Tee:
    def __init__(self, stream1, stream2):
        self.stream1 = stream1
        self.stream2 = stream2
    def write(self, data):
        self.stream1.write(data)
        self.stream2.write(data)
    def flush(self):
        self.stream1.flush()
        self.stream2.flush()


def _run_pipeline_sync():
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

    with redirect_stdout(Tee(sys.stdout, f_out)), redirect_stderr(Tee(sys.stderr, f_err)):
        try:
            run_extraction()
            run_audit()
            generate_report()
            ok = True
        except (SystemExit, RuntimeError) as e:
            print(f"[PIPELINE] {type(e).__name__}: {e}", file=f_err)
            ok = False
        except Exception:
            import traceback
            traceback.print_exc(file=f_err)
            ok = False

    return ok, f_out.getvalue(), f_err.getvalue()


def _run_stage(stage_fn):
    """Run a single pipeline stage synchronously, capturing output."""
    f_out = io.StringIO()
    f_err = io.StringIO()
    ok = False
    with redirect_stdout(Tee(sys.stdout, f_out)), redirect_stderr(Tee(sys.stderr, f_err)):
        try:
            stage_fn()
            ok = True
        except (SystemExit, RuntimeError) as e:
            print(f"[PIPELINE] {type(e).__name__}: {e}", file=f_err)
        except Exception:
            import traceback
            traceback.print_exc(file=f_err)
    return ok, f_out.getvalue(), f_err.getvalue()


class _QueuedStream:
    """A file-like wrapper that forwards to the original stdout and pushes lines to a queue."""
    def __init__(self, orig, queue):
        self.orig = orig
        self.queue = queue
        self.linebuf = ""

    def write(self, data):
        self.orig.write(data)
        self.linebuf += data
        while "\n" in self.linebuf:
            line, self.linebuf = self.linebuf.split("\n", 1)
            self.queue.put({"type": "log", "line": line})

    def flush(self):
        self.orig.flush()

    def close(self):
        self.flush()


def _run_stage_streamed_target(stage_fn, queue, stage_name):
    """Thread target that runs a stage and yields log lines through the queue."""
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    stream = _QueuedStream(orig_stdout, queue)
    err_stream = _QueuedStream(orig_stderr, queue)

    full_out = io.StringIO()
    full_err = io.StringIO()
    ok = False

    try:
        sys.stdout = Tee(stream, full_out)
        sys.stderr = Tee(err_stream, full_err)
        try:
            stage_fn()
            ok = True
        except (SystemExit, RuntimeError) as e:
            print(f"[PIPELINE] {type(e).__name__}: {e}", file=sys.stderr)
        except Exception:
            import traceback
            traceback.print_exc(file=sys.stderr)
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        if stream.linebuf:
            queue.put({"type": "log", "line": stream.linebuf})
        if err_stream.linebuf:
            queue.put({"type": "log", "line": err_stream.linebuf})
        queue.put({"type": "done", "ok": ok, "stdout": full_out.getvalue(), "stderr": full_err.getvalue()})


async def _stream_stage(stage_fn, stage_name):
    """Async generator that runs a stage in a thread and yields log events."""
    queue: Queue = Queue()
    thread = Thread(target=_run_stage_streamed_target, args=(stage_fn, queue, stage_name), daemon=True)
    thread.start()

    while thread.is_alive() or not queue.empty():
        try:
            item = queue.get(timeout=0.2)
        except Exception:
            await asyncio.sleep(0.1)
            continue

        if item["type"] == "log":
            yield {"type": "log", "line": item["line"]}
        elif item["type"] == "done":
            ok = item["ok"]
            if not ok:
                yield {"type": "error", "message": item["stderr"] or item["stdout"] or f"{stage_name} failed"}
            thread.join(timeout=1)
            break

    if thread.is_alive():
        thread.join(timeout=5)


def _import_stages():
    """Import all pipeline stage functions. Returns (success, stages_dict, error_msg)."""
    if str(PIPELINE_DIR) not in sys.path:
        sys.path.insert(0, str(PIPELINE_DIR))
    try:
        from drive_extract import run_extraction
        from llm_analysis import run_audit
        from report_service import generate_report
        return True, {
            "drive_extract": run_extraction,
            "llm_analysis": run_audit,
            "report_service": generate_report,
        }, ""
    except ImportError as e:
        return False, {}, str(e)


def _scheduled_job():
    settings = load_settings()
    print(f"[SCHEDULER] Poll at {datetime.now().isoformat()} | active={settings.get('active')} | next_run={settings.get('next_run')} | last_run={settings.get('last_run')}")

    if not check_schedule_action(settings):
        return

    print(f"[SCHEDULER] Triggering pipeline...")
    ok, out, err = _run_pipeline_sync()
    if not ok:
        print(f"[SCHEDULER] Pipeline failed: {err or out}")
        return

    recipients = settings.get("recipients", [])
    if not recipients:
        print(f"[SCHEDULER] No recipients configured, skipping email.")
    else:
        print(f"[SCHEDULER] Sending email to {recipients}...")
        result = send_email_with_pdf(
            recipients=recipients,
            subject=settings.get("subject", "Company Workforce Report"),
            body_line=settings.get("body_line", "Please find the attached report."),
            html_path=str(REPORT_HTML),
            pdf_path=str(REPORT_PDF),
        )
        print(f"[SCHEDULER] Email result: {result}")

    now = datetime.now()
    settings["last_run"] = now.isoformat()

    if settings.get("continuous"):
        interval = settings.get("interval_hours", 24)
        next_run = settings.get("next_run")
        if next_run:
            try:
                dt = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
                # If old next_run was in the past, jump to the next future slot
                base = max(now, dt)
                settings["next_run"] = (base + timedelta(hours=interval)).isoformat()
            except Exception:
                pass
    else:
        settings["active"] = False

    save_settings(settings)
    print(f"[SCHEDULER] Saved settings. next_run={settings.get('next_run')} | active={settings.get('active')}")


scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    scheduler.add_job(_scheduled_job, "interval", minutes=1, id="poll_schedule")
    yield
    scheduler.shutdown()

app = FastAPI(title="Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──
@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Pipeline Status ──
@app.get("/api/pipeline-status")
def pipeline_status():
    """
    Return the current state of each stage based on output files on disk.
    Used by the frontend to show already-completed stages before streaming starts.
    """
    return {
        "drive_extract": {
            "completed": EXTRACTED_JSON.exists(),
            "output_files": _stage_output_files("drive_extract"),
        },
        "llm_analysis": {
            "completed": ANALYSIS_JSON.exists(),
            "output_files": _stage_output_files("llm_analysis"),
        },
        "report_service": {
            "completed": REPORT_HTML.exists(),
            "output_files": _stage_output_files("report_service"),
        },
    }


# ── Output file paths for stage completion reporting ──
EXTRACTED_JSON = PIPELINE_DIR / "all_files_extracted_data.json"
ANALYSIS_JSON  = PIPELINE_DIR / "data" / "workforce_analysis_output.json"


def _stage_output_files(stage_id: str) -> list[dict]:
    """Return which expected output files exist for a given stage."""
    if stage_id == "drive_extract":
        return [{"name": str(EXTRACTED_JSON.relative_to(PIPELINE_DIR)), "exists": EXTRACTED_JSON.exists(), "size": EXTRACTED_JSON.stat().st_size if EXTRACTED_JSON.exists() else 0}]
    if stage_id == "llm_analysis":
        return [{"name": str(ANALYSIS_JSON.relative_to(PIPELINE_DIR)), "exists": ANALYSIS_JSON.exists(), "size": ANALYSIS_JSON.stat().st_size if ANALYSIS_JSON.exists() else 0}]
    if stage_id == "report_service":
        return [{"name": str(REPORT_HTML.relative_to(PIPELINE_DIR)), "exists": REPORT_HTML.exists(), "size": REPORT_HTML.stat().st_size if REPORT_HTML.exists() else 0}]
    return []


@app.post("/api/run-pipeline")
async def run_pipeline(request: Request):
    print("RUN PIPELINE HIT")
    async def event_stream():
        ok, stages_map, err = _import_stages()
        if not ok:
            yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'failed', 'message': f'Import error: {err}'})}\n\n"
            return

        stage_labels = [
            ("drive_extract", "Fetching Excel from Google Drive"),
            ("llm_analysis", "LLM Analysis"),
            ("report_service", "Generating HTML Report"),
        ]

        for stage_id, stage_name in stage_labels:
            yield f"data: {json.dumps({'stage': stage_id, 'status': 'running', 'message': stage_name})}\n\n"
            await asyncio.sleep(0.05)

            stage_fn = stages_map[stage_id]
            async for ev in _stream_stage(stage_fn, stage_name):
                if ev["type"] == "log":
                    yield f"data: {json.dumps({'stage': stage_id, 'status': 'running', 'message': ev['line']})}\n\n"
                elif ev["type"] == "error":
                    yield f"data: {json.dumps({'stage': stage_id, 'status': 'error', 'message': ev['message']})}\n\n"
                    yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'failed', 'message': ev['message']})}\n\n"
                    return

            yield "data: " + json.dumps({"stage": stage_id, "status": "completed", "message": f"{stage_name} ✓", "output_files": _stage_output_files(stage_id)}) + "\n\n"
            await asyncio.sleep(0.05)

        yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'success', 'message': 'Pipeline completed'})}\n\n"

    return StreamingResponse(
        event_stream(), 
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@app.post("/api/generate-report")
async def generate_report_only():
    """Regenerate the HTML report from the existing analysis JSON (skip Drive + LLM)."""
    print("GENERATE REPORT HIT")
    async def event_stream():
        ok, stages_map, err = _import_stages()
        if not ok:
            yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'failed', 'message': f'Import error: {err}'})}\n\n"
            return

        # Mark earlier stages as skipped
        for stage_id, stage_name in [
            ("drive_extract", "Fetching Excel from Google Drive"),
            ("llm_analysis", "LLM Analysis"),
        ]:
            yield f"data: {json.dumps({'stage': stage_id, 'status': 'completed', 'message': f'{stage_name} — skipped (report-only mode)', 'output_files': _stage_output_files(stage_id)})}\n\n"
            await asyncio.sleep(0.05)

        # Run only report_service with live logs
        stage_id, stage_name = "report_service", "Generating HTML Report"
        yield f"data: {json.dumps({'stage': stage_id, 'status': 'running', 'message': stage_name})}\n\n"
        await asyncio.sleep(0.05)

        stage_fn = stages_map[stage_id]
        async for ev in _stream_stage(stage_fn, stage_name):
            if ev["type"] == "log":
                yield f"data: {json.dumps({'stage': stage_id, 'status': 'running', 'message': ev['line']})}\n\n"
            elif ev["type"] == "error":
                yield f"data: {json.dumps({'stage': stage_id, 'status': 'error', 'message': ev['message']})}\n\n"
                yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'failed', 'message': ev['message']})}\n\n"
                return

        yield f"data: {json.dumps({'stage': stage_id, 'status': 'completed', 'message': f'{stage_name} ✓', 'output_files': _stage_output_files(stage_id)})}\n\n"
        await asyncio.sleep(0.05)

        yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'success', 'message': 'Report generated successfully'})}\n\n"

    return StreamingResponse(
        event_stream(), 
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
class RunAndEmailPayload(BaseModel):
    recipients: list[str] = []
    subject: str = "Company Workforce Report"
    body_line: str = "Dear Team,\n\nPlease find the attached Company Workforce Report for your review."

@app.post("/api/run-and-email")
async def run_and_email(request: Request, payload: RunAndEmailPayload):
    recipients = payload.recipients
    subject = payload.subject
    body_line = payload.body_line

    async def event_stream():
        ok, stages_map, err = _import_stages()
        if not ok:
            yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'failed', 'message': f'Import error: {err}'})}\n\n"
            return

        stage_labels = [
            ("drive_extract", "Fetching Excel from Google Drive"),
            ("llm_analysis", "LLM Analysis"),
            ("report_service", "Generating HTML Report"),
        ]

        for stage_id, stage_name in stage_labels:
            yield f"data: {json.dumps({'stage': stage_id, 'status': 'running', 'message': stage_name})}\n\n"
            await asyncio.sleep(0.05)

            stage_fn = stages_map[stage_id]
            ok, stdout, stderr = await asyncio.to_thread(_run_stage, stage_fn)

            if not ok:
                yield f"data: {json.dumps({'stage': stage_id, 'status': 'error', 'message': stderr or stdout or f'{stage_name} failed'})}\n\n"
                yield f"data: {json.dumps({'stage': 'pipeline', 'status': 'failed', 'message': stderr or stdout or f'{stage_name} failed'})}\n\n"
                return

            yield "data: " + json.dumps({"stage": stage_id, "status": "completed", "message": f"{stage_name} ✓", "output_files": _stage_output_files(stage_id)}) + "\n\n"
            await asyncio.sleep(0.05)

        yield "data: " + json.dumps({"stage": "pipeline", "status": "success", "message": "Report generated successfully"}) + "\n\n"
        await asyncio.sleep(0.2)

        if not recipients:
            yield "data: " + json.dumps({"stage": "email", "status": "failed", "message": "No recipients selected."}) + "\n\n"
            return

        yield "data: " + json.dumps({"stage": "email", "status": "running", "message": "Sending email via SMTP..."}) + "\n\n"
        await asyncio.sleep(0.05)

        result = await asyncio.to_thread(
            send_email_with_pdf,
            recipients=recipients,
            subject=subject,
            body_line=body_line,
            html_path=str(REPORT_HTML),
            pdf_path=str(REPORT_PDF),
        )

        if result.get("success"):
            msg = f'Email sent to {", ".join(recipients)}'
            yield f"data: {json.dumps({'stage': 'email', 'status': 'success', 'message': msg})}\n\n"
        else:
            yield f"data: {json.dumps({'stage': 'email', 'status': 'failed', 'message': result.get('error', 'Email sending failed')})}\n\n"

    return StreamingResponse(
        event_stream(), 
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@app.post("/api/send-email")
async def send_email_only(payload: RunAndEmailPayload):
    if not payload.recipients:
        return JSONResponse({"success": False, "error": "No recipients selected."}, status_code=400)
    
    result = send_email_with_pdf(
        recipients=payload.recipients,
        subject=payload.subject,
        body_line=payload.body_line,
        html_path=str(REPORT_HTML),
        pdf_path=str(REPORT_PDF),
    )
    return result


# ── Report ──
@app.get("/api/report")
def get_report():
    if not REPORT_HTML.exists():
        return JSONResponse({"detail": "Report not found. Run pipeline first."}, status_code=404)
    with open(REPORT_HTML, "r", encoding="utf-8") as f:
        content = f.read()
    return JSONResponse({"html": content})


# ── Settings ──
class SettingsPayload(BaseModel):
    recipients: list[str] = []
    next_run: Optional[str] = None
    stop_run: Optional[str] = None
    continuous: bool = False
    active: bool = False
    subject: str = "Company report"
    body_line: str = "Please find the attached company workforce report."
    interval_hours: int = 24

@app.get("/api/settings")
def get_settings():
    return load_settings()

@app.post("/api/settings")
def update_settings(payload: SettingsPayload):
    old_settings = load_settings()
    was_active = old_settings.get("active", False)
    settings = payload.dict()
    settings["last_run"] = old_settings.get("last_run")
    if payload.active and not was_active:
        settings["last_run"] = None
    save_settings(settings)
    return {"status": "ok", "settings": settings}


# ── Root ──
@app.get("/")
def root():
    if REPORT_HTML.exists():
        return FileResponse(str(REPORT_HTML))
    return {"message": "Pipeline API is running."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)