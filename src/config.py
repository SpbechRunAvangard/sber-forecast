"""Константы итоговой модели v6 (одни и те же для обучения и контейнера)."""
SEED = 42
H, W = 63, 9                     # горизонт: 63 дня = 9 недель
MIN_HISTORY_DAYS = 180           # минимум по ТЗ для API
FULL_HISTORY_DAYS = 454          # с этой глубины доступны прошлогодние признаки и сезонная поправка
SEASON_POWER, SCALE, THRESHOLD = 0.5, 0.9, 0.5
EXT_SETS = ('E', 'E2')           # наборы доп. признаков расширенной модели
CAT_COLS = ('warehouse', 'category', 'cat2')

PARAMS = dict(objective='tweedie', tweedie_variance_power=1.3, n_estimators=400, learning_rate=0.05, num_leaves=63,
              min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=SEED,
              deterministic=True, force_row_wise=True, n_jobs=2, verbose=-1)
GAIN_PARAMS = {**{k: v for k, v in PARAMS.items() if k != 'tweedie_variance_power'}, 'objective': 'regression'}

BASE_FEATURES = ['mean_7', 'mean_14', 'mean_28', 'mean_56', 'mean_90', 'mean_180', 'share_pos_28', 'share_pos_90',
                 'share_pos_180', 'max_90', 'max_180', 'days_since_sale', 'stock_last', 'stock_missing_last',
                 'oos_share_30', 'oos_share_90', 'stock_missing_90', 'stock_mean_90', 'mean_in_stock_90', 'age',
                 'warehouse', 'category']

MODEL_FILES = {'base': 'model_v6_base.txt', 'ext': 'model_v6_ext.txt', 'gain': 'model_v6_gain.txt'}
