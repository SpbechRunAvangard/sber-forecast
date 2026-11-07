"""Обучение и применение итоговой модели v6.

Уровень: среднее двух LightGBM Tweedie («базовая» на 22 признаках, «расширенная» на всех) × сезон^0.5 × 0.9,
округление до целых. Решение «0 или уровень»: третья модель (регрессия) оценивает выигрыш SMAPE от ненулевого
прогноза; ряд получает уровень (не меньше 1), если выигрыш > 0 и уровень ≥ 0.5 шт./нед., иначе 0.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb

from .config import BASE_FEATURES, CAT_COLS, GAIN_PARAMS, H, PARAMS, SCALE, SEASON_POWER, THRESHOLD, W
from .features import Features


def smape_series(Y, c):
    """SMAPE ряда (в %) за 9 недель при плоском прогнозе c; 0/0 = 0, как в score.py."""
    P = np.asarray(c, float)[:, None]; den = (Y + P) / 2
    out = np.zeros_like(den, dtype=float); np.divide(np.abs(Y - P), den, out=out, where=den > 0); return out.mean(1) * 100


def smape_gain(Yw):
    """Выигрыш SMAPE от ненулевого прогноза: SMAPE(0) − SMAPE(max(round(среднее 9 недель), 1))."""
    Y = Yw.astype(float)
    return smape_series(Y, np.zeros(len(Y))) - smape_series(Y, np.maximum(np.round(Y.mean(1)), 1))


def train(Q, ST, SV, DV, meta, d0):
    """Обучающая выборка — даты отсечки с шагом 7 дней, цель целиком в известном прошлом. Возвращает три бустера."""
    feats = Features(Q, ST, SV, DV, meta, d0)
    c = Q.shape[1] - 1
    Xs, ys, gs = [], [], []
    for cc in range(c - H, 179, -7):
        Xs.append(feats(cc)); Yw = Q[:, cc+1:cc+1+H].reshape(feats.S, W, 7).sum(2)
        ys.append(Yw.mean(1)); gs.append(smape_gain(Yw))
    X = pd.concat(Xs, ignore_index=True); y = np.concatenate(ys); gain = np.concatenate(gs)
    for col in CAT_COLS:
        X[col] = X[col].astype('category')
    ext = list(feats(c).columns)
    m_base = lgb.LGBMRegressor(**PARAMS).fit(X[BASE_FEATURES], y)
    m_ext = lgb.LGBMRegressor(**PARAMS).fit(X[ext], y)
    m_gain = lgb.LGBMRegressor(**GAIN_PARAMS).fit(X[ext], gain)
    return {'base': m_base.booster_, 'ext': m_ext.booster_, 'gain': m_gain.booster_}, ext


def predict(boosters, Q, ST, SV, DV, meta, d0):
    """Плоский недельный прогноз на 9 недель для каждого ряда (по последнему дню матриц)."""
    feats = Features(Q, ST, SV, DV, meta, d0)
    c = Q.shape[1] - 1
    Xt = feats(c); ext = list(Xt.columns)
    r_base = boosters['base'].predict(Xt[BASE_FEATURES])
    r_ext = boosters['ext'].predict(Xt[ext])
    adv = boosters['gain'].predict(Xt[ext])
    weekly = 0.5 * (np.clip(r_base, 0, None) + np.clip(r_ext, 0, None))
    tot = Xt.tot_ly_ratio.iloc[0]
    season = float(np.clip(tot, 0.6, 1.8)) if np.isfinite(tot) else 1.0     # меньше 454 дней истории — без поправки
    weekly = weekly * season ** SEASON_POWER * SCALE
    keep = (weekly >= THRESHOLD) & (adv > 0)
    weekly = np.where(keep, np.maximum(np.round(weekly), 1.0), 0.0)
    return weekly, dict(r_base=r_base, r_ext=r_ext, adv=adv, season=season)
