from __future__ import annotations

import logging
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pathlib import Path

from minstock.config import load_settings
from minstock.db import connect, init_db
from minstock.services import InventoryService

settings = load_settings()
connection = connect(settings.database_path)
init_db(connection)
inventory = InventoryService(connection)

logger = logging.getLogger(__name__)
app = FastAPI(title="MiniStock")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
security = HTTPBasic(auto_error=False)


def _check_secret(credentials: HTTPBasicCredentials | None) -> bool:
    if not settings.web_auth_secret:
        return True
    if credentials is None:
        return False
    return secrets.compare_digest(credentials.password, settings.web_auth_secret)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    if not _check_secret(credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/stock", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def stock(request: Request, q: str = ""):
    rows = inventory.stock_rows(limit=200)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["article"].lower() or ql in r["name"].lower()]
    return templates.TemplateResponse("stock.html", {"request": request, "rows": rows, "q": q})


@app.get("/history", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def history(request: Request, days: int = 30):
    rows = inventory.history(days=days)
    return templates.TemplateResponse("history.html", {"request": request, "rows": rows, "days": days})


@app.get("/purchases", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def purchases(request: Request):
    rows = inventory.purchase_rows()
    return templates.TemplateResponse("purchases.html", {"request": request, "rows": rows})


@app.get("/export", dependencies=[Depends(require_auth)])
async def export():
    data = inventory.generate_excel()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=minstock.xlsx"},
    )
