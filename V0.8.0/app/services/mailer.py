import os
import smtplib
from email.message import EmailMessage

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def send_password_reset_email(recipient: str, reset_link: str) -> tuple[bool, str]:
    """
    Envia o link de redefinição por SMTP.
    Retorna (ok, mensagem_interna).
    """
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", user).strip()
    use_tls = _env_bool("SMTP_TLS", True)

    # Modo de desenvolvimento é opcional e deve ser usado somente no piloto local.
    if not host:
        if _env_bool("EMAIL_DEV_MODE", False):
            print(f"[EMAIL_DEV_MODE] Reset para {recipient}: {reset_link}")
            return True, "Link registrado no terminal em modo de desenvolvimento."
        return False, "SMTP não configurado."

    msg = EmailMessage()
    msg["Subject"] = "Redefinição de senha — CAD Inspector"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        "Foi solicitada uma redefinição de senha para o CAD Inspector.\n\n"
        f"Acesse o link abaixo para criar uma nova senha:\n{reset_link}\n\n"
        "Este link expira em 15 minutos e só pode ser usado uma vez.\n"
        "Se você não solicitou a alteração, ignore esta mensagem."
    )

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True, "E-mail enviado."
    except Exception as e:
        return False, f"Falha SMTP: {e}"
