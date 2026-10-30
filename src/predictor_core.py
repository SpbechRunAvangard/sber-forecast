"""Инференс итоговой модели v6 по сырым sales/stock (ядро для app/predictor.py).

Контракт: на вход сырые DataFrame sales и stock (формат обучающих CSV), на выход DataFrame в формате submission
(week, warehouse_name, article, quantity) по всем 11 × 799 парам из config.json — 79 101 строка.
Первая неделя — понедельник календарной недели, следующей за неделей последней даты в sales.
"""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .data import build_arrays, build_meta
from .model import predict


def load_artifacts(model_dir):
    model_dir = Path(model_dir)
    cfg = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    boosters = {k: lgb.Booster(model_file=str(model_dir / f)) for k, f in cfg["model_files"].items()}
    meta = build_meta(cfg["warehouses"], cfg["articles"], cfg["article_cat1"], cfg["article_cat2"],
                      cfg["cat1_levels"], cfg["cat2_levels"])
    return {"cfg": cfg, "boosters": boosters, "meta": meta}


def forecast(df_sales, df_stock, art):
    cfg, meta = art["cfg"], art["meta"]
    Q, ST, SV, DV, d0, last_date = build_arrays(df_sales, df_stock, meta)
    weekly, info = predict(art["boosters"], Q, ST, SV, DV, meta, d0)
    first_week = last_date - pd.Timedelta(days=last_date.weekday()) + pd.Timedelta(days=7)
    weeks = pd.date_range(first_week, periods=cfg["weeks"], freq="7D").strftime("%Y-%m-%d")
    df = pd.DataFrame({
        "week": np.tile(weeks, len(meta)),
        "warehouse_name": np.repeat(meta.warehouse_name.astype(str).values, cfg["weeks"]),
        "article": np.repeat(meta.article.astype(str).values, cfg["weeks"]),
        "quantity": np.repeat(weekly, cfg["weeks"]).astype(int),
    })
    info["history_days"] = int((last_date - pd.to_datetime(df_sales["date"]).min()).days) + 1
    return df, info
