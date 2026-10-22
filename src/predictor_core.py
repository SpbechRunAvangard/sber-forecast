"""Предсказание по массивам последних 180 дней. Это ядро для predictor.py в контейнере.

Контракт: на вход матрицы продаж и остатков (серии x 180 дней, NaN = данных нет),
названия складов и артикулов каждой серии. На выходе матрица прогноза (серии x 64 дня).
"""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

from . import features


def load_artifacts(model_dir):
    model_dir = Path(model_dir)
    cfg = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    booster = lgb.Booster(model_file=str(model_dir / "model.txt"))
    return {"cfg": cfg, "booster": booster}


def predict_from_arrays(Qw, STw, warehouses, articles, art):
    cfg = art["cfg"]
    window = cfg["window"]
    if Qw.shape[1] != window or STw.shape[1] != window:
        raise ValueError(f"Нужно ровно {window} дней, получено {Qw.shape[1]}")

    wh_index = {n: i for i, n in enumerate(cfg["warehouses"])}
    cat_index = {n: i for i, n in enumerate(cfg["categories"])}
    unknown = cat_index.get("unknown", -1)
    wh_code = np.array([wh_index.get(w, -1) for w in warehouses])
    cat_code = np.array([cat_index.get(cfg["article_category"].get(a, "unknown"), unknown)
                         for a in articles])

    Q0 = np.nan_to_num(Qw)
    first_idx = np.argmax(~np.isnan(Qw), axis=1)
    X = features.build_features(Q0, STw, window - 1, first_idx, wh_code, cat_code)

    rate = np.clip(art["booster"].predict(X), 0, None) * cfg["scale"]
    rate = np.where(rate < cfg["threshold"], 0.0, rate)
    return np.repeat(rate[:, None], cfg["horizon"], axis=1)
