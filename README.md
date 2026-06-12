# Wohlig Report Pipeline Dashboard

Full-stack automation dashboard for generating workforce intelligence reports from Google Drive → LLM Analysis → HTML/PDF → Email.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Next.js App   │────▶│   FastAPI API   │────▶│ Python Pipeline │
│   Port 3000     │     │   Port 8000     │     │  (app.py)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        │            ┌──────────────┐                  │
        └───────────▶│  APScheduler │◀─────────────────┘
                     │  (cron-like) │
                     └──────────────┘
```

## Setup

### 1. Install Python Dependencies

```bash
cd /path/to/pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
pip install python-dotenv pandas openpyxl google-api-python-client ollama jinja2
```

### 2. Configure Environment

Edit `.env` in the project root:

```env
# ── Ollama ───────────────────────────────────────
OLLAMA_API_KEY=your-key
OLLAMA_MODEL=gemma4:31b-cloud

# ── Google Drive ──────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_FILE=my-service-account.json
DRIVE_FILE_NAME=Wohlig Active Employee Data.xlsx
DRIVE_FILE_ID=1EAGD1LreF9KF3kSyqsOTSinmo9iSEDWn

# ── SMTP / Email ─────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com
```

For Gmail, generate an **App Password** at https://myaccount.google.com/apppasswords

### 3. Install Node.js & Frontend Dependencies

Requires **Node.js 18+**.

```bash
cd dashboard
npm install
```

## Running the Application

### Option A: One-Command Start (Terminal 1)

```bash
chmod +x start.sh
./start.sh
```

Then open: http://localhost:3000

### Option B: Separate Terminals

**Terminal 1 — Backend:**
```bash
cd /path/to/pipeline
source .venv/bin/activate
python3 -c "import sys; sys.path.insert(0,'.'); from api.main import app; import uvicorn; uvicorn.run(app, host='127.0.0.1', port=8000)"
```

**Terminal 2 — Frontend:**
```bash
cd /path/to/pipeline/dashboard
npm run dev
```

Then open: http://localhost:3000

## Usage

### 1. Run Pipeline Manually
- Click **Go** button to execute the full pipeline:
  - Fetch Excel from Google Drive
  - LLM Analysis via Ollama
  - Generate HTML Report
- The report appears in the Preview tab instantly.

### 2. Send Email
- Open **Settings** (⚙️)
- Select email recipients (click buttons to toggle)
- Set **Subject** (default: "Company report")
- Set **Body line** (default: "Please find the attached company workforce report.")
- Click **Send Email**
- The PDF is auto-generated from the HTML and emailed.

### 3. Schedule Automated Runs

#### One-Time Run
1. Open **Settings**
2. Turn **Active** ON
3. Set **Next Run** date & time
4. Optionally set **Stop Run**
5. Click **Save**

#### Continuous Runs
1. Open **Settings**
2. Turn **Active** ON
3. Turn **Continuous** ON
4. Set **Interval** (e.g., 24 hours)
5. Set **Next Run** start time
6. Optionally set **Stop Run**
7. Click **Save**

The backend polls every minute. When the scheduled time is reached, it:
- Runs the pipeline
- Generates PDF
- Emails selected recipients
- If continuous: advances next_run by interval

### 4. Deactivate Automation
- Open **Settings**
- Turn **Active** OFF
- Click **Save**
- Or hit **Reset** to clear everything.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/run-pipeline` | POST | Run full pipeline (SSE stream) |
| `/api/report` | GET | Get latest HTML report |
| `/api/report/download` | GET | Download HTML file |
| `/api/generate-pdf` | POST | Generate PDF from HTML |
| `/api/pdf` | GET | Download PDF file |
| `/api/settings` | GET / POST | Load / save settings |
| `/api/send-email` | POST | Send PDF to recipients |

## File Structure

```
pipeline/
├── .env                              # Environment variables
├── app.py                            # Pipeline orchestrator
├── drive_extract.py                  # Google Drive extraction
├── llm_analysis.py                   # LLM audit analysis
├── report_service.py                 # HTML report generation
├── workforce_report_template.html    # Jinja2 template
├── start.sh                          # One-command launcher
│
├── api/
│   ├── requirements.txt              # FastAPI deps
│   ├── main.py                       # FastAPI app
│   ├── settings_manager.py           # Schedule settings persistence
│   └── email_sender.py               # SMTP + PDF generation
│
└── dashboard/                        # Next.js frontend
    ├── package.json
    ├── next.config.mjs               # Proxies /api/* to FastAPI
    ├── tsconfig.json
    ├── tailwind.config.ts
    └── app/
        ├── layout.tsx
        ├── globals.css
        └── page.tsx                  # Main dashboard UI
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No module named 'fastapi'` | `pip install -r api/requirements.txt` |
| `SMTP auth failed` | Enable 2FA on Gmail and use an **App Password** |
| `PDF generation failed` | Install Chrome, or `pip install weasyprint` |
| `CORS error` | Ensure backend runs on `127.0.0.1:8000` and frontend on `localhost:3000` |
| `Backend not running` | Start FastAPI first before the Next.js dev server |
| `Report shows empty cards` | This means the LLM JSON had key casing mismatches. The latest `report_service.py` handles this dynamically. |
