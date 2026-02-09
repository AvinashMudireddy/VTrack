from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fpdf import FPDF

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
CSV_PATH = DATA_DIR / "vehicle_status.csv"
XLSX_PATH = DATA_DIR / "vehicle_status.xlsx"
PDF_PATH = DATA_DIR / "vehicle_status.pdf"

FIELDNAMES = [
    "timestamp",
    "handled_by",
    "stock_id",
    "vin",
    "current_location",
    "previous_location",
]

app = FastAPI()
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def _init_csv() -> None:
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def _find_previous_location(vin: str, stock_id: str) -> Optional[str]:
    if not CSV_PATH.exists():
        return None

    previous = None
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("vin") == vin or row.get("stock_id") == stock_id:
                previous = row.get("current_location") or previous
    return previous


def _load_records() -> list[dict[str, str]]:
    _init_csv()
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _find_latest_record_by_vin(vin: str) -> Optional[dict[str, str]]:
    rows = _load_records()
    latest = None
    for row in rows:
        if row.get("vin") == vin:
            latest = row
    return latest


def _delete_records_by_vin(vin: str) -> int:
    _init_csv()
    if not CSV_PATH.exists():
        return 0

    removed = 0
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    remaining = []
    for row in rows:
        if row.get("vin") == vin:
            removed += 1
            continue
        remaining.append(row)

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(remaining)

    return removed


def _build_excel() -> None:
    rows = _load_records()
    df = pd.DataFrame(rows, columns=FIELDNAMES)
    df.to_excel(XLSX_PATH, index=False)


def _build_pdf() -> None:
    rows = _load_records()
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    col_widths = [40, 30, 25, 40, 55, 55]
    headers = [
        "Timestamp",
        "Handled By",
        "Stock ID",
        "VIN",
        "Current Location",
        "Previous Location",
    ]

    pdf.set_fill_color(15, 107, 107)
    pdf.set_text_color(255, 255, 255)
    for header, width in zip(headers, col_widths):
        pdf.cell(width, 8, header, border=1, fill=True)
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    for row in rows:
        values = [
            row.get("timestamp", ""),
            row.get("handled_by", ""),
            row.get("stock_id", ""),
            row.get("vin", ""),
            row.get("current_location", ""),
            row.get("previous_location", ""),
        ]
        for value, width in zip(values, col_widths):
            pdf.cell(width, 7, value[:50], border=1)
        pdf.ln()

    pdf.output(str(PDF_PATH))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    _init_csv()
    return templates.TemplateResponse(
        "index.html",
        {"request": request},
    )


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, vin: str = ""):
    vin = vin.strip()
    if not vin:
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "search_error": None,
                "result": None,
                "searched_vin": None,
            },
        )

    result = _find_latest_record_by_vin(vin)
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "search_error": None if result else "No records found for that VIN.",
            "result": result,
            "searched_vin": vin,
        },
    )


@app.get("/update", response_class=HTMLResponse)
def update_form(request: Request):
    _init_csv()
    error = request.query_params.get("error")
    success = request.query_params.get("success")
    return templates.TemplateResponse(
        "update.html",
        {
            "request": request,
            "error": error,
            "success": success,
        },
    )


@app.post("/update")
def submit(
    handled_by: str = Form(...),
    vin: str = Form(...),
    stock_id: str = Form(...),
    current_location: str = Form(...),
):
    handled_by = handled_by.strip()
    vin = vin.strip()
    stock_id = stock_id.strip()
    current_location = current_location.strip()

    if not all([handled_by, vin, stock_id, current_location]):
        return RedirectResponse(url="/update?error=All%20fields%20are%20required.", status_code=303)

    previous_location = _find_previous_location(vin=vin, stock_id=stock_id)

    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "handled_by": handled_by,
                "stock_id": stock_id,
                "vin": vin,
                "current_location": current_location,
                "previous_location": previous_location or "",
            }
        )

    return RedirectResponse(url="/update?success=Saved%20update.", status_code=303)


@app.get("/download/csv")
def download_csv():
    _init_csv()
    return FileResponse(CSV_PATH, filename="vehicle_status.csv")


@app.get("/download/excel")
def download_excel():
    _build_excel()
    return FileResponse(XLSX_PATH, filename="vehicle_status.xlsx")


@app.get("/download/pdf")
def download_pdf():
    _build_pdf()
    return FileResponse(PDF_PATH, filename="vehicle_status.pdf")


@app.get("/delete", response_class=HTMLResponse)
def delete_form(request: Request):
    error = request.query_params.get("error")
    delete_message = request.query_params.get("delete")
    return templates.TemplateResponse(
        "delete.html",
        {
            "request": request,
            "error": error,
            "delete_message": delete_message,
        },
    )


@app.post("/delete")
def delete_vehicle(vin: str = Form(...)):
    vin = vin.strip()
    if not vin:
        return RedirectResponse(url="/delete?error=VIN%20is%20required%20to%20delete.", status_code=303)

    removed = _delete_records_by_vin(vin)
    if removed == 0:
        return RedirectResponse(url="/delete?error=No%20records%20found%20for%20that%20VIN.", status_code=303)

    return RedirectResponse(url="/delete?delete=Deleted%20" + str(removed) + "%20record(s).", status_code=303)
