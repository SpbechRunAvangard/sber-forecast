"""Сырые sales/stock -> дневные матрицы «ряд × день» (одинаково при обучении и в контейнере).

- Продажи: сумма quantity по date × склад × артикул (строки по департаментам и городам складываются).
- Остатки (на начало дня): все строки с одним ключом суммируются, отрицательные (резерв) сохраняются,
  дней без записи — NaN (без заполнения вперёд: так обучена модель).
- sales_sum и discount_sum хранятся как np.log: перед суммированием по дню применяется np.exp, как разрешает ТЗ.
  В признаки идут только отношения (цена сейчас / цена за полгода, доля скидки), абсолютные суммы не используются.
"""
import numpy as np
import pandas as pd

MIN_DAYS = 186   # самое длинное окно признаков — 26 недель (182 дня); короче история дополняется пустыми днями


def build_meta(warehouses, articles, article_cat1, article_cat2, cat1_levels=None, cat2_levels=None):
    """Сетка рядов «склад × артикул» в фиксированном порядке и категории артикулов с фиксированными кодами."""
    meta = (pd.MultiIndex.from_product([list(warehouses), list(articles)], names=['warehouse_name', 'article'])
            .to_frame(index=False))
    meta['sid'] = np.arange(len(meta))
    for col, mapping, levels in (('category_lvl_1', article_cat1, cat1_levels), ('category_lvl_2', article_cat2, cat2_levels)):
        values = meta.article.map(mapping).fillna('unknown')
        if levels is not None:
            values = values.where(values.isin(levels), 'unknown')
            values = pd.Series(pd.Categorical(values, categories=levels), index=meta.index)
        meta[col] = values
    return meta


def meta_from_sales(sales):
    """Сетка для обучения: все склады × все артикулы из sales; категория — первая непустая по артикулу."""
    maps = {}
    for lvl in ('category_lvl_1', 'category_lvl_2'):
        maps[lvl] = sales.dropna(subset=[lvl]).drop_duplicates('article').set_index('article')[lvl].to_dict()
    return build_meta(sorted(sales.warehouse_name.unique()), sorted(sales.article.unique()),
                      maps['category_lvl_1'], maps['category_lvl_2'])


def build_arrays(sales, stock, meta, cutoff=None):
    """
    sales, stock — сырые DataFrame (stock с колонкой char_article); cutoff — последняя используемая дата
    (по умолчанию максимальная дата в sales). Возвращает Q, ST, SV, DV (ряды × дни), d0 (дата нулевого дня), cutoff.
    """
    sales = sales.copy(); stock = stock.copy()
    sales['date'] = pd.to_datetime(sales['date'], format='%Y-%m-%d')
    stock['date'] = pd.to_datetime(stock['date'], format='%Y-%m-%d')
    if 'char_article' in stock.columns:
        stock = stock.rename(columns={'char_article': 'article'})
    cutoff = pd.Timestamp(cutoff) if cutoff is not None else sales['date'].max()
    d0 = min(sales['date'].min(), stock['date'].min())
    if (cutoff - d0).days + 1 < MIN_DAYS:
        d0 = cutoff - pd.Timedelta(days=MIN_DAYS - 1)
    S, D = len(meta), (cutoff - d0).days + 1
    keys = meta[['warehouse_name', 'article', 'sid']].astype({'warehouse_name': str, 'article': str})

    sl = sales[sales['date'] <= cutoff].copy()
    sl['warehouse_name'] = sl['warehouse_name'].astype(str); sl['article'] = sl['article'].astype(str)
    sl['quantity'] = pd.to_numeric(sl['quantity'], errors='coerce').fillna(0.0)
    q = sl.groupby(['date', 'warehouse_name', 'article'], as_index=False).quantity.sum().merge(keys)
    Q = np.zeros((S, D), np.float32); Q[q.sid.values, (q.date - d0).dt.days.values] = q.quantity.values

    st = stock[stock['date'] <= cutoff].copy()
    st['warehouse_name'] = st['warehouse_name'].astype(str); st['article'] = st['article'].astype(str)
    st['stock'] = pd.to_numeric(st['stock'], errors='coerce')
    s = st.groupby(['date', 'warehouse_name', 'article'], as_index=False).stock.sum().merge(keys)
    ST = np.full((S, D), np.nan, np.float32); ST[s.sid.values, (s.date - d0).dt.days.values] = s.stock.values

    sl['sv'] = np.exp(pd.to_numeric(sl['sales_sum'], errors='coerce').fillna(-np.inf))
    dsum = pd.to_numeric(sl['discount_sum'], errors='coerce')
    sl['dv'] = np.where(dsum.isna(), 0.0, np.exp(dsum))        # null = скидки нет
    g = sl.groupby(['date', 'warehouse_name', 'article'], as_index=False)[['sv', 'dv']].sum().merge(keys)
    SV = np.zeros((S, D), np.float32); DV = np.zeros((S, D), np.float32)
    di = (g.date - d0).dt.days.values
    SV[g.sid.values, di] = g.sv.values; DV[g.sid.values, di] = g.dv.values
    return Q, ST, SV, DV, d0, cutoff
