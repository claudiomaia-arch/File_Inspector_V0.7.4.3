from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db
from app.routers import auth, inspector

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="CAD / Usinagem Inspector", version="0.7.4.3")
app.add_middleware(SessionMiddleware, secret_key="cad-usinagem-inspector-local-v02-change-later")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(auth.router)
app.include_router(inspector.router)

@app.on_event("startup")
def startup():
    init_db()
