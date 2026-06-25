from __future__ import annotations

from minstock.config import load_settings
from minstock.db import connect, init_db
from minstock.services import InventoryService

settings = load_settings()
connection = connect(settings.database_path)
init_db(connection)
inventory = InventoryService(connection)

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path

app = FastAPI(title="MiniStock")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/stock", response_class=HTMLResponse)
async def stock(request: Request, q: str = ""):
    rows = inventory.stock_rows(limit=200)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["article"].lower() or ql in r["name"].lower()]
    return templates.TemplateResponse("stock.html", {"request": request, "rows": rows, "q": q})


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request, days: int = 30):
    rows = inventory.history(days=days)
    return templates.TemplateResponse("history.html", {"request": request, "rows": rows, "days": days})


@app.get("/purchases", response_class=HTMLResponse)
async def purchases(request: Request):
    rows = inventory.purchase_rows()
    return templates.TemplateResponse("purchases.html", {"request": request, "rows": rows})


@app.get("/export")
async def export():
    data = inventory.generate_excel()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=minstock.xlsx"},
    )
