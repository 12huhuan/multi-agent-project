"""通知模块 — 邮件 + Server酱 双通道"""

import os
import smtplib
from email.mime.text import MIMEText

import httpx

# Server酱
SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY", "")
# 邮件
EMAIL_SMTP = os.getenv("NOTIFY_EMAIL_SMTP", "")
EMAIL_PORT = int(os.getenv("NOTIFY_EMAIL_PORT", "465"))
EMAIL_FROM = os.getenv("NOTIFY_EMAIL_FROM", "")
EMAIL_PASSWORD = os.getenv("NOTIFY_EMAIL_PASSWORD", "")
EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO", "")
# 企微
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "")
# PushPlus
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "")


async def send_notification(title: str, content: str = "") -> bool:
    """双通道通知：邮件 + Server酱 同时发送"""
    results = []

    # 邮件（锁屏可见，不会被折叠）
    if EMAIL_SMTP and EMAIL_FROM and EMAIL_PASSWORD and EMAIL_TO:
        results.append(_send_email(title, content))

    # Server酱（微信服务号）
    if SERVERCHAN_SENDKEY:
        results.append(await _send_serverchan(title, content))
    elif WECOM_WEBHOOK_URL:
        results.append(await _send_wecom(f"{title}\n{content}" if content else title))
    elif PUSHPLUS_TOKEN:
        results.append(await _send_pushplus(title, content))

    if not results:
        print(f"[通知] {title}: {content[:200]}")
        return False
    return any(results)


def _send_email(title: str, content: str = "") -> bool:
    """QQ邮箱 SMTP 发送通知"""
    try:
        msg = MIMEText(content or title, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        server = smtplib.SMTP_SSL(EMAIL_SMTP, EMAIL_PORT)
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[邮件] 发送失败: {e}")
        return False


async def _send_serverchan(title: str, content: str = "") -> bool:
    """Server酱 推送 (微信接收)"""
    url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
    body = {"title": title, "desp": content or title}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json=body)
            return r.status_code == 200 and r.json().get("code") == 0
    except Exception as e:
        print(f"[Server酱] 失败: {e}")
    return False


async def _send_wecom(content: str) -> bool:
    """企微群机器人"""
    body = {"msgtype": "text", "text": {"content": content}}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(WECOM_WEBHOOK_URL, json=body)
            return r.status_code == 200
    except Exception:
        pass
    return False


async def _send_pushplus(title: str, content: str = "") -> bool:
    """PushPlus 推送"""
    url = "https://www.pushplus.plus/send"
    body = {"token": PUSHPLUS_TOKEN, "title": title, "content": content or title}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json=body)
            return r.status_code == 200 and r.json().get("code") == 200
    except Exception:
        pass
    return False


# 兼容旧接口
send_wecom_message = send_notification
