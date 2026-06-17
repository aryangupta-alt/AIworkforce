# Repository Logging & Observability Audit Report

**Scope:** Full workforce-intelligence pipeline repository (`/Users/dhruv.solanki/Documents/pipeline`).
**Goal:** Identify every API entry point, route handler, FastAPI endpoint, middleware, scheduler job, external API integration, and background task, then describe current logging behavior, missing information, and recommended additions.
**Constraint:** No source code was modified.

---

## Executive Summary

The project is a FastAPI-backed automation pipeline that:
1. Downloads an Excel file from Google Drive.
2. Extracts all sheets to JSON.
3. Sends the data to an Ollama-hosted LLM (`deepseek-v4-flash:cloud`) for workforce auditing.
4. Renders an HTML/PDF report from a Jinja2 template.
5. Emails the report via SMTP.
6. Schedules reruns via APScheduler.
7. Exposes two UIs: a Next.js dashboard (`dashboard/`) and a legacy standalone viewer (`ui/index.html`).

**Logging maturity:** Low. Most modules use ad-hoc `print()` statements. FastAPI endpoints have almost no request/response logging. Sensitive values (passwords, API keys, full JSON payloads) are not consistently redacted. No structured logging, no request IDs, no timing metrics, and no centralized audit trail for automation state changes.

---

## 1. API Endpoints

### 1.1 FastAPI Application Bootstrap

| # | File | Function/Class | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 1.1.1 | `api/main.py:38-47` | `class Tee` (stdout/stderr tee) | None | It silently duplicates streams; callers cannot tell when capture starts/stops | Log when capture context is entered/exited and how many bytes were captured |
| 1.1.2 | `api/main.py:49-77` | `_run_pipeline_sync()` | Errors printed to captured `f_err` only; `print(f"[PIPELINE] {type(e).__name__}: {e}", file=f_err)` at line 70 | No structured log of stage start, success, duration, or stdout/stderr size | Log before/after each stage call with timing; log captured stdout/stderr length |
| 1.1.3 | `api/main.py:80-94` | `_run_stage()` | Errors printed to `f_err` only at lines 90, 93 | Same as above, per-stage | Log stage name, start timestamp, success/failure, duration, exception traceback length |
| 1.1.4 | `api/main.py:97-111` | `_import_stages()` | None | Import success/failure is not logged at API layer | Log imported modules, `sys.path`, and `ImportError` details |
| 1.1.5 | `api/main.py:162-169` | `scheduler` + `lifespan()` | `scheduler.start()` and `scheduler.add_job(...)` have no logs | Scheduler startup/shutdown is invisible | Log scheduler start, registered jobs, intervals, and shutdown |
| 1.1.6 | `api/main.py:171-179` | `CORSMiddleware` | None | No request/response logging | Add `AccessInfoMiddleware` to log method, path, origin, status, duration, request ID |

### 1.2 Health & Root

| # | Path | Method | Handler | File | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|---|---|
| 1.2.1 | `/health` | `GET` | `health()` | `api/main.py:183-185` | None | No request log | Log health-check caller IP/user-agent at `INFO` (rate-limited) |
| 1.2.2 | `/` | `GET` | `root()` | `api/main.py:367-371` | None | No file-hit/miss log | Log whether `FileResponse` or JSON was returned, report file size |

### 1.3 Pipeline Endpoints

| # | Path | Method | Handler | File | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|---|---|
| 1.3.1 | `/api/run-pipeline` | `POST` | `run_pipeline(request: Request)` | `api/main.py:205-240` | None at endpoint level; only SSE event messages | No request start/end log; no timing; no client IP; no payload size; import errors only emitted to SSE | Log request arrival, client info, SSE stream start/end, total stream duration, success/failure |
| 1.3.2 | `/api/run-and-email` | `POST` | `run_and_email(request: Request, payload: RunAndEmailPayload)` | `api/main.py:249-311` | Same as above | Same as above plus no recipient/ subject logging (security gap too) | Log request, masked recipient count, email result, and whether PDF was attached |
| 1.3.3 | `/api/send-email` | `POST` | `send_email_only(payload: RunAndEmailPayload)` | `api/main.py:314-326` | None | No request/response log; no recipient count; no timing; no SMTP result details | Log request, recipient count, attachment status, SMTP result or error, response status |
| 1.3.4 | `/api/report` | `GET` | `get_report()` | `api/main.py:330-336` | None | No access log; no file size on success | Log file path, size, and 404 cases |
| 1.3.5 | `/api/settings` | `GET` | `get_settings()` | `api/main.py:350-352` | None | No access log; no tamper detection | Log read event, caller, settings version/hash (exclude secrets) |
| 1.3.6 | `/api/settings` | `POST` | `update_settings(payload: SettingsPayload)` | `api/main.py:354-363` | None | No audit log of active/inactive transitions or schedule changes | Log pre/post state diff, who changed active/next_run, old vs new `last_run` reset |

### 1.4 Dashboard Frontend Fetch Calls

| # | File | Function | HTTP Call | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|---|
| 1.4.1 | `dashboard/app/page.tsx:131` | mount `useEffect` | `fetch('/api/report')` | Success updates UI; errors silently caught (`catch(() => {})`) | No log of fetch failure or non-200 | `console.error` / Sentry on failure; include HTTP status |
| 1.4.2 | `dashboard/app/page.tsx:144` | mount `useEffect` | `fetch('/api/settings')` | Same silent catch | Same | Same |
| 1.4.3 | `dashboard/app/page.tsx:180` | `runPipelineOnly()` | `fetch('/api/run-pipeline')` | UI status only; parse errors silently swallowed (`catch { /* ignore */ }`) | No log of network/SSE parse failures | Log SSE parse errors, connection drop, total duration |
| 1.4.4 | `dashboard/app/page.tsx:296` | `sendEmail()` | `fetch('/api/send-email')` | UI status on success/failure | No structured log of request/response | Log recipient count, success/error, response status |
| 1.4.5 | `dashboard/app/page.tsx:321` | `saveSettings()` | `fetch('/api/settings')` | UI status only | No log of payload or server response | Log settings mutation (exclude secrets), HTTP status, response active flag |

### 1.5 Legacy UI Fetch Calls

| # | File | Function | HTTP Call | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|---|
| 1.5.1 | `ui/index.html:939` | `runPipeline()` | `fetch('/api/run-pipeline')` | `console.warn` on SSE parse failure only | No request/response duration logs; backend 404 handled in UI only | Add `console.info` for start/end/duration; backend should log concurrently |
| 1.5.2 | `ui/index.html:939` | `runPipeline()` | SSE reader | `console.warn` on parse errors (lines 1010, 1049) | No log of successful stream close, total events, or duration | Log stream close, total events, final status |

---

## 2. Scheduler Jobs

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 2.1 | `api/main.py:114-159` | `_scheduled_job()` | Poll line: `print(f"[SCHEDULER] Poll at ... | active=... | next_run=... | last_run=...")` (line 116). Trigger line: line 121. Failure line: 124. Email line: 131. Result line: 139. Save line: 159. | No job ID or execution ID; no elapsed time; no decision reason when skipping; `check_schedule_action` result is not logged; exceptions inside `_run_pipeline_sync` may be swallowed; no persistent audit trail | Add `execution_id`, log `check_schedule_action` decision (why yes/no), log each sub-step duration, log scheduler settings diff before/after, persist run history |
| 2.2 | `api/main.py:162-169` | `scheduler` + `lifespan()` | None | APScheduler start/shutdown invisible | Log scheduler start, timezone, job store, registered job IDs, misfire/grace settings |
| 2.3 | `api/settings_manager.py:44-76` | `check_schedule_action()` | None | The function decides whether to run but never logs its reasoning | Log evaluation: active flag, next_run/stop_run parse results, computed decision, side effects like auto-deactivation |

### Recommended scheduler logging additions

```text
[SCHEDULER] execution_id=... job_id=poll_schedule poll_at=... active=... next_run=... stop_run=... last_run=...
[SCHEDULER] decision execution_id=... should_run=... reason="next_run reached" | "stop_run reached - deactivating" | "not active" | "next_run in future"
[SCHEDULER] pipeline_start execution_id=...
[SCHEDULER] pipeline_end execution_id=... success=... duration_sec=... stdout_bytes=... stderr_bytes=...
[SCHEDULER] email_start execution_id=... recipient_count=...
[SCHEDULER] email_end execution_id=... success=... duration_sec=...
[SCHEDULER] settings_persisted execution_id=... active=... next_run=... last_run=...
```

---

## 3. Email Sending Flows

### 3.1 SMTP Configuration

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 3.1.1 | `api/email_sender.py:11-20` | `_smtp_config()` | None | Configuration values (host, port, from_addr) are never logged | Log host/port/user at startup (redact password); warn if missing credentials |

### 3.2 PDF Generation

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 3.2.1 | `api/email_sender.py:23-63` | `generate_pdf()` | None | Each fallback attempt (Chrome, WeasyPrint, pdfkit) is silent | Log each renderer attempt, command, success/failure reason, duration, output file size |

### 3.3 Email Dispatch

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 3.3.1 | `api/email_sender.py:66-115` | `send_email_with_pdf()` | None | No request-level log before sending; SMTP exception logged only in returned dict | Log start, recipient count, subject, attachment type/size, SMTP host, duration; log specific SMTP exceptions; log success with message-id if available |

### Recommended email logging additions

```text
[EMAIL] start recipients=... subject="..." attachment_type=pdf|html attachment_size=... smtp_host=... smtp_port=...
[EMAIL] pdf_generation renderer=chrome result=success duration_sec=... pdf_size=...
[EMAIL] smtp_login user=... host=...
[EMAIL] send recipients=... from=...
[EMAIL] success duration_sec=...
[EMAIL] error error_type=SMTPAuthenticationError detail=...
```

**Security note:** Never log `EMAIL_PASSWORD`, full message bodies, or recipient lists beyond count.

---

## 4. LLM / Ollama / DeepSeek Calls

### 4.1 Client Initialization

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 4.1.1 | `llm_analysis.py:24-36` | `_get_client()` | Logs host/model at line 34-35 | Does not log whether API key is present (only raises if missing); does not log client reuse | Log client creation vs reuse; log that API key is present (never the value); log timeout settings |

### 4.2 Prompt Building

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 4.2.1 | `llm_analysis.py:57-114` | `build_prompt()` | Logs truncation warning at line 62 | Does not log final prompt size or truncation amount | Log raw input size, truncated size, system prompt length, model name |

### 4.3 LLM Request / Response

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 4.3.1 | `llm_analysis.py:171-260` | `call_llm()` | Logs `generate`/`chat` attempts and response type/length (lines 178, 185, 207, 216, 227, 253) | No request ID; no request duration; no token usage; no raw status code; no retry count; no raw response preview on failure | Log request ID, model, API type, duration, status code, response length, retry/fallback events |
| 4.3.2 | `llm_analysis.py:121-164` | `extract_json_from_response()` | None | JSON extraction failures are not logged before raising | Log extraction method used, failure reasons, raw preview on failure |
| 4.3.3 | `llm_analysis.py:267-328` | `run_audit()` | Logs load, send, input size, response length, missing keys, save success (lines 271, 276, 277, 285, 307, 317) | No end-to-end audit ID; no duration; no schema validation results; no raw response preview on failure | Add `audit_id`, log start/end, duration, input/output file sizes, validation results |

### Recommended LLM logging additions

```text
[LLM] request_id=... model=deepseek-v4-flash:cloud api=generate input_chars=... temperature=0.1
[LLM] response_id=... status=200 duration_sec=... response_chars=...
[LLM] fallback request_id=... from_api=generate to_api=chat reason=...
[LLM] json_extract request_id=... method=code_block success=...
[LLM] audit_complete request_id=... output_file=... duration_sec=... missing_keys=...
```

---

## 5. Google Drive Integrations

### 5.1 Service Account Discovery

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 5.1.1 | `drive_extract.py:21-60` | `find_service_account_file()` | None | Searches multiple patterns silently; does not log which pattern matched | Log candidate patterns tried, which file matched, whether env-var JSON or file path was used |
| 5.1.2 | `drive_extract.py:63-87` | `authenticate_drive()` | Logs env-var usage (line 70), parse error (line 74), missing file errors (lines 79-80), and file used (line 83) | No log of Drive API `build()` call or credential scopes | Log scopes, project ID from service account, API build success/failure |

### 5.2 File Download

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 5.2.1 | `drive_extract.py:90-100` | `download_file_from_drive()` | Logs file ID and progress (lines 92, 99) | No log of file name, MIME type, total bytes, download duration, or failure | Log file name, size, duration, bytes downloaded, error details |

### 5.3 Excel Extraction

| # | File | Function | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|
| 5.3.1 | `drive_extract.py:107-135` | `extract_all_excel_data()` | Logs file read (line 111), rows per tab (line 130), errors (line 134) | No log of header-fixing decisions, columns found, or truncation | Log sheet count, header row detection, columns per sheet, memory usage |
| 5.3.2 | `drive_extract.py:142-198` | `run_extraction()` | Logs save action (lines 190, 193) and failure (line 197) | No log of configured drive files or download folder; no log of individual file success/failure duration | Log drive_files map (file IDs), output path, per-file download/extract duration |

### Recommended Google Drive logging additions

```text
[DRIVE] auth method=env_json|file file=... project_id=... scopes=...
[DRIVE] download_start file_id=... file_name=... output_path=...
[DRIVE] download_progress file_id=... pct=...
[DRIVE] download_end file_id=... duration_sec=... bytes=...
[DRIVE] extract_start file=... sheets_found=...
[DRIVE] extract_sheet file=... sheet=... rows=... columns=... header_fixed=...
[DRIVE] extract_end file=... duration_sec=... output_json=...
```

---

## 6. Report Generation

| # | File | Function | Current Logging | Current Logging | Missing Logging | Recommended Additions |
|---|---|---|---|---|---|---|
| 6.1 | `report_service.py:269-426` | `generate_report()` | `print(f"Report generated: {OUTPUT_FILE}")` at line 426 only | No log of template load, data load, JSON parse, enrichment steps, logo detection, or render duration | Log input file paths, data shape, active employee count, project count, unallocated count, logo file used, render duration, output size |
| 6.2 | `report_service.py:21-265` | Helper functions (`_safe_get`, `_flatten_allocations`, etc.) | None | Fuzzy matches and format fallbacks are invisible | Log when non-trivial format fallback is used (e.g., `_flatten_allocations` format 3 vs 5) |

### Recommended report logging additions

```text
[REPORT] start input=... extracted=... template=...
[REPORT] data_overview active_employees=... active_projects=... unallocated=...
[REPORT] logo logo_file=... data_uri_length=...
[REPORT] render duration_sec=...
[REPORT] end output=... size=...
```

---

## 7. Error Handling Gaps

| # | File | Location | Current Behavior | Risk | Recommended Fix |
|---|---|---|---|---|---|
| 7.1 | `api/main.py:209-211` | `run_pipeline` import error | Emits to SSE only, no server-side log | Server admin cannot see why pipeline failed | Log `ImportError` at `ERROR` level with traceback |
| 7.2 | `api/main.py:226-229` | `_run_stage` failure inside SSE | Emits to SSE, but `_run_pipeline_sync` also captures; duplicate/lossy | No single authoritative error log | Log a structured `ERROR` entry with stage, exception, captured stderr length |
| 7.3 | `api/main.py:315-326` | `send_email_only` | Returns dict directly; no try/except around `send_email_with_pdf` | Unhandled exceptions return 500 with no detail | Wrap call in try/except, log exception, return safe JSON |
| 7.4 | `api/main.py:355-363` | `update_settings` | Does not validate payload dates; no error handling on `save_settings` | Corrupt settings file may crash scheduler | Validate ISO dates, log validation failures, catch persistence errors |
| 7.5 | `api/email_sender.py:106-115` | SMTP block | Catches `SMTPAuthenticationError` and generic Exception but only returns dict | Server log has zero visibility into email failures | Log exceptions before returning; include sanitized SMTP reply |
| 7.6 | `api/email_sender.py:23-63` | `generate_pdf()` | Silent fallback chain; final `False` gives no detail | Hard to diagnose missing PDFs | Log each renderer attempt and why it failed |
| 7.7 | `api/settings_manager.py:33-35` | `load_settings()` | Swallows JSON parse/file errors silently | Corrupt settings silently revert to defaults | Log file path, parse error, fallback to defaults |
| 7.8 | `llm_analysis.py:320-328` | `run_audit()` exception handler | Raises generic `RuntimeError`; loses original stack | Debugging LLM failures is hard | Log full traceback and raw response preview before re-raising |
| 7.9 | `dashboard/app/page.tsx:235-237, 278` | SSE parse errors | Silently swallowed (`catch { /* ignore */ }`) | Frontend may appear stuck while backend sent valid data | Log parse errors to console/Sentry; include raw line |
| 7.10 | `dashboard/app/page.tsx:131-150` | Initial fetch errors | Silently caught | User sees "Ready" even if backend is down | Log and surface backend unreachable state |

---

## 8. Security Concerns

| # | File | Location | Concern | Recommended Mitigation |
|---|---|---|---|---|
| 8.1 | `api/email_sender.py:12-19` | `_smtp_config()` | Email password loaded from env but never validated or logged; if logging is added, password could be accidentally included | Explicitly redact `password` in any log; use Pydantic SecretStr |
| 8.2 | `llm_analysis.py:21, 27-33` | `_get_client()` | `OLLAMA_API_KEY` is read and sent in header; never log the key | Redact `Authorization` header in logs |
| 8.3 | `drive_extract.py:21-60` | `find_service_account_file()` | Service account JSON may be written to a temp file without logging or cleanup | Log temp file creation and ensure cleanup; restrict permissions |
| 8.4 | `api/settings_manager.py` | `save_settings()` | Settings JSON written to disk; contains recipient list but no secrets | OK, but log writes for audit |
| 8.5 | `api/main.py:173-179` | `CORSMiddleware` | `allow_origins` restricted to localhost; OK for dev but production may be wildcarded accidentally | Keep restrictive; log disallowed origins at `WARNING` |
| 8.6 | `api/main.py:354-363` | `update_settings()` | No authentication/authorization; anyone with network access can toggle automation | Add API key or session auth; log all mutations with caller IP |
| 8.7 | `api/main.py:205-240, 249-311` | Pipeline endpoints | No rate limiting; expensive LLM calls could be triggered repeatedly | Add rate limiting middleware; log throttling events |
| 8.8 | `dashboard/app/page.tsx:321-344` | `saveSettings()` | Sends full settings to backend without auth headers | Add auth header and log unauthorized attempts |
| 8.9 | `api/email_sender.py:105-110` | SMTP login | Plain-text SMTP with STARTTLS; ensure TLS is enforced | Log TLS version/cipher if available; reject plaintext on port 587 if server supports TLS |
| 8.10 | `api/main.py:330-336` | `/api/report` | Returns entire report HTML without auth | Add auth or at least log access |

---

## 9. Recommended Logging Architecture

### 9.1 Goals

1. **Centralized structured logs** using Python `logging` with JSON formatter.
2. **Request correlation** via a `request_id` propagated across FastAPI, frontend, scheduler, LLM, and email flows.
3. **No secrets in logs** — automatic redaction of `password`, `api_key`, `Authorization`, `GOOGLE_SERVICE_ACCOUNT_JSON`, and email bodies.
4. **Performance/timing** for every external call (SMTP, Ollama, Google Drive, PDF generation).
5. **Audit trail** for automation state changes (`active`, `next_run`, `last_run`).
6. **Frontend observability** by sending client logs to the same backend endpoint or using a browser error boundary.

### 9.2 Suggested Implementation (no code changes made)

#### A. Replace `print()` with a configured logger

Create `api/logger.py`:

```python
import logging
import sys
from pythonjsonlogger import jsonlogger  # add to requirements

handler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter(
    '%(timestamp)s %(level)s %(name)s %(message)s '
    '%(request_id)s %(execution_id)s %(duration_ms)s',
    rename_fields={'levelname': 'level', 'asctime': 'timestamp'}
)
handler.setFormatter(formatter)
logger = logging.getLogger("pipeline")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

Then in modules:

```python
from api.logger import logger
logger.info("download_start", extra={"file_id": file_id, "file_name": file_name})
```

#### B. Add a FastAPI middleware for request logging

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(
        "http_request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "origin": request.headers.get("origin"),
        },
    )
    response.headers["x-request-id"] = request_id
    return response
```

#### C. Add context propagation

Use `contextvars` to store `request_id`/`execution_id` and bind them in helper functions without threading args everywhere:

```python
import contextvars
request_id_var = contextvars.ContextVar("request_id", default=None)
execution_id_var = contextvars.ContextVar("execution_id", default=None)
```

#### D. Redaction helper

```python
SENSITIVE_KEYS = {"password", "api_key", "authorization", "token", "secret"}
def redact(obj: dict) -> dict:
    return {
        k: "***REDACTED***" if k.lower() in SENSITIVE_KEYS else v
        for k, v in obj.items()
    }
```

#### E. Frontend logging

Add a lightweight wrapper in `dashboard/app/page.tsx`:

```typescript
function log(level: 'info'|'warn'|'error', message: string, meta?: object) {
  const entry = { ts: new Date().toISOString(), level, message, ...meta };
  // Send to backend /api/client-log or console in dev
  console[level](entry);
}
```

Replace `catch(() => {})` with `catch(err => log('error', 'fetch_failed', { path: '/api/report', error: err.message }))`.

#### F. Scheduler audit log

Persist a separate append-only log file `api/scheduler_audit.logl` (JSON lines) with one entry per poll and one per execution:

```json
{"ts":"2026-06-17T10:00:00","event":"poll","execution_id":"...","active":true,"next_run":"...","decision":false,"reason":"next_run_in_future"}
{"ts":"2026-06-17T10:01:00","event":"execution_start","execution_id":"..."}
{"ts":"2026-06-17T10:02:30","event":"execution_end","execution_id":"...","pipeline_ok":true,"email_ok":true,"duration_sec":90}
```

This survives restarts and provides a non-repudiation trail for automation runs.

### 9.3 Files to Modify (when approved)

1. `api/logger.py` — new file.
2. `api/main.py` — add middleware, bind logger in endpoints, log scheduler events.
3. `api/email_sender.py` — add logging with redaction.
4. `api/settings_manager.py` — log load/save/validation events.
5. `drive_extract.py` — replace/augment `print()` with logger calls.
6. `llm_analysis.py` — add request IDs, durations, and raw-response previews on failure.
7. `report_service.py` — log data shape and render duration.
8. `dashboard/app/page.tsx` — add client logger and remove silent catches.
9. `ui/index.html` — add `console.info` for lifecycle events.
10. `requirements.txt` — add `python-json-logger`.

### 9.4 Logging Levels Guide

| Level | Use Case |
|---|---|
| `DEBUG` | Raw response previews (truncated), prompt snippets, full tracebacks in dev |
| `INFO` | Endpoint starts/ends, scheduler polls, successful external calls, settings changes |
| `WARNING` | Retries, fallback PDF renderers, missing optional files, large input truncation |
| `ERROR` | Pipeline stage failures, SMTP errors, LLM API errors, settings corruption |
| `CRITICAL` | Scheduler crash, auth failures, inability to persist settings |

---

## 10. Quick-Win Checklist

1. Add FastAPI request/response middleware with timing and `x-request-id`.
2. Log every `/api/settings` mutation with old/new state diff.
3. Log `_scheduled_job` decisions from `check_schedule_action()`.
4. Replace silent `catch(() => {})` blocks in `dashboard/app/page.tsx` with error logging.
5. Log each PDF renderer attempt in `email_sender.py`.
6. Log LLM request/response durations and fallback events.
7. Add redaction helper before any credential is logged.
8. Create `api/scheduler_audit.logl` for persistent automation history.

---

*Report generated on 2026-06-17. No code changes were made.*