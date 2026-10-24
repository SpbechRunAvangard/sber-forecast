import pandas as pd

def load_raw_data(sales_path: str, stock_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Загружает сырые CSV файлы."""
    df_sales = pd.read_csv(sales_path, parse_dates=["date"])
    df_stock = pd.read_csv(stock_path, parse_dates=["date"])
    return df_sales, df_stock


def clean_stock(df_stock: pd.DataFrame) -> pd.DataFrame:
    """Очищает остатки: удаляет дубликаты, суммирует партии и зануляет минусы."""
    keys = ["date", "warehouse_name", "article"]
    
    # Удаление полных дубликатов
    df_stock_clean = df_stock.drop_duplicates(
        subset=["date", "warehouse_name", "article", "stock"]
    ).copy()
    
    # Агрегация остатков
    df_stock_clean = df_stock_clean.groupby(
        keys, as_index=False
    ).agg(
        stock=("stock", "sum")
    )
    
    # Зануляем отрицательные остатки
    df_stock_clean['stock'] = df_stock_clean['stock'].clip(lower=0)
    
    return df_stock_clean


def build_full_grid(df_sales: pd.DataFrame, df_stock_clean: pd.DataFrame) -> pd.DataFrame:
    """Создает полную сетку дат и заполняет остатки"""
    keys = ["date", "warehouse_name", "article"]
    
    # Границы дат
    min_date = min(df_stock_clean['date'].min(), df_sales['date'].min())
    max_date = max(df_stock_clean['date'].max(), df_sales['date'].max())
    all_dates = pd.date_range(min_date, max_date, freq='D')
    
    # Уникальные списки
    warehouses = df_sales['warehouse_name'].unique()
    articles = df_sales['article'].unique()
    
    # Полная сетка
    full_grid = pd.MultiIndex.from_product(
        [warehouses, articles, all_dates],
        names=['warehouse_name', 'article', 'date']
    ).to_frame(index=False)
    
    # Присоединение остатков
    df_stock_daily = full_grid.merge(df_stock_clean, on=keys, how='left')
    
    # Сортировка и ffill
    df_stock_daily = df_stock_daily.sort_values(['warehouse_name', 'article', 'date'])
    df_stock_daily['stock'] = (
        df_stock_daily.groupby(['warehouse_name', 'article'])['stock'].ffill()
    )
    
    return df_stock_daily


def clean_sales(df_sales: pd.DataFrame) -> pd.DataFrame:
    """Очищает продажи (суммирует департаменты) и сохраняет категории."""
    keys = ["date", "warehouse_name", "article"]
    cat_cols = ["cities_name", "category_lvl_1", "category_lvl_2", "category_lvl_3"]
    
    # Чистим пропуски в категориях
    for col in cat_cols:
        if col in df_sales.columns:
            df_sales[col] = df_sales[col].fillna("unknown")
    
    # Агрегируем департаменты
    df_sales_clean = (
        df_sales
        .groupby(keys, as_index=False)
        .agg(
            quantity=("quantity", "sum"),
            cities_name=("cities_name", "first"),
            category_lvl_1=("category_lvl_1", "first"),
            category_lvl_2=("category_lvl_2", "first"),
            category_lvl_3=("category_lvl_3", "first"),
        )
    )
    
    
    return df_sales_clean


def build_final_dataset(df_sales_clean: pd.DataFrame, df_stock_daily: pd.DataFrame) -> pd.DataFrame:
    """Финальный merge"""
    keys = ["date", "warehouse_name", "article"]
    cat_cols = ["cities_name", "category_lvl_1", "category_lvl_2", "category_lvl_3"]
    
    # Присоединяем продажи к сетке стоков
    df_final = df_stock_daily.merge(
        df_sales_clean,
        on=keys,
        how="left"
    )
    
    # Заполняем продажи нулями
    df_final["quantity"] = df_final["quantity"].fillna(0)
    
    # Заполняем категории "unknown" 
    for col in cat_cols:
        df_final[col] = df_final[col].fillna("unknown")
        
    return df_final


def prepare_data_for_api(sales_path: str, stock_path: str) -> pd.DataFrame:
    """
    Главная функция для API (Docker-контейнера).
    Принимает пути к CSV, возвращает готовый DataFrame.
    """
    df_sales_raw, df_stock_raw = load_raw_data(sales_path, stock_path)
    df_stock_clean = clean_stock(df_stock_raw)
    df_stock_daily = build_full_grid(df_sales_raw, df_stock_clean)
    df_sales_clean = clean_sales(df_sales_raw)
    df_final = build_final_dataset(df_sales_clean, df_stock_daily)
    
    return df_final