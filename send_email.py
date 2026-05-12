#!/usr/bin/env python3
"""Send an email notification with a preview of the daily news report."""

import html
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


def extract_summaries(html_content):
    """Extract a brief preview from each report section."""
    summaries = []
    sections = re.split(r"<section[^>]*>", html_content)

    for section in sections[1:]:
        h2 = re.search(r"<h2>(.*?)</h2>", section, re.DOTALL)
        if not h2:
            continue
        heading = re.sub(r"<[^>]+>", "", h2.group(1)).strip()

        after_h2 = section[h2.end() :]
        h3 = re.search(r"<h3>(.*?)</h3>", after_h2, re.DOTALL)
        p = re.search(r"<p>(.*?)</p>", after_h2, re.DOTALL)

        preview = ""
        if h3:
            title = re.sub(r"<[^>]+>", "", h3.group(1)).strip()
            preview = title
            if p:
                body = re.sub(r"<[^>]+>", "", p.group(1)).strip()
                if len(body) > 120:
                    body = body[:117] + "..."
                preview += f" — {body}"
        elif p:
            preview = re.sub(r"<[^>]+>", "", p.group(1)).strip()
            if len(preview) > 200:
                preview = preview[:197] + "..."
        else:
            preview = "See full report for details."

        summaries.append((heading, preview))

    return summaries


def build_email_html(summaries, report_url, date_str):
    safe_url = html.escape(report_url, quote=True)
    rows = ""
    for heading, text in summaries:
        rows += f"""
        <tr>
            <td style="padding: 10px 0; border-bottom: 1px solid #eee;">
                <strong style="color: #222; font-size: 15px;">{html.escape(heading)}</strong><br>
                <span style="color: #555; font-size: 14px; line-height: 1.5;">{html.escape(text)}</span>
            </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
             max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
    <h2 style="color: #222; border-bottom: 2px solid #222; padding-bottom: 8px; margin-bottom: 4px;">
        Daily News Report
    </h2>
    <p style="color: #666; font-style: italic; margin-bottom: 20px;">{html.escape(date_str)}</p>

    <table style="width: 100%; border-collapse: collapse;">
        {rows}
    </table>

    <p style="margin-top: 28px;">
        <a href="{safe_url}"
           style="display: inline-block; background: #2a5db0; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 6px; font-weight: 600;">
            Read Full Report &rarr;
        </a>
    </p>

    <p style="margin-top: 36px; font-size: 12px; color: #999;">
        Generated with Gemini AI &bull;
        <a href="{safe_url}" style="color: #999;">{safe_url}</a>
    </p>
</body>
</html>"""


def send_email(subject, html_body, from_addr, to_addr, app_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    plain = re.sub(r"<[^>]+>", "", html_body)
    plain = re.sub(r"\s+", " ", plain).strip()
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_addr, app_password)
        server.sendmail(from_addr, to_addr, msg.as_string())


def main():
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email = os.environ["TO_EMAIL"]
    report_url = os.environ.get("GITHUB_PAGES_URL", "")

    report_path = Path("output/index.html")
    if not report_path.exists():
        print("Error: output/index.html not found. Run generate_report.py first.")
        sys.exit(1)

    html_content = report_path.read_text(encoding="utf-8")
    date_str = datetime.now(CENTRAL_TZ).strftime("%A, %B %d, %Y")

    summaries = extract_summaries(html_content)
    if not summaries:
        summaries = [("Daily Report", "Your daily news report is ready.")]

    email_html = build_email_html(summaries, report_url, date_str)
    subject = f"Daily News Report — {date_str}"

    print(f"Sending email to {to_email}...")
    send_email(subject, email_html, gmail_address, to_email, gmail_app_password)
    print("Email sent successfully.")


if __name__ == "__main__":
    main()
