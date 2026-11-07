import io
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .predictor import NotReadyError, Predictor
from .validators import validate_sales_csv, validate_stock_csv

app = FastAPI(
    title="Hackathon Forecast API",
    description="Прогноз продаж по складам и товарам (9 недель)",
    version="1.0.0",
)

# Модель загружается в память при старте контейнера
predictor = Predictor.load(Path("model"))
INDEX_HTML = Path(__file__).with_name("static").joinpath("index.html")


class ApiError(Exception):
    """Ошибка с единым форматом ответа: {"detail": ..., "code": ...}."""

    def __init__(self, status_code: int, detail: str, code: str = "VALIDATION_ERROR"):
        self.status_code, self.detail, self.code = status_code, detail, code


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Нужны два файла: sales и stock (multipart/form-data)", "code": "VALIDATION_ERROR"},
    )


def csv_response(df: pd.DataFrame, filename: str) -> StreamingResponse:
    output = io.StringIO()
    df.to_csv(output, index=False)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def cached_forecast() -> pd.DataFrame:
    try:
        return predictor.get_cached_forecast()
    except NotReadyError as e:
        raise ApiError(409, str(e), code="FORECAST_NOT_READY")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    """Простой веб-интерфейс: загрузка двух CSV, скачивание прогноза, поиск по артикулу и складу."""
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/options")
async def options():
    """Списки складов и артикулов, по которым строится прогноз (для подсказок в интерфейсе)."""
    cfg = predictor.art["cfg"]
    return {"warehouses": cfg["warehouses"], "articles": cfg["articles"]}


@app.get("/status")
async def status():
    """Есть ли рассчитанный прогноз и краткая сводка по нему."""
    try:
        df = predictor.get_cached_forecast()
    except NotReadyError:
        return {"ready": False}
    first = df[df["week"] == df["week"].min()]
    return {
        "ready": True,
        "rows": int(len(df)),
        "weeks": sorted(df["week"].unique().tolist()),
        "series": int(len(first)),
        "series_nonzero": int((first["quantity"] > 0).sum()),
        "total_quantity": int(df["quantity"].sum()),
        "history_days": predictor.last_info.get("history_days"),
        "last_date": predictor.last_info.get("last_date"),
    }


def apply_cutoff(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    return df[pd.to_datetime(df["date"], format="%Y-%m-%d") <= cutoff].reset_index(drop=True)


@app.post("/predict")
async def predict_post(
    sales: bytes = File(...),
    stock: bytes = File(...),
    cutoff: Optional[str] = Query(None, description="Необязательно: последняя используемая дата YYYY-MM-DD "
                                                    "(более поздние строки отбрасываются)"),
):
    """Принимает два CSV (sales + stock) и возвращает CSV с прогнозом на 9 недель."""
    if not sales.strip() or not stock.strip():
        raise ApiError(400, "Пустой файл: нужны непустые sales и stock")
    try:
        df_sales = pd.read_csv(io.BytesIO(sales))
        df_stock = pd.read_csv(io.BytesIO(stock))
    except Exception as e:
        raise ApiError(400, f"Ошибка парсинга CSV: {e}")
    if df_sales.empty or df_stock.empty:
        raise ApiError(400, "Пустой файл: в sales или stock нет строк с данными")

    errors = validate_sales_csv(df_sales) + validate_stock_csv(df_stock)
    if errors:
        raise ApiError(422, "; ".join(errors))

    if cutoff:
        try:
            cutoff_ts = pd.to_datetime(cutoff, format="%Y-%m-%d")
        except Exception:
            raise ApiError(422, "Неверный формат cutoff (ожидается YYYY-MM-DD)")
        df_sales, df_stock = apply_cutoff(df_sales, cutoff_ts), apply_cutoff(df_stock, cutoff_ts)
        if df_sales.empty or df_stock.empty:
            raise ApiError(422, f"До даты {cutoff} в sales или stock нет данных")
        errors = validate_sales_csv(df_sales) + validate_stock_csv(df_stock)
        if errors:
            raise ApiError(422, "; ".join(errors))

    df_forecast = predictor.predict(df_sales, df_stock)
    return csv_response(df_forecast, "forecast.csv")


@app.get("/predict")
async def predict_get(
    article: Optional[str] = Query(None, description="Артикул товара"),
    warehouse: Optional[str] = Query(None, description="Наименование склада"),
):
    """Прогноз по артикулу и/или складу (CSV, 9 недель). Хотя бы один параметр обязателен."""
    if not article and not warehouse:
        raise ApiError(400, "Укажите хотя бы один параметр: article или warehouse")

    df_forecast = cached_forecast()
    mask = pd.Series(True, index=df_forecast.index)
    if article:
        mask &= df_forecast["article"] == article
    if warehouse:
        mask &= df_forecast["warehouse_name"] == warehouse
    return csv_response(df_forecast[mask], "filtered_forecast.csv")


@app.get("/predict/all")
async def predict_all(format: str = Query("csv", description="Формат ответа: csv или json")):
    """Весь прогноз целиком на 9 недель (79 101 строка при полном произведении 11 x 799)."""
    if format not in ("csv", "json"):
        raise ApiError(400, "Параметр format должен быть 'csv' или 'json'")
    df_forecast = cached_forecast()
    if format == "csv":
        return csv_response(df_forecast, "full_forecast.csv")
    return JSONResponse(content=df_forecast.to_dict(orient="records"))
