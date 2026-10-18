from __future__ import annotations

import logging
import time

from app.agent.logging_util import check_deadline
from app.agent.tools.email import is_valid_email, send_research_email
from app.agent.tools.report_pdf import markdown_to_pdf_bytes, safe_pdf_filename
from app.common.config import get_settings
from app.common.logging_util import event_msg

logger = logging.getLogger(__name__)


def _resolve_to_addr(intent: dict) -> str | None:
    """优先用户话术中的邮箱，否则回落 RESEARCH_DEFAULT_EMAIL。"""
    user_to = (intent.get("to_email") or "").strip()
    if is_valid_email(user_to):
        return user_to
    settings = get_settings()
    default_to = (settings.RESEARCH_DEFAULT_EMAIL or "").strip()
    return default_to if is_valid_email(default_to) else None


def mailer_node(state: dict) -> dict:
    """发信闸门：超时/无标的则跳过；成功时发 PDF，投递说明只写进聊天正文。"""
    patch = check_deadline(state)
    timed_out = bool(state.get("timed_out") or patch.get("timed_out"))
    # 发信用干净正文；投递说明只追加到聊天 report_md，不进 PDF
    report = (state.get("report_md") or "").rstrip()
    intent = state.get("intent") or {}
    want_email = bool(intent.get("want_email"))
    skip_analysts = bool(state.get("skip_analysts"))

    def finish(status: str, *, note: str | None = None) -> dict:
        """写回 delivery_status，必要时把说明追加到 report_md。"""
        out = {"delivery_status": status, "report_md": report}
        if timed_out or (state.get("deadline_ts") and time.time() > float(state["deadline_ts"])):
            out["timed_out"] = True
        if note and (want_email or timed_out):
            out["report_md"] = f"{report}\n\n{note}".strip()
        return out

    if timed_out or (state.get("deadline_ts") and time.time() > float(state["deadline_ts"])):
        return finish("已跳过（超时）", note="未发送邮件（超时）。")

    if skip_analysts:
        return finish(
            "已跳过（无有效标的）",
            note="未发送邮件（未识别有效股票标的）。" if want_email else None,
        )

    if not want_email:
        return finish("已跳过（用户未要求发信）")

    to_addr = _resolve_to_addr(intent)
    if not to_addr:
        return finish(
            "已跳过（无可用收件人）",
            note="未发送邮件：请在话术中写明邮箱，或配置 RESEARCH_DEFAULT_EMAIL。",
        )

    name = intent.get("asset_name") or "标的"
    code = intent.get("asset_code") or ""
    title = f"{name}（{code}）深度市场分析报告" if code else f"{name}深度市场分析报告"
    subject = title
    pdf_name = safe_pdf_filename(title)
    try:
        pdf_bytes = markdown_to_pdf_bytes(report)
    except Exception as exc:
        logger.warning(event_msg("mailer_node", err=exc))
        pdf_bytes = None

    plain_body = (
        f"您好，附件为「{title}」（PDF），请查收。\n"
        "本邮件由 Knowledge Hub 自动发送。"
        if pdf_bytes
        else report
    )
    try:
        send_research_email(
            subject=subject,
            body=plain_body,
            to_addr=to_addr,
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_name if pdf_bytes else None,
        )
        return finish(f"报告已发送至 {to_addr}", note=f"报告已发送至 {to_addr}。")
    except Exception as exc:
        logger.warning(event_msg("mailer_node", err=exc))
        return finish(f"发送失败: {exc}", note=f"邮件发送失败：{exc}")
