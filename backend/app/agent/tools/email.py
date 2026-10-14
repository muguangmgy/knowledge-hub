from __future__ import annotations

import re
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.common.config import get_settings

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_EMAIL_IN_TEXT_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)


def is_valid_email(addr: str | None) -> bool:
    """校验邮箱格式是否可用作收件人。"""
    if not addr or not isinstance(addr, str):
        return False
    return bool(_EMAIL_RE.match(addr.strip()))


def extract_email_from_text(text: str | None) -> str | None:
    """从用户话术中提取邮箱；无则 None。"""
    if not text:
        return None
    m = _EMAIL_IN_TEXT_RE.search(text)
    if not m:
        return None
    addr = m.group(0).strip()
    return addr if is_valid_email(addr) else None


def send_research_email(
    *,
    subject: str,
    body: str,
    to_addr: str,
    pdf_bytes: bytes | None = None,
    pdf_filename: str | None = None,
) -> None:
    """同步 SMTP 发送；有 PDF 时以附件发出，正文为简短说明（不含投递回执）。"""
    settings = get_settings()
    host = settings.SMTP_HOST
    port = int(settings.SMTP_PORT)
    user = settings.SMTP_USER
    password = settings.SMTP_PASSWORD
    from_addr = settings.SMTP_FROM or user
    if not host or not user or not password or not from_addr:
        raise RuntimeError("SMTP 未完整配置")

    if pdf_bytes:
        msg: MIMEMultipart | MIMEText = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        plain = (
            body.strip()
            or "您好，附件为本次股票投研分析报告（PDF），请查收。"
        )
        msg.attach(MIMEText(plain, _subtype="plain", _charset="utf-8"))
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        fname = pdf_filename or "research_report.pdf"
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", fname))
        msg.attach(part)
    else:
        msg = MIMEText(body, _subtype="plain", _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr

    raw = msg.as_string()
    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(host, port, timeout=10) as smtp:
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to_addr], raw)
    else:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to_addr], raw)
