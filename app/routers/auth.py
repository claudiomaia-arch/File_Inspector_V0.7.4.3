from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import secrets
import hashlib
import os

from app.database import get_conn
from app.security import hash_password, check_password
from app.services.mailer import send_password_reset_email

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/")
def home(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (email.strip(),)).fetchone()
    if not user or not check_password(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {"request": request, "error": "E-mail ou senha inválidos."})
    request.session["user_id"] = user["id"]
    request.session["user_name"] = user["name"]
    return RedirectResponse("/dashboard", status_code=303)

@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@router.post("/register")
def register(request: Request,
             name: str = Form(...),
             email: str = Form(...),
             company: str = Form(""),
             password: str = Form(...)):
    if len(password) < 4:
        return templates.TemplateResponse("register.html", {"request": request, "error": "A senha deve ter pelo menos 4 caracteres."})
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users(name,email,company,password_hash,created_at) VALUES(?,?,?,?,?)",
                (name.strip(), email.strip(), company.strip(), hash_password(password), datetime.now().isoformat(timespec="seconds"))
            )
    except Exception:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Este e-mail já está cadastrado."})
    return RedirectResponse("/", status_code=303)


@router.get("/forgot-password")
def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "message": None
    })

@router.post("/forgot-password")
def forgot_password(request: Request, email: str = Form(...)):
    email = email.strip()
    generic_message = (
        "Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha."
    )

    with get_conn() as conn:
        user = conn.execute(
            "SELECT id,email,name FROM users WHERE lower(email)=lower(?)", (email,)
        ).fetchone()

        if user:
            # Invalida tokens anteriores ainda não usados.
            conn.execute(
                "UPDATE password_reset_tokens SET used_at=? "
                "WHERE user_id=? AND used_at IS NULL",
                (datetime.now().isoformat(timespec="seconds"), user["id"])
            )

            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            now = datetime.now()
            expires = now + timedelta(minutes=15)

            conn.execute(
                """INSERT INTO password_reset_tokens
                   (user_id,token_hash,expires_at,used_at,created_at)
                   VALUES(?,?,?,?,?)""",
                (
                    user["id"],
                    token_hash,
                    expires.isoformat(timespec="seconds"),
                    None,
                    now.isoformat(timespec="seconds")
                )
            )

            base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
            reset_link = f"{base_url}/reset-password?token={raw_token}"
            ok, internal = send_password_reset_email(user["email"], reset_link)

            # Nunca expõe existência do e-mail nem o token ao usuário.
            # A falha fica apenas no terminal para diagnóstico.
            if not ok:
                print(f"[PASSWORD_RESET] {internal}")

    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "message": generic_message
    })

@router.get("/reset-password")
def reset_password_page(request: Request, token: str):
    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "token": token,
        "error": None,
        "success": None
    })

@router.post("/reset-password")
def reset_password(request: Request,
                   token: str = Form(...),
                   password: str = Form(...),
                   password_confirm: str = Form(...)):
    if password != password_confirm:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "token": token,
            "error": "As senhas não coincidem.", "success": None
        })
    if len(password) < 8:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "token": token,
            "error": "A nova senha deve ter pelo menos 8 caracteres.", "success": None
        })

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now()

    with get_conn() as conn:
        row = conn.execute(
            """SELECT prt.*, u.email
               FROM password_reset_tokens prt
               JOIN users u ON u.id=prt.user_id
               WHERE prt.token_hash=?""",
            (token_hash,)
        ).fetchone()

        if not row or row["used_at"]:
            return templates.TemplateResponse("reset_password.html", {
                "request": request, "token": token,
                "error": "Este link é inválido ou já foi utilizado.", "success": None
            })

        expires = datetime.fromisoformat(row["expires_at"])
        if now > expires:
            return templates.TemplateResponse("reset_password.html", {
                "request": request, "token": token,
                "error": "Este link expirou. Solicite uma nova redefinição.", "success": None
            })

        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(password), row["user_id"])
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used_at=? WHERE id=?",
            (now.isoformat(timespec="seconds"), row["id"])
        )

    return templates.TemplateResponse("reset_password.html", {
        "request": request, "token": "",
        "error": None,
        "success": "Senha redefinida com sucesso. Você já pode entrar no CAD Inspector."
    })

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
