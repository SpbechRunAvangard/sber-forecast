from typing import List

import pandas as pd

SALES_REQUIRED_COLS = [
    "date", "warehouse_name", "article", "quantity",
    "sales_sum", "discount_sum",
    "composite_division", "cities_name",
    "category_lvl_1", "category_lvl_2", "category_lvl_3",
    "characteristic",
]

STOCK_REQUIRED_COLS = ["date", "warehouse_name", "char_article", "stock"]

MIN_HISTORY_DAYS = 180


def validate_sales_csv(df: pd.DataFrame) -> List[str]:
    errors = []
    missing = set(SALES_REQUIRED_COLS) - set(df.columns)
    if missing:
        errors.append(f"Отсутствуют колонки в sales: {sorted(missing)}")
        return errors

    try:
        dates = pd.to_datetime(df["date"], format="%Y-%m-%d")
    except Exception:
        errors.append("Неверный формат даты в sales (ожидается YYYY-MM-DD)")
        return errors

    history_days = (dates.max() - dates.min()).days + 1
    if history_days < MIN_HISTORY_DAYS:
        errors.append(f"Недостаточно истории в sales: {history_days} дней, минимум {MIN_HISTORY_DAYS}")

    # Null в discount_sum означает отсутствие скидки. Здесь его не трогаем: discount_sum хранится как np.log,
    # и замена null на 0 означала бы скидку exp(0) = 1. Null обрабатывается в src/data.py (скидка = 0).

    quantity = pd.to_numeric(df["quantity"], errors="coerce")
    if quantity.isna().any():
        errors.append("В quantity есть нечисловые или пустые значения")
    elif (quantity < 0).any():
        errors.append("Найдены отрицательные значения в quantity")

    return errors


def validate_stock_csv(df: pd.DataFrame) -> List[str]:
    errors = []
    # По ТЗ колонка артикула в stock — char_article; в выданном обучающем файле она называется article.
    # Принимаем оба варианта.
    if "char_article" not in df.columns and "article" in df.columns:
        df.rename(columns={"article": "char_article"}, inplace=True)
    missing = set(STOCK_REQUIRED_COLS) - set(df.columns)
    if missing:
        errors.append(f"Отсутствуют колонки в stock: {sorted(missing)}")
        return errors

    try:
        dates = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise")
    except Exception:
        errors.append("Неверный формат даты в stock (ожидается YYYY-MM-DD)")
        return errors

    history_days = (dates.max() - dates.min()).days + 1
    if history_days < MIN_HISTORY_DAYS:
        errors.append(f"Недостаточно истории в stock: {history_days} дней, минимум {MIN_HISTORY_DAYS}")

    # Отрицательные значения stock допустимы: это зарезервированный товар.
    if pd.to_numeric(df["stock"], errors="coerce").isna().any():
        errors.append("В stock есть нечисловые или пустые значения")

    return errors
