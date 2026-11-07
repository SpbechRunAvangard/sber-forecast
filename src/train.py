"""Обучение итоговой модели v6 из сырых CSV и сохранение артефактов для контейнера.

Запуск (из корня репозитория):
    python -m src.train data/raw/sales_dataset_hakaton_train.csv data/raw/stock_dataset_hakaton_train.csv \
        --cutoff 2026-07-26 --model-dir model --submission submission.csv

Пишет в model/: model_v6_base.txt, model_v6_ext.txt, model_v6_gain.txt и config.json
(списки складов, артикулов и категорий фиксируют коды признаков для контейнера).
По ТЗ для обучения используются данные только по 2026-07-26 включительно. Результат детерминирован.
"""
import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import config as C
from .data import build_arrays, meta_from_sales
from .model import predict, train


def submission_frame(meta, weekly, first_week):
    weeks = pd.date_range(first_week, periods=C.W, freq='7D').strftime('%Y-%m-%d')
    return pd.DataFrame({'week': np.tile(weeks, len(meta)),
                         'warehouse_name': np.repeat(meta.warehouse_name.astype(str).values, C.W),
                         'article': np.repeat(meta.article.astype(str).values, C.W),
                         'quantity': np.repeat(weekly, C.W).astype(int)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sales'); ap.add_argument('stock')
    ap.add_argument('--cutoff', default='2026-07-26')
    ap.add_argument('--model-dir', default='model')
    ap.add_argument('--submission', default=None)
    a = ap.parse_args()

    sales = pd.read_csv(a.sales, usecols=['date', 'warehouse_name', 'article', 'category_lvl_1', 'category_lvl_2',
                                          'quantity', 'sales_sum', 'discount_sum'])
    stock = pd.read_csv(a.stock)
    meta = meta_from_sales(sales)
    Q, ST, SV, DV, d0, cutoff = build_arrays(sales, stock, meta, cutoff=a.cutoff)
    boosters, ext = train(Q, ST, SV, DV, meta, d0)

    out = Path(a.model_dir); out.mkdir(parents=True, exist_ok=True)
    for k, b in boosters.items():
        b.save_model(str(out / C.MODEL_FILES[k]))
    cat_maps = {lvl: dict(zip(meta.article, meta[lvl])) for lvl in ('category_lvl_1', 'category_lvl_2')}
    cfg = {
        'model': 'v6', 'kind': 'lightgbm', 'lightgbm_version': lgb.__version__,
        'weeks': C.W, 'horizon_days': C.H, 'train_cutoff': str(cutoff.date()),
        'min_history_days': C.MIN_HISTORY_DAYS, 'full_history_days': C.FULL_HISTORY_DAYS,
        'season_power': C.SEASON_POWER, 'scale': C.SCALE, 'threshold': C.THRESHOLD,
        'model_files': C.MODEL_FILES, 'base_features': C.BASE_FEATURES, 'ext_features': ext,
        'warehouses': sorted(meta.warehouse_name.unique().tolist()),
        'articles': sorted(meta.article.unique().tolist()),
        'cat1_levels': sorted(meta.category_lvl_1.unique().tolist()),
        'cat2_levels': sorted(meta.category_lvl_2.unique().tolist()),
        'article_cat1': {k: cat_maps['category_lvl_1'][k] for k in sorted(cat_maps['category_lvl_1'])},
        'article_cat2': {k: cat_maps['category_lvl_2'][k] for k in sorted(cat_maps['category_lvl_2'])},
        'seed': C.SEED,
    }
    (out / 'config.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf-8')

    if a.submission:
        weekly, info = predict(boosters, Q, ST, SV, DV, meta, d0)
        first_week = cutoff - pd.Timedelta(days=cutoff.weekday()) + pd.Timedelta(days=7)
        sub = submission_frame(meta, weekly, first_week)
        assert not sub.duplicated(['week', 'warehouse_name', 'article']).any() and (sub.quantity >= 0).all()
        sub.to_csv(a.submission, index=False)
        print(f'{len(sub)} строк; сезонная поправка {info["season"] ** C.SEASON_POWER * C.SCALE:.3f}; '
              f'прогноз за 9 недель {weekly.sum() * C.W:,.0f} шт.; обнулено рядов: {(weekly == 0).mean():.1%}')


if __name__ == '__main__':
    main()
