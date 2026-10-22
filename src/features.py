"""Признаки для прогноза продаж. Единый источник кода для ноутбука и контейнера.

Правила: используются только данные до даты отсечки включительно, окна не длиннее 180 дней.
"""
import warnings

import numpy as np
import pandas as pd

WINDOW = 180
AGE_CAP = WINDOW - 1   # контейнер видит ровно 180 дней, поэтому возраст ряда ограничен 179

FEATURE_ORDER = [
    "mean_7", "mean_14", "mean_28", "mean_56", "mean_90", "mean_180",
    "share_pos_28", "share_pos_90", "share_pos_180", "max_90", "max_180",
    "days_since_sale", "stock_last", "stock_missing_last", "oos_share_30", "oos_share_90",
    "stock_missing_90", "stock_mean_90", "mean_in_stock_90", "age", "warehouse", "category",
]


def build_features(Q0, ST, c, first_idx, wh_code, cat_code):
    """
    Q0  — продажи (серии x дни), пропуски заменены нулями
    ST  — остатки (серии x дни), NaN = данных нет
    c   — индекс последнего известного дня
    first_idx — индекс первого дня ряда, wh_code / cat_code — коды склада и категории
    """
    f = {}
    for w in (7, 14, 28, 56, 90, 180):
        f[f"mean_{w}"] = Q0[:, c - w + 1:c + 1].mean(axis=1)
    for w in (28, 90, 180):
        f[f"share_pos_{w}"] = (Q0[:, c - w + 1:c + 1] > 0).mean(axis=1)
    for w in (90, 180):
        f[f"max_{w}"] = Q0[:, c - w + 1:c + 1].max(axis=1)

    pos = Q0[:, c - 179:c + 1] > 0
    f["days_since_sale"] = np.where(pos.any(axis=1), 179 - np.argmax(pos[:, ::-1], axis=1), 180)

    s = ST[:, c - 179:c + 1]
    f["stock_last"] = s[:, -1]
    f["stock_missing_last"] = np.isnan(s[:, -1]).astype(np.float32)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for w in (30, 90):
            sw = s[:, -w:]
            zero_share = np.where(np.isnan(sw), np.nan, (sw == 0).astype(np.float32))
            f[f"oos_share_{w}"] = np.nanmean(zero_share, axis=1)
        f["stock_missing_90"] = np.isnan(s[:, -90:]).mean(axis=1)
        f["stock_mean_90"] = np.nanmean(s[:, -90:], axis=1)

    q90 = Q0[:, c - 89:c + 1]
    in_stock = ST[:, c - 90:c] > 0
    cnt_in = in_stock.sum(axis=1)
    f["mean_in_stock_90"] = np.where(
        cnt_in > 0, (q90 * in_stock).sum(axis=1) / np.maximum(cnt_in, 1), np.nan)

    f["age"] = np.minimum(c - first_idx, AGE_CAP)
    f["warehouse"] = wh_code
    f["category"] = cat_code

    X = pd.DataFrame(f)[FEATURE_ORDER]
    X["warehouse"] = X["warehouse"].astype("category")
    X["category"] = X["category"].astype("category")
    return X
