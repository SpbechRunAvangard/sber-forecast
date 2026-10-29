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
    
    
    return df_stock_clean


def build_full_grid(df_sales: pd.DataFrame, df_stock_clean: pd.DataFrame) -> pd.DataFrame:
    """Создает полную сетку дат и заполняет остатки (ffill)."""
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
    
    # Сортировка
    df_stock_daily = df_stock_daily.sort_values(['warehouse_name', 'article', 'date'])
    
    # Флаг отсутствия данных 
    df_stock_daily['stock_was_nan'] = df_stock_daily['stock'].isna().astype(int)
    
    # Заполнение остатков вперед 
    df_stock_daily['stock'] = (
        df_stock_daily.groupby(['warehouse_name', 'article'])['stock'].ffill()
    )
    
    return df_stock_daily


def clean_sales(df_sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Очищает продажи, создает справочник категорий и возвращает два DataFrame."""
    keys = ["date", "warehouse_name", "article"]
    cat_cols = ["cities_name", "category_lvl_1", "category_lvl_2"]
    
    # Заменяем null в скидках на 0
    df_sales["discount_sum"] = df_sales["discount_sum"].fillna(0)
    
    # Строим чистый справочник "артикул -> категория"
    df_items_directory = df_sales[["article"] + cat_cols].dropna().drop_duplicates(subset=["article"])
    
    # Агрегируем департаменты 
    df_sales_clean = (
        df_sales
        .groupby(keys, as_index=False)
        .agg(
            quantity=("quantity", "sum")
        )
    )
    
    return df_sales_clean, df_items_directory


def build_final_dataset(df_sales_clean: pd.DataFrame, df_stock_daily: pd.DataFrame, df_items_directory: pd.DataFrame) -> pd.DataFrame:
    """Финальный merge"""
    keys = ["date", "warehouse_name", "article"]
    cat_cols = ["cities_name", "category_lvl_1", "category_lvl_2"]
    
    # Присоединяем продажи к сетке стоков
    df_final = df_stock_daily.merge(
        df_sales_clean,
        on=keys,
        how="left"
    )
    
    # Заполняем продажи нулями
    df_final["quantity"] = df_final["quantity"].fillna(0)
    
    # Присоединяем справочник категорий
    df_final = df_final.merge(df_items_directory, on="article", how="left")
    
    # Заполняем категории (и переводим в тип category, как в ноутбуке)
    for col in cat_cols:
        df_final[col] = df_final[col].fillna("unknown").astype("category")
        
    return df_final


def prepare_data_for_api(sales_path: str, stock_path: str) -> pd.DataFrame:
    
    df_sales_raw, df_stock_raw = load_raw_data(sales_path, stock_path)
    df_stock_clean = clean_stock(df_stock_raw)
    df_stock_daily = build_full_grid(df_sales_raw, df_stock_clean)
    df_sales_clean, df_items_directory = clean_sales(df_sales_raw)
    df_final = build_final_dataset(df_sales_clean, df_stock_daily, df_items_directory)
    
    return df_final