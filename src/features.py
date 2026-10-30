"""Признаки итоговой модели v6. Единый код для обучения (src/train.py) и контейнера (app/predictor.py).

Все признаки на дату отсечки c используют только дни 0..c включительно.
  base   — 22 исходных признака ряда + недельные, прошлогодние (продажи тех же 9 недель год назад) и категориальные;
  extra  — артикул по всем складам, склад, относительная цена и доля скидки, возраст ряда и артикула;
  extra2 — короткий спрос артикула, остатки артикула и склада, динамика остатков, категория×склад, цена ряда.
Прошлогодние признаки требуют не меньше 454 дней истории; при более короткой истории они равны NaN.
"""
import warnings

import numpy as np
import pandas as pd

from .config import CAT_COLS, EXT_SETS, H, W

# пустые окна (нет остатков, нет продаж) дают NaN — это ожидаемо, предупреждения numpy не нужны
warnings.filterwarnings('ignore', category=RuntimeWarning)


class Features:
    def __init__(self, Q, ST, SV, DV, meta, d0):
        self.Q, self.ST, self.SV, self.DV, self.d0 = Q, ST, SV, DV, d0
        self.S = Q.shape[0]
        self.wh = pd.Categorical(meta.warehouse_name).codes
        self.cat = pd.Categorical(meta.category_lvl_1).codes
        self.cat2 = pd.Categorical(meta.category_lvl_2).codes
        self.ncat = self.cat.max() + 1
        self.art = pd.Categorical(meta.article).codes.astype(np.int64); self.NA = int(self.art.max()) + 1
        self.wh64 = self.wh.astype(np.int64); self.NW = int(self.wh64.max()) + 1
        self.cat64 = self.cat.astype(np.int64); self.NC = int(self.cat64.max()) + 1
        pos_any = Q > 0
        self.first = np.where(pos_any.any(1), np.argmax(pos_any, 1), 10**6)
        self.art_first = np.full(self.NA, 10**6); np.minimum.at(self.art_first, self.art, self.first)
        self.cnt_art = np.bincount(self.art, minlength=self.NA).astype(float)

    # --- признаки ряда (как в v2/v3) ---
    def base(self, c):
        Q, ST, S, cat, cat2 = self.Q, self.ST, self.S, self.cat, self.cat2
        f = {}
        for w in (7, 14, 28, 56, 90, 180): f[f'mean_{w}'] = Q[:, c-w+1:c+1].mean(1)
        for w in (28, 90, 180): f[f'share_pos_{w}'] = (Q[:, c-w+1:c+1] > 0).mean(1)
        for w in (90, 180): f[f'max_{w}'] = Q[:, c-w+1:c+1].max(1)
        pos = Q[:, c-179:c+1] > 0
        f['days_since_sale'] = np.where(pos.any(1), 179 - np.argmax(pos[:, ::-1], 1), 180)
        s = ST[:, c-179:c+1]
        f['stock_last'] = s[:, -1]; f['stock_missing_last'] = np.isnan(s[:, -1]).astype(np.float32)
        for w in (7, 30, 90):
            sw = s[:, -w:]
            f[f'oos_share_{w}'] = np.nanmean(np.where(np.isnan(sw), np.nan, (sw <= 0).astype(np.float32)), 1)
        f['stock_missing_90'] = np.isnan(s[:, -90:]).mean(1); f['stock_mean_90'] = np.nanmean(s[:, -90:], 1)
        q90, ins = Q[:, c-89:c+1], ST[:, c-89:c+1] > 0; cnt = ins.sum(1)
        f['mean_in_stock_90'] = np.where(cnt > 0, (q90 * ins).sum(1) / np.maximum(cnt, 1), np.nan)
        f['cover_days'] = s[:, -1] / (f['mean_28'] + 0.05)
        w26 = Q[:, c-181:c+1].reshape(S, 26, 7).sum(2); w13 = w26[:, -13:]
        f['wk_pos_13'] = (w13 > 0).mean(1); f['wk_pos_26'] = (w26 > 0).mean(1)
        nz = np.where(w26 > 0, w26, np.nan)
        f['wk_nz_mean_26'] = np.nanmean(nz, 1); f['wk_nz_med_26'] = np.nanmedian(nz, 1)
        f['wk_nz_med_13'] = np.nanmedian(np.where(w13 > 0, w13, np.nan), 1)
        f['wk_last'] = w26[:, -1]; f['wk_last4_mean'] = w26[:, -4:].mean(1)
        a, b = c - 364 + 1, c - 364 + H + 1
        if a - 90 >= 0:
            ly, lyp = Q[:, a:b].mean(1), Q[:, a-90:a].mean(1)
            f['ly_same'] = ly; f['ly_prev'] = lyp; f['ly_ratio'] = (ly + 0.01) / (lyp + 0.01)
            f['ly_pos_share'] = (Q[:, a:b].reshape(S, W, 7).sum(2) > 0).mean(1)
            f['cat_ly_ratio'] = ((np.bincount(cat, ly, self.ncat) + 0.1) / (np.bincount(cat, lyp, self.ncat) + 0.1))[cat]
            f['cat2_ly_ratio'] = ((np.bincount(cat2, ly) + 0.1) / (np.bincount(cat2, lyp) + 0.1))[cat2]
            f['tot_ly_ratio'] = np.full(S, Q[:, a:b].sum() / (Q[:, a-90:a].sum() * H / 90 + 1e-6))
        else:
            for k in ('ly_same', 'ly_prev', 'ly_ratio', 'ly_pos_share', 'cat_ly_ratio', 'cat2_ly_ratio', 'tot_ly_ratio'):
                f[k] = np.full(S, np.nan)
        c28, c90 = np.bincount(cat, f['mean_28'], self.ncat), np.bincount(cat, f['mean_90'], self.ncat)
        f['cat_trend'] = ((c28 + 0.01) / (c90 + 0.01))[cat]
        doy = (self.d0 + pd.Timedelta(days=c + 1)).dayofyear
        f['doy_sin'] = np.full(S, np.sin(2 * np.pi * doy / 365.25)); f['doy_cos'] = np.full(S, np.cos(2 * np.pi * doy / 365.25))
        f['age'] = np.full(S, min(c, 179)); f['warehouse'] = self.wh; f['category'] = cat; f['cat2'] = cat2
        X = pd.DataFrame(f).astype(np.float32)
        for col in CAT_COLS:
            X[col] = X[col].astype(int).astype('category')
        return X

    # --- E: артикул по всем складам, склад, цена/скидка (относительные), возраст ряда и артикула ---
    def extra(self, c):
        Q, SV, DV, S, art, NA = self.Q, self.SV, self.DV, self.S, self.art, self.NA
        wh, NW, bc = self.wh64, self.NW, np.bincount
        f = {}
        m = {w: Q[:, c-w+1:c+1].mean(1) for w in (28, 90, 180)}
        A = {w: bc(art, m[w], NA)[art] for w in m}
        f['art_mean_28'], f['art_mean_90'], f['art_mean_180'] = A[28], A[90], A[180]
        f['art_trend'] = (A[28] + 0.01) / (A[90] + 0.01); f['art_trend_long'] = (A[90] + 0.01) / (A[180] + 0.01)
        f['art_nwh_28'] = bc(art, (Q[:, c-27:c+1].sum(1) > 0).astype(float), NA)[art]
        f['art_nwh_90'] = bc(art, (Q[:, c-89:c+1].sum(1) > 0).astype(float), NA)[art]
        f['share_art_90'] = m[90] / (A[90] + 1e-6)
        w13 = (Q[:, c-90:c+1].reshape(S, 13, 7).sum(2) > 0).mean(1)
        f['art_wkpos_13'] = (bc(art, w13, NA) / self.cnt_art)[art]
        W28, W90 = bc(wh, m[28], NW)[wh], bc(wh, m[90], NW)[wh]
        f['wh_trend'] = (W28 + 0.01) / (W90 + 0.01)
        a, b = c - 364 + 1, c - 364 + H + 1
        if a - 90 >= 0:
            ly, lyp = Q[:, a:b].mean(1), Q[:, a-90:a].mean(1)
            f['art_ly_ratio'] = ((bc(art, ly, NA) + 0.05) / (bc(art, lyp, NA) + 0.05))[art]
            f['wh_ly_ratio'] = ((bc(wh, ly, NW) + 0.05) / (bc(wh, lyp, NW) + 0.05))[wh]
        else:
            f['art_ly_ratio'] = np.full(S, np.nan); f['wh_ly_ratio'] = np.full(S, np.nan)
        first, art_first = self.first, self.art_first
        f['series_age'] = np.where(first <= c, np.minimum(c - first, 400), -1).astype(float)
        f['art_age'] = np.where(art_first[art] <= c, np.minimum(c - art_first[art], 400), -1).astype(float)
        with np.errstate(all='ignore'):
            sv28, q28 = bc(art, SV[:, c-27:c+1].sum(1), NA), bc(art, Q[:, c-27:c+1].sum(1), NA)
            sv180, q180 = bc(art, SV[:, c-179:c+1].sum(1), NA), bc(art, Q[:, c-179:c+1].sum(1), NA)
            p28 = np.where(q28 > 0, sv28 / q28, np.nan); p180 = np.where(q180 > 0, sv180 / q180, np.nan)
            f['art_price_rel'] = (p28 / p180)[art]
            dv28, dv180 = bc(art, DV[:, c-27:c+1].sum(1), NA), bc(art, DV[:, c-179:c+1].sum(1), NA)
            d28 = np.where(sv28 > 0, dv28 / sv28, np.nan); d180 = np.where(sv180 > 0, dv180 / sv180, np.nan)
            f['art_disc_28'], f['art_disc_180'], f['art_disc_change'] = d28[art], d180[art], (d28 - d180)[art]
            sq90 = Q[:, c-89:c+1].sum(1); sp90 = np.where(sq90 > 0, SV[:, c-89:c+1].sum(1) / sq90, np.nan)
            ap90 = np.where(bc(art, sq90, NA) > 0, bc(art, SV[:, c-89:c+1].sum(1), NA) / bc(art, sq90, NA), np.nan)
            f['wh_price_rel'] = sp90 / ap90[art]
        return pd.DataFrame(f).astype(np.float32)

    # --- E2: короткий спрос артикула, остатки артикула/склада, динамика остатков, категория×склад, цена ряда ---
    def extra2(self, c):
        Q, ST, SV, DV, S, art, NA = self.Q, self.ST, self.SV, self.DV, self.S, self.art, self.NA
        wh, NW, cat, NC, bc = self.wh64, self.NW, self.cat64, self.NC, np.bincount
        def nanshare(num_mask, valid_mask, keys, n):
            return (bc(keys, num_mask.astype(float), n) / np.maximum(bc(keys, valid_mask.astype(float), n), 1))[keys]
        f = {}
        with np.errstate(all='ignore'):
            m = {w: Q[:, c-w+1:c+1].mean(1) for w in (7, 14, 28, 90)}
            A = {w: bc(art, m[w], NA)[art] for w in m}
            f['art_mean_7'], f['art_mean_14'] = A[7], A[14]
            f['art_trend_7_28'] = (A[7] + 0.01) / (A[28] + 0.01)
            s_last = ST[:, c]; has = ~np.isnan(s_last)
            f['art_stock_last'] = bc(art, np.where(has, s_last, 0), NA)[art]
            f['art_stock_pos_share'] = nanshare(s_last > 0, has, art, NA)
            s30 = ST[:, c-29:c+1]
            oos30 = np.nanmean(np.where(np.isnan(s30), np.nan, (s30 <= 0).astype(np.float32)), 1)
            ok30 = ~np.isnan(oos30)
            f['art_oos_30'] = (bc(art, np.nan_to_num(oos30), NA) / np.maximum(bc(art, ok30.astype(float), NA), 1))[art]
            f['art_cover'] = f['art_stock_last'] / (A[28] + 0.05)
            f['stock_chg_7'] = s_last - ST[:, c-7]
            f['stock_max_30'] = np.nanmax(s30, 1)
            s90 = ST[:, c-89:c+1]; oos = s90 <= 0
            f['days_since_oos'] = np.where(oos.any(1), 89 - np.argmax(oos[:, ::-1], 1), 90).astype(float)
            inc = np.diff(s90, axis=1) > 0
            f['days_since_restock'] = np.where(inc.any(1), 88 - np.argmax(inc[:, ::-1], 1), 89).astype(float)
            q28 = Q[:, c-27:c+1]; ins28 = ST[:, c-27:c+1] > 0; cnt = ins28.sum(1)
            f['mean_in_stock_28'] = np.where(cnt > 0, (q28 * ins28).sum(1) / np.maximum(cnt, 1), np.nan)
            f['wh_mean_28'] = bc(wh, m[28], NW)[wh]
            f['wh_oos_30'] = (bc(wh, np.nan_to_num(oos30), NW) / np.maximum(bc(wh, ok30.astype(float), NW), 1))[wh]
            cw = cat * NW + wh; NCW = NC * NW
            f['catwh_trend'] = ((bc(cw, m[28], NCW) + 0.01) / (bc(cw, m[90], NCW) + 0.01))[cw]
            sv28 = SV[:, c-27:c+1].sum(1); q28s = q28.sum(1)
            sv180 = SV[:, c-179:c+1].sum(1); q180 = Q[:, c-179:c+1].sum(1)
            p28 = np.where(q28s > 0, sv28 / q28s, np.nan); p180 = np.where(q180 > 0, sv180 / q180, np.nan)
            f['ser_price_rel'] = p28 / p180
            f['ser_disc_28'] = np.where(sv28 > 0, DV[:, c-27:c+1].sum(1) / sv28, np.nan)
            w26 = Q[:, c-181:c+1].reshape(S, 26, 7).sum(2); pos = w26 > 0
            f['zero_wk_streak'] = np.where(pos.any(1), np.argmax(pos[:, ::-1], 1), 26).astype(float)
            w13 = w26[:, -13:]; mu = w13.mean(1)
            f['wk_cv_13'] = np.where(mu > 0, w13.std(1) / mu, np.nan)
        return pd.DataFrame(f).astype(np.float32)

    def __call__(self, c):
        parts = [self.base(c)]
        if 'E' in EXT_SETS: parts.append(self.extra(c))
        if 'E2' in EXT_SETS: parts.append(self.extra2(c))
        return pd.concat(parts, axis=1)
