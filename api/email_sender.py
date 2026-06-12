import os
import smtplib
import subprocess
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def _smtp_config():
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")),
    }


def generate_pdf(html_path: str, pdf_path: str) -> bool:
    """
    Convert HTML to PDF using available tools.
    Strategy:
    1. Chrome/Chromium headless (best fidelity)
    2. weasyprint (pure python, no extra binaries)
    3. pdfkit + wkhtmltopdf
    4. None available - return False
    """
    chrome_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for chrome in chrome_candidates:
        if Path(chrome).exists():
            try:
                cmd = [
                    chrome,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--print-to-pdf-no-header",
                    f"--print-to-pdf={pdf_path}",
                    html_path,
                ]
                subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)
                if Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 0:
                    return True
            except Exception:
                continue

    try:
        import weasyprint
        weasyprint.HTML(filename=html_path).write_pdf(pdf_path)
        return True
    except Exception:
        pass

    try:
        import pdfkit
        pdfkit.from_file(html_path, pdf_path)
        return True
    except Exception:
        pass

    return False


def send_email_with_pdf(
    recipients: list[str],
    subject: str,
    body_line: str,
    html_path: str,
    pdf_path: str,
) -> dict:
    cfg = _smtp_config()
    if not cfg["user"] or not cfg["password"]:
        return {"success": False, "error": "SMTP_USER or SMTP_PASSWORD not set in .env"}

    if not recipients:
        return {"success": False, "error": "No recipients selected"}

    # Proceed without failing if PDF generation didn't work previously
    msg = MIMEMultipart()
    msg["From"] = cfg["from_addr"] or cfg["user"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    msg.attach(MIMEText(body_line, "plain"))

    # Try to generate PDF. On Vercel, this might fail due to lack of binaries.
    # If it fails, we will fallback to attaching the HTML file directly!
    has_pdf = False
    if Path(html_path).exists():
        has_pdf = generate_pdf(html_path, pdf_path)
        
    if has_pdf and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="Company_Report.pdf"')
        msg.attach(part)
    elif Path(html_path).exists():
        # Fallback to HTML attachment
        with open(html_path, "rb") as f:
            part = MIMEBase("text", "html")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="Company_Report.html"')
        msg.attach(part)

    try:
        server = smtplib.SMTP(cfg["host"], cfg["port"])
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["from_addr"] or cfg["user"], recipients, msg.as_string())
        server.quit()
        return {"success": True, "sent_to": recipients}
    except Exception as e:
        return {"success": False, "error": str(e)}
