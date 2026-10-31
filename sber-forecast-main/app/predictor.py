from pathlib import Path
from typing import Optional

import pandas as pd

from src import predictor_core


class NotReadyError(RuntimeError):
    """Прогноз ещё не рассчитан (не было POST /predict)."""


class Predictor:
    """Обёртка над итоговой моделью v6: три бустера LightGBM загружаются один раз при старте."""

    def __init__(self, art):
        self.art = art
        self._cached_forecast: Optional[pd.DataFrame] = None
        self.last_info: dict = {}

    @classmethod
    def load(cls, model_dir: Path) -> "Predictor":
        return cls(predictor_core.load_artifacts(model_dir))

    def predict(self, df_sales: pd.DataFrame, df_stock: pd.DataFrame) -> pd.DataFrame:
        """Принимает сырые sales и stock, возвращает прогноз на 9 недель в формате submission."""
        df_forecast, info = predictor_core.forecast(df_sales, df_stock, self.art)
        self._cached_forecast, self.last_info = df_forecast, info
        return df_forecast

    def get_cached_forecast(self) -> pd.DataFrame:
        if self._cached_forecast is None:
            raise NotReadyError("Прогноз не рассчитан. Сначала вызовите POST /predict.")
        return self._cached_forecast
