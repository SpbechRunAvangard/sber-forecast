"""Проверка: прогноз контейнера по полным данным до 2026-07-26 совпадает с основным submission один в один.

Запуск из корня репозитория (сырые CSV организаторов положить в data/raw/):
    python tests/test_parity.py data/raw/sales_dataset_hakaton_train.csv data/raw/stock_dataset_hakaton_train.csv
Тот же результат даёт POST /predict с этими файлами, обрезанными по 2026-07-26 включительно.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import predictor_core  # noqa: E402

CUTOFF = '2026-07-26'


def main(sales_path, stock_path, reference='data/submission_weekly_v6.csv'):
    sales = pd.read_csv(sales_path); stock = pd.read_csv(stock_path)
    sales, stock = sales[sales['date'] <= CUTOFF], stock[stock['date'] <= CUTOFF]
    art = predictor_core.load_artifacts('model')
    forecast, info = predictor_core.forecast(sales, stock, art)
    ref = pd.read_csv(reference)
    same = forecast.reset_index(drop=True).equals(ref.reset_index(drop=True))
    print(f'строк: {len(forecast)}; сезонный коэффициент прошлого года: {info["season"]:.3f}; совпадает с {reference}: {same}')
    if not same:
        diff = (forecast['quantity'] != ref['quantity']).sum()
        print(f'отличается строк: {diff}')
        sys.exit(1)


if __name__ == '__main__':
    main(*sys.argv[1:3])
