# Wohlig Workforce Intelligence Platform

## Overview

The Wohlig Workforce Intelligence Platform is a full-stack workforce analytics and reporting solution that automates workforce data extraction, AI-powered analysis, executive report generation, email distribution, and scheduled report delivery.

The platform fetches workforce allocation data from Google Drive, analyzes employee utilization using an LLM, generates executive-ready HTML reports, converts reports into PDF format, and distributes them automatically via email.

---

# Architecture

```text
Next.js Dashboard (Port 3000)
            │
            ▼
       FastAPI API
       (Port 8000)
            │
            ▼
     Python Pipeline
            │
            ▼
Google Drive Workforce Data
            │
            ▼
Drive Extraction
            │
            ▼
LLM Workforce Analysis
            │
            ▼
HTML Report Generation
            │
            ▼
PDF Generation
            │
            ▼
Email Distribution
```

---

# Features

### Workforce Analytics

* Employee allocation analysis
* Resource utilization tracking
* Bench employee identification
* Project allocation insights
* Workforce optimization recommendations
* Employee-level reasoning

### AI-Powered Analysis

* Ollama Cloud integration
* Workforce intelligence generation
* Executive summaries
* Utilization recommendations
* Allocation validation

### Report Generation

* Dynamic HTML reports
* Executive dashboard format
* Workforce allocation tables
* Project utilization analytics
* PDF export support
* Live dashboard preview

### Email Automation

* SMTP email integration
* Multiple recipients
* PDF attachment support
* HTML fallback attachment
* Scheduled email delivery

### Scheduler

* One-time execution
* Continuous recurring execution
* Configurable intervals
* Automatic report generation
* Automatic email distribution

### Dashboard

* Live pipeline progress
* Report preview
* HTML source view
* Scheduler management
* Email configuration

---

# Technology Stack

| Layer            | Technology            |
| ---------------- | --------------------- |
| Frontend         | Next.js 15            |
| Language         | TypeScript            |
| Styling          | Tailwind CSS          |
| Backend          | FastAPI               |
| AI Model         | Ollama                |
| Data Processing  | Pandas                |
| Excel Processing | OpenPyXL              |
| Templates        | Jinja2                |
| Email            | SMTP                  |
| Scheduler        | APScheduler           |
| Deployment       | Google Cloud Platform |

---

# Project Structure

```text
pipeline/

├── api/
│   ├── main.py
│   ├── email_sender.py
│   ├── settings_manager.py
│   ├── requirements.txt
│   └── schedule_settings.json
│
├── dashboard/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   └── globals.css
│   │
│   ├── public/
│   ├── package.json
│   ├── next.config.mjs
│   └── tailwind.config.ts
│
├── data/
│   └── workforce_analysis_output.json
│
├── reports/
│   ├── workforce_report.html
│   └── workforce_report.pdf
│
├── drive_extract.py
├── llm_analysis.py
├── report_service.py
├── workforce_report_template.html
├── app.py
├── .env
└── README.md
```

---

# Environment Variables

Create a `.env` file in the project root.

```env
# Google Drive

GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
DRIVE_FILE_ID=YOUR_DRIVE_FILE_ID
DRIVE_FILE_NAME=Wohlig Active Employee Data.xlsx

# Ollama

OLLAMA_API_KEY=YOUR_OLLAMA_API_KEY
OLLAMA_MODEL=deepseek-v4-flash:cloud

# Email

EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_gmail_app_password

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

---

# Local Setup

## Backend

```bash
python3 -m venv .venv

source .venv/bin/activate

pip install -r api/requirements.txt

uvicorn api.main:app --reload
```

Backend URL:

```text
http://127.0.0.1:8000
```

---

## Frontend

```bash
cd dashboard

npm install

npm run dev
```

Frontend URL:

```text
http://localhost:3000
```

---

# Pipeline Workflow

## Full Pipeline

```text
Google Drive Excel
        │
        ▼
Drive Extraction
        │
        ▼
all_files_extracted_data.json
        │
        ▼
LLM Analysis
        │
        ▼
workforce_analysis_output.json
        │
        ▼
HTML Report Generation
        │
        ▼
workforce_report.html
        │
        ▼
PDF Generation
        │
        ▼
Email Distribution
```

---

## Generate Report Only

Uses existing extracted data and existing LLM analysis.

```text
Generate Report Only
        │
        ▼
Generate HTML Report
        │
        ▼
workforce_report.html
        │
        ▼
GET /api/report
        │
        ▼
Dashboard Preview
```

---

# Scheduler & Automation

The platform includes a background scheduler powered by APScheduler.

The scheduler automatically checks schedules every minute and triggers report generation and email delivery.

## Scheduler Flow

```text
User Saves Settings
        │
        ▼
schedule_settings.json
        │
        ▼
Background Scheduler
(Polls Every Minute)
        │
        ▼
Scheduled Time Reached
        │
        ▼
Run Pipeline
        │
        ▼
Generate Report
        │
        ▼
Generate PDF
        │
        ▼
Send Email
        │
        ▼
Update Next Run
```

---

## One-Time Scheduling

Configure:

* Active = ON
* Continuous = OFF
* Next Run = Desired Date & Time

Behavior:

* Runs once
* Generates report
* Sends email
* Automatically disables itself

---

## Continuous Scheduling

Configure:

* Active = ON
* Continuous = ON
* Interval Hours = Desired Interval

Behavior:

* Runs repeatedly
* Automatically updates next run time
* Continues until disabled

---

## Scheduler Storage

Configuration is stored in:

```text
api/schedule_settings.json
```

Example:

```json
{
  "recipients": [],
  "next_run": "",
  "stop_run": "",
  "continuous": false,
  "active": false,
  "subject": "",
  "body_line": "",
  "interval_hours": 24,
  "last_run": ""
}
```

---

# API Endpoints

| Endpoint             | Method | Description            |
| -------------------- | ------ | ---------------------- |
| /health              | GET    | Health Check           |
| /api/health          | GET    | Health Check           |
| /api/pipeline-status | GET    | Stage Status           |
| /api/run-pipeline    | POST   | Full Pipeline          |
| /api/generate-report | POST   | Report Only            |
| /api/run-and-email   | POST   | Pipeline + Email       |
| /api/send-email      | POST   | Email Existing Report  |
| /api/report          | GET    | Get Latest HTML Report |
| /api/settings        | GET    | Load Settings          |
| /api/settings        | POST   | Save Settings          |

---

# Generated Files

### Extracted Workforce Data

```text
all_files_extracted_data.json
```

Generated by:

```text
drive_extract.py
```

---

### Workforce Analysis

```text
data/workforce_analysis_output.json
```

Generated by:

```text
llm_analysis.py
```

---

### HTML Report

```text
reports/workforce_report.html
```

Generated by:

```text
report_service.py
```

---

### PDF Report

```text
reports/workforce_report.pdf
```

Generated automatically during email workflow.

---

# Email Configuration

Supported:

* Gmail SMTP
* Multiple recipients
* PDF attachments
* HTML fallback attachments

For Gmail:

1. Enable Two-Factor Authentication
2. Create an App Password
3. Use App Password as:

```env
EMAIL_PASSWORD=YOUR_APP_PASSWORD
```

---

# GCP Deployment

## Backend

```bash
source .venv/bin/activate

uvicorn api.main:app \
  --host 0.0.0.0 \
  --port 8000
```

## Frontend

```bash
cd dashboard

npm run build

npm start
```

---

# Troubleshooting

### ECONNREFUSED 127.0.0.1:8000

Backend is not running.

Start FastAPI:

```bash
uvicorn api.main:app --reload
```

---

### Report Not Found

Generate a report first:

```http
POST /api/generate-report
```

or

```http
POST /api/run-pipeline
```

---

### SMTP Authentication Failed

Use a Gmail App Password instead of your Gmail password.

---

### Report Preview Blank

The frontend automatically calls:

```http
GET /api/report
```

after successful report generation and loads the HTML preview.

---

# Security

* Never commit `.env`
* Never commit SMTP credentials
* Never commit Google Service Account credentials
* Use GCP Secret Manager in production
* Restrict Google Drive access appropriately

---

# License

Private Internal Project

Wohlig Technologies

---

# Authors

Aryan Gupta

Dhruv Solanki
