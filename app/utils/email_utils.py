from email.message import EmailMessage
import hashlib
import secrets
from pydantic import EmailStr
from fastapi.templating import Jinja2Templates
from app.core.config import settings
import aiosmtplib


templates = Jinja2Templates(directory="templates")



async def send_email(
        to_email: EmailStr,
        subject: str,
        content: str,
        html_content: str | None = None
):
    message = EmailMessage()
    message["From"] = settings.MAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(content)

    if html_content:
        message.add_alternative(html_content, subtype="html")


    await aiosmtplib.send(
        message,
        hostname=settings.MAIL_SERVER,
        port=settings.MAIL_PORT,
        username=settings.MAIL_USERNAME or None,
        password=settings.MAIL_PASSWORD.get_secret_value() or None,
        use_tls=settings.MAIL_USE_TLS,
        start_tls=settings.MAIL_START_TLS,
    )


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)

def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()




async def send_password_reset_email(to_email: str, name: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    template = templates.env.get_template("password_reset.html")

    html_content = template.render(reset_url=reset_url,name=name)


    plain_text = f"""Hi {name},

You requested to reset your password. Click the link below to set a new password:

{reset_url}

This link will expire in 1 hour.

If you didn't request this, you can safely ignore this email.

Best regards,
The Shopping Team
"""

    await send_email(
        to_email, 
        "Reset Your Password - FastapiShop", 
        plain_text, 
        html_content
    )