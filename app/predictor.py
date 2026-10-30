from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src import predictor_core, raw_to_arrays


class NotReadyError(RuntimeError):
    """Прогноз ещё не рассчитан (не было POST /predict)."""


class Predictor:
    """Обёртка над моделью для инференса."""

    def __init__(self, art):
        self.art = art
        self._cached_forecast: Optional[pd.DataFrame] = None

    @classmethod
    def load(cls, model_dir: Path) -> "Predictor":
        return cls(predictor_core.load_artifacts(model_dir))

    def predict(self, df_sales: pd.DataFrame, df_stock: pd.DataFrame) -> pd.DataFrame:
        """Принимает сырые sales и stock, возвращает прогноз на 9 недель в формате submission."""
        cfg = self.art["cfg"]
        pairs, weeks = cfg["pairs"], cfg["weeks"]
        Qw, STw, last_date = raw_to_arrays.build_arrays(df_sales, df_stock, pairs, cfg["window"])
        warehouses = [p[0] for p in pairs]
        articles = [p[1] for p in pairs]
        P = predictor_core.predict_from_arrays(Qw, STw, warehouses, articles, self.art)

        # прогноз начинается с понедельника календарной недели, следующей за неделей последней даты sales
        this_week_monday = last_date - pd.Timedelta(days=last_date.weekday())
        week_dates = pd.date_range(this_week_monday + pd.Timedelta(days=7), periods=weeks, freq="7D")
        df_forecast = pd.DataFrame({
            "week": np.tile(week_dates.strftime("%Y-%m-%d"), len(pairs)),
            "warehouse_name": np.repeat(warehouses, weeks),
            "article": np.repeat(articles, weeks),
            "quantity": np.round(P.reshape(-1), 4),
        })
        self._cached_forecast = df_forecast
        return df_forecast

    def get_cached_forecast(self) -> pd.DataFrame:
        if self._cached_forecast is None:
            raise NotReadyError("Прогноз не рассчитан. Сначала вызовите POST /predict.")
        return self._cached_forecast
