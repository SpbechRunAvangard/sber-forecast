"""Сборка матриц «серии x последние 180 дней» из сырых sales и stock (как приходят в API)."""
import numpy as np
import pandas as pd


def _fill(matrix, frame, idx, start):
    """Складываем значения frame (warehouse_name, article, date, value) в матрицу по индексам серий."""
    g = frame.groupby(["warehouse_name", "article", "date"], as_index=False)["value"].sum()
    rows = idx.get_indexer(pd.MultiIndex.from_frame(g[["warehouse_name", "article"]]))
    cols = (g["date"] - start).dt.days.values
    ok = rows >= 0                                  # серии, которых не было при обучении, пропускаем
    matrix[rows[ok], cols[ok]] = g["value"].values[ok]


def build_arrays(df_sales, df_stock, pairs, window=180):
    """
    df_sales — сырые продажи (несколько строк на день из-за composite_division суммируются)
    df_stock — сырые остатки (колонка char_article = article, дубли суммируются)
    pairs    — список пар [склад, артикул] в порядке серий модели
    Возвращает Qw, STw (серии x window) и последнюю дату в sales.
    """
    sales_dates = pd.to_datetime(df_sales["date"]).dt.normalize()
    last_date = sales_dates.max()
    start = last_date - pd.Timedelta(days=window - 1)
    idx = pd.MultiIndex.from_tuples([tuple(p) for p in pairs], names=["warehouse_name", "article"])

    s = pd.DataFrame({
        "warehouse_name": df_sales["warehouse_name"].astype(str).values,
        "article": df_sales["article"].astype(str).values,
        "date": sales_dates.values,
        "value": pd.to_numeric(df_sales["quantity"], errors="coerce").fillna(0.0).values,
    })
    s = s[(s["date"] >= start) & (s["date"] <= last_date)]
    Qw = np.zeros((len(idx), window), dtype=np.float32)          # дни без продаж = 0
    _fill(Qw, s, idx, start)

    k = pd.DataFrame({
        "warehouse_name": df_stock["warehouse_name"].astype(str).values,
        "article": df_stock["char_article"].astype(str).values,
        "date": pd.to_datetime(df_stock["date"]).dt.normalize().values,
        "value": pd.to_numeric(df_stock["stock"], errors="coerce").values,
    })
    k = k.dropna(subset=["value"])
    k = k[k["date"] <= last_date]                                # остатки позже последней даты sales не берём
    # Дубли (дата, склад, артикул) суммируем целиком, как требует ТЗ: без drop_duplicates.
    k = k.groupby(["warehouse_name", "article", "date"], as_index=False)["value"].sum()

    STw = np.full((len(idx), window), np.nan, dtype=np.float32)  # нет данных = NaN (остаток может быть отрицательным)
    _fill(STw, k[k["date"] >= start], idx, start)

    # Как в base_grid: остаток «тянется вперёд» от последнего известного значения (ffill),
    # NaN остаётся только до первого появления остатка. Если файл длиннее окна,
    # последнее значение до начала окна переносится в первый день окна.
    prev = (k[k["date"] < start].sort_values("date")
            .groupby(["warehouse_name", "article"], as_index=False).last())
    if len(prev):
        rows = idx.get_indexer(pd.MultiIndex.from_frame(prev[["warehouse_name", "article"]]))
        ok = (rows >= 0)
        rows, vals = rows[ok], prev["value"].values[ok]
        first_empty = np.isnan(STw[rows, 0])
        STw[rows[first_empty], 0] = vals[first_empty]
    STw = pd.DataFrame(STw.T).ffill().to_numpy().T.astype(np.float32)
    return Qw, STw, last_date
