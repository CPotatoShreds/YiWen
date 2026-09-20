"""邮件发送：console（开发，写日志）与 SMTP 双实现。

生产建议用阿里云邮件推送（DirectMail）的 SMTP 端点（smtpdm.aliyun.com:465），
与自建/免费 SMTP 共用同一条 SMTP 代码路径，仅配置不同。console 实现只把邮件
内容写进日志，供开发与测试环境零配置使用。
"""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("mail")


async def send_email(to: str, subject: str, body: str) -> None:
    """发送纯文本邮件。失败抛异常，由调用方决定是否吞掉（对外一律 202）。"""
    mail_settings = get_settings()
    if mail_settings.EMAIL_PROVIDER == "console":
        logger.warning("MAIL(console) to=%s subject=%s\n%s", to, subject, body)
        return

    def _send() -> None:
        message = EmailMessage()
        message["From"] = mail_settings.EMAIL_FROM
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if mail_settings.SMTP_PORT == 465:
            client = smtplib.SMTP_SSL(mail_settings.SMTP_HOST, 465, timeout=10)
        else:
            client = smtplib.SMTP(mail_settings.SMTP_HOST, mail_settings.SMTP_PORT, timeout=10)
            client.starttls(context=ssl.create_default_context())
        with client:
            client.login(mail_settings.SMTP_USERNAME, mail_settings.SMTP_PASSWORD)
            client.send_message(message)

    await asyncio.to_thread(_send)
