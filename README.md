# Wohlig Report Pipeline Dashboard

Full-stack automation dashboard for generating workforce intelligence reports from Google Drive → LLM Analysis → HTML/PDF → Email with automated scheduling.

## 🏗️ Architecture

```
┌──────────────────┐        ┌──────────────────┐        ┌─────────────────┐
│   Next.js 14     │───────▶│   FastAPI 0.111  │───────▶│ Python Pipeline │
│   React 18       │        │   Port 8000      │        │  (Ollama)       │
│   Port 3000      │        │                  │        │                 │
└──────────────────┘        └──────────────────┘        └─────────────────┘
                                     │                          │
                            ┌────────┴──────────┐                │
                            │                   ▼                │
                       ┌─────────────────────────────┐           │
                       │  Background Scheduler       │◀──────────┘
                       │  (Local: every 60s)         │
                       │  (Vercel: Cron Jobs)        │
                       └─────────────────────────────┘
```

## 🛠️ Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Frontend** | Next.js + React | 14.2.5 / 18.3.1 |
| **Styling** | Tailwind CSS + PostCSS | 3.4.7 |
| **Backend API** | FastAPI + Uvicorn | 0.111.0 |
| **LLM** | Ollama (local or cloud) | Any model |
| **Data Source** | Google Drive API | v3 |
| **Email** | SMTP (Gmail) | TLS 1.2 |
| **Scheduling** | Background Thread + Vercel Cron | Local + Cloud |
| **Database** | JSON Files (local) / Vercel KV (cloud) | - |

## 🚀 Quick Start

## 🚀 Quick Start

### Local Development (5 minutes)

**Prerequisites:**
- Python 3.9+
- Node.js 18+
- Google Service Account JSON (for Drive access)
- Gmail App Password (for email)
- Ollama running locally (or cloud API key)

**1. Install Dependencies**

```bash
# Python backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

# Node frontend
cd dashboard
npm install
cd ..
```

**2. Configure Environment**

Create `.env` in project root:

```env
# ── Google Drive ──────────────────────────
GOOGLE_SERVICE_ACCOUNT_FILE=my-service-account.json
DRIVE_FILE_ID=1EAGD1LreF9KF3kSyqsOTSinmo9iSEDWn
DRIVE_FILE_NAME=Wohlig Active Employee Data.xlsx

# ── Ollama LLM ────────────────────────────
OLLAMA_API_KEY=your-api-key
OLLAMA_MODEL=gemma4:31b-cloud

# ── Gmail SMTP ────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com
```

> 💡 **Gmail Setup:** Generate App Password at https://myaccount.google.com/apppasswords (enable 2FA first)

**3. Start Development Servers**

```bash
# Terminal 1: Backend (auto-starts scheduler)
source .venv/bin/activate
uvicorn api.main:app --reload

# Terminal 2: Frontend
cd dashboard && npm run dev
```

Open http://localhost:3000

---

## ⏰ Scheduler Configuration

### Local Development

The **background scheduler** runs automatically:
- ✅ Starts with backend
- ✅ Checks every 60 seconds
- ✅ Executes `/api/cron` endpoint
- ✅ Sends emails on schedule

**Logs you'll see:**
```
[BACKGROUND_SCHEDULER] Starting background scheduler...
[SCHEDULER] ✓ Email sent successfully
[SCHEDULER] Next run calculated: 2026-06-13T15:30:00
```

### Using Frontend Settings

1. Open http://localhost:3000 → **Settings** tab
2. Configure:
   - **Recipients:** Select email addresses
   - **Next Run:** Set execution time
   - **Cron Expression:** `*/2 * * * *` (every 2 min) or leave empty
   - **Interval (hours):** `24` (used if no cron)
   - **Continuous:** ✓ Check for recurring runs
   - **Active:** ✓ Check to enable

3. Click **Save Settings** → Scheduler triggers immediately

**Example Cron Expressions:**
```
*/2 * * * *     → Every 2 minutes
0 9 * * *       → Daily at 9 AM
0 */6 * * *     → Every 6 hours
0 0 * * 1       → Weekly on Monday
```

### Manual Testing

```bash
# Trigger scheduler manually
curl http://127.0.0.1:8000/api/cron

# View current settings
curl http://127.0.0.1:8000/api/settings

# View generated report
curl http://127.0.0.1:8000/api/report
```

---

## 🌐 Vercel Deployment

### Prerequisites

- GitHub repository with code pushed
- Vercel account (free)
- Environment variables ready

### Step-by-Step Deployment

**1. Push Code to GitHub**

```bash
git add .
git commit -m "Ready for Vercel deployment"
git push origin main
```

**2. Create Vercel Project**

- Go to https://vercel.com/dashboard
- Click **"Add New..."** → **"Project"**
- Select your GitHub `pipeline` repo
- Click **"Import"**

Vercel auto-detects:
- ✅ Next.js frontend
- ✅ Python backend
- ✅ vercel.json config

**3. Add Environment Variables**

In Vercel dashboard → **Settings** → **Environment Variables**, add:

```
SMTP_HOST                     smtp.gmail.com
SMTP_PORT                     587
SMTP_USER                     your-email@gmail.com
SMTP_PASSWORD                 your-app-password
SMTP_FROM                     your-email@gmail.com
GOOGLE_SERVICE_ACCOUNT_JSON   {"type":"service_account","project_id":"..."}
DRIVE_FILE_ID                 1EAGD1LreF9KF3kSyqsOTSinmo9iSEDWn
DRIVE_FILE_NAME               Wohlig Active Employee Data.xlsx
OLLAMA_API_KEY                your-api-key
OLLAMA_MODEL                  gemma4:31b-cloud
```

**4. Redeploy**

- Go to **Deployments**
- Click **"Redeploy"** on latest deployment

Wait 3-5 minutes for deployment...

**5. Verify Deployment**

```bash
# Check health
curl https://your-app.vercel.app/health

# Trigger scheduler manually
curl https://your-app.vercel.app/api/cron
```

**6. Test Scheduler (Optional)**

Update [vercel.json](vercel.json) to test every 2 minutes:

```json
{
  "crons": [{
    "path": "/api/cron",
    "schedule": "*/2 * * * *"
  }]
}
```

Push the change → Vercel redeploys automatically

---

## � Project Structure

```
pipeline/
├── api/
│   ├── main.py                 # FastAPI app + scheduler
│   ├── email_sender.py         # SMTP email + PDF generation
│   ├── settings_manager.py     # Schedule settings persistence
│   ├── requirements.txt        # Python dependencies
│   └── schedule_settings.json  # Current schedule config (gitignored)
│
├── dashboard/
│   ├── app/
│   │   ├── page.tsx           # Main UI + Settings form
│   │   ├── layout.tsx         # Root layout
│   │   └── globals.css        # Global styles
│   ├── public/                # Static assets
│   ├── package.json           # Node dependencies
│   └── tailwind.config.ts     # Tailwind config
│
├── app.py                      # Python pipeline orchestrator
├── drive_extract.py            # Google Drive → Excel extraction
├── llm_analysis.py             # Ollama LLM analysis
├── report_service.py           # HTML report generation
├── start.sh                    # One-command local start
├── vercel.json                 # Vercel + Cron config
├── README.md                   # This file
└── .env                        # Secrets (gitignored)
```

---

## 🔄 Pipeline Flow

### Manual Execution (Button Click)

1. **Frontend:** Click "Go" button
2. **Backend:** Runs pipeline via `/api/run-pipeline` (SSE streaming)
3. **Drive Extract:** Fetches Excel from Google Drive
4. **LLM Analysis:** Ollama processes workforce data
5. **Report Generation:** Jinja2 creates HTML
6. **PDF Conversion:** Chrome/Chromium headless converts to PDF
7. **Display:** Report shows in Preview tab instantly

### Automated Execution (Scheduler)

1. **Settings Saved:** User configures recipients + schedule
2. **Background Scheduler:** Checks every 60 seconds (local) or cron job (Vercel)
3. **Condition Met:** If time reached, triggers `_scheduled_job()`
4. **Pipeline Runs:** Full flow (extract → analyze → report → PDF)
5. **Email Sent:** PDF attachment to all recipients
6. **Next Run:** Calculated and saved to schedule_settings.json

---

## 🐛 Debugging

### View Scheduler Logs

**Local:**
```bash
# Terminal running uvicorn
[SCHEDULER] Starting scheduled job
[SCHEDULER] ✓ PDF generated
[SCHEDULER] Sending to: ['email@example.com']
[SCHEDULER] ✓ Email sent successfully
```

**Vercel:**
- Go to https://vercel.com/dashboard → Deployments → Logs
- Scroll to find `[SCHEDULER]` output

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Trigger scheduler
curl http://localhost:8000/api/cron

# Get settings
curl http://localhost:8000/api/settings | jq

# Run pipeline
curl -X POST http://localhost:8000/api/run-pipeline \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Email not sent | Check SMTP credentials in `.env` / Vercel env vars |
| Report not generated | Verify Google Drive file ID + service account permissions |
| Scheduler not running | Check `[BACKGROUND_SCHEDULER]` logs, ensure `VERCEL` env not set |
| PDF generation failed | Chrome/Chromium not installed on Vercel (normal, HTML attachment used) |
| Double emails | Fixed with debounce flag in frontend |

---

## 📊 Features

- ✅ **Full Automation:** Extract → Analyze → Report → Email
- ✅ **Cron Scheduling:** Flexible cron expressions + simple intervals
- ✅ **Smart Scheduling:** Different behavior for local vs cloud
- ✅ **Background Processing:** Non-blocking pipeline execution
- ✅ **Email Attachments:** PDF or HTML fallback
- ✅ **Responsive UI:** Tailwind CSS responsive design
- ✅ **Real-time Preview:** HTML report preview in dashboard
- ✅ **Cloud Ready:** Vercel deployment with cron jobs
- ✅ **Debugging:** Comprehensive logging + terminal output

---

## 🔐 Security Considerations

1. **Never commit `.env`** — gitignore is set up
2. **Use App Passwords** — Gmail specific passwords, not main password
3. **Vercel Env Vars** — Always use Vercel dashboard, never commit secrets
4. **Google Service Account** — Share only with necessary Drive access
5. **CRON_SECRET** — Optional: add token to Vercel cron calls for verification

---

## 📝 License

Private project - Wohlig Technologies

---

## 🤝 Support

For issues or questions:
1. Check logs in backend terminal or Vercel dashboard
2. Verify `.env` variables are set correctly
3. Test `/api/cron` endpoint manually
4. Check Google Drive permissions
5. Verify Ollama API access



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
