# -*- coding: utf-8 -*-
"""
core_econometrics.py
经济学面板数据计量内核：负责面板设定、模型估计、多维聚类标准误与 Hausman 检验
"""

import numpy as np
import pandas as pd
from scipy import stats
from linearmodels.panel import (
    PooledOLS,
    PanelOLS,
    RandomEffects,
    BetweenOLS,
)
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ModelResultWrapper:
    """统一封装单个面板回归模型的结果，用于多模型并排对比"""
    model_title: str               # 模型列标题，如 "(1) 混合OLS"
    model_type: str                # 模型类别标识
    dep_var: str                   # 被解释变量名称
    exog_vars: List[str]           # 解释变量名称列表（不含常数项）
    params: pd.Series              # 回归系数
    std_errors: pd.Series          # 标准误
    tstats: pd.Series              # t / z 统计量
    pvalues: pd.Series             # p 值
    nobs: int                      # 观测值数量 N
    n_entities: int                # 个体数量
    n_periods: int                 # 时间期数
    r2_within: float               # 组内 R2
    r2_between: float              # 组间 R2
    r2_overall: float              # 总体 R2
    r2_model: float
    f_stat: Optional[float]        # F 统计量
    f_pval: Optional[float]        # F 检验 p 值
    entity_fe: bool                # 是否控制个体固定效应
    time_fe: bool                  # 是否控制时间固定效应
    se_type_label: str             # 标准误类型描述
    fitted_values: pd.Series       # 拟合值（用于绘图）
    residuals: pd.Series           # 残差（用于绘图）
    conf_int_low: pd.Series        # 95% 置信区间下限
    conf_int_high: pd.Series       # 95% 置信区间上限
    sample_index: pd.MultiIndex


class PanelEconometricsEngine:
    """面板数据计量引擎"""

    MODEL_TYPES = [
        "双向固定效应 (Two-Way FE)",
        "个体固定效应 (Entity FE)",
        "时间固定效应 (Time FE)",
        "混合最小二乘 (Pooled OLS)",
        "随机效应模型 (Random Effects)",
        "组间估计量 (Between Estimator)",
        "一阶差分模型 (First Difference)"
    ]

    SE_TYPES = [
        "个体聚类稳健标准误 (Cluster by Entity)",
        "双向聚类稳健标准误 (Two-Way Cluster)",
        "异方差稳健标准误 (White Robust)",
        "普通标准误 (Homoscedastic)"
    ]

    @staticmethod
    def generate_demo_panel_data(n_firms: int = 120, n_years: int = 10, seed: int = 42) -> pd.DataFrame:
        """
        生成经典的“企业数字化转型与全要素生产率(TFP)”仿真平衡面板数据
        包含明确的个体效应与时间效应，便于验证固定效应模型与 Hausman 检验
        """
        rng = np.random.default_rng(seed)
        firms = [f"Firm_{i:03d}" for i in range(1, n_firms + 1)]
        years = list(range(2015, 2015 + n_years))

        records = []
        # 个体不可观测异质性 alpha_i
        firm_alpha = rng.normal(0, 1.2, size=n_firms)
        # 时间宏观趋势冲击 lambda_t
        year_lambda = np.linspace(0, 0.8, n_years) + rng.normal(0, 0.1, size=n_years)

        for i, firm in enumerate(firms):
            alpha_i = firm_alpha[i]
            base_size = rng.normal(22.0, 1.2)
            for t, year in enumerate(years):
                lam_t = year_lambda[t]
                # 解释变量与 alpha_i 相关（内生性，使随机效应有偏而固定效应一致）
                digital_index = 0.5 * alpha_i + 0.15 * t + rng.normal(2.5, 0.8)
                rd_intensity = 0.2 * alpha_i + rng.uniform(0.01, 0.12)
                firm_size = base_size + 0.08 * t + rng.normal(0, 0.25)
                lev = np.clip(rng.normal(0.45, 0.15) - 0.02 * alpha_i, 0.05, 0.95)
                roa = np.clip(0.06 + 0.02 * alpha_i + rng.normal(0, 0.03), -0.20, 0.35)
                firm_age = (t + 5) + (i % 15)

                # 真实数据生成过程 (DGP):
                # tfp = 1.5 + 0.35*digital + 1.80*rd + 0.18*size - 0.45*lev + 0.80*roa + alpha_i + lam_t + eps
                eps = rng.normal(0, 0.35)
                tfp = (
                    1.50
                    + 0.35 * digital_index
                    + 1.80 * rd_intensity
                    + 0.18 * firm_size
                    - 0.45 * lev
                    + 0.80 * roa
                    + alpha_i
                    + lam_t
                    + eps
                )

                records.append({
                    "firm_id": firm,
                    "year": int(year),
                    "tfp": round(tfp, 4),
                    "digital_index": round(digital_index, 4),
                    "rd_intensity": round(rd_intensity, 4),
                    "firm_size": round(firm_size, 4),
                    "lev": round(lev, 4),
                    "roa": round(roa, 4),
                    "firm_age": int(firm_age)
                })

        return pd.DataFrame(records)

    @staticmethod
    def validate_and_set_panel(df, entity_col, time_col):
        """校验面板键，保留日期精度，报告清洗数量。"""
        if entity_col == time_col:
            raise ValueError("个体列与时间列必须不同。")
        work = df.dropna(subset=[entity_col, time_col]).copy()
        if pd.api.types.is_string_dtype(work[entity_col]):
            work = work.loc[work[entity_col].str.strip().ne("")].copy()
        if pd.api.types.is_string_dtype(work[time_col]):
            work = work.loc[work[time_col].str.strip().ne("")].copy()
        if work.empty:
            raise ValueError("没有同时具备个体和时间的记录。")

        time = work[time_col]
        if not pd.api.types.is_datetime64_any_dtype(time):
            try:
                time = pd.to_numeric(time)
            except (ValueError, TypeError):
                try:
                    time = pd.to_datetime(time, format="mixed")
                except (ValueError, TypeError) as error:
                    raise ValueError("时间列需要使用数值或可识别的日期。") from error
        if getattr(time.dtype, "tz", None) is not None:
            time = time.dt.tz_localize(None)
        if pd.api.types.is_numeric_dtype(time):
            time = time.where(np.isfinite(time))
        work[time_col] = time
        work = work.dropna(subset=[time_col])
        missing = len(df) - len(work)
        work = work.drop_duplicates(subset=[entity_col, time_col], keep="first")
        duplicates = len(df) - missing - len(work)
        if work.empty:
            raise ValueError("清洗后没有可用的面板观测。")

        panel = work.set_index([entity_col, time_col]).sort_index()
        entities, periods = (panel.index.get_level_values(i) for i in (0, 1))
        balanced = len(panel) == entities.nunique() * periods.nunique()
        time_text = " 至 ".join(
            value.isoformat(sep=" ", timespec="minutes") if isinstance(value, pd.Timestamp)
            and value != value.normalize() else str(value.date() if isinstance(value, pd.Timestamp) else value)
            for value in (periods.min(), periods.max())
        )
        balance = "强平衡" if balanced else "非平衡"
        status = f"{balance} · {entities.nunique()} 个体 · {periods.nunique()} 期 · {len(panel):,} 条\n{time_text}"
        if missing or duplicates:
            status += f"\n移除键缺失 {missing} 条，重复键 {duplicates} 条（保留首条）"
        return panel, {"status_text": status, "is_balanced": balanced,
                       "dup_dropped": duplicates, "missing_dropped": missing}

    @staticmethod
    def compute_descriptive_stats(df, cols):
        rows = []
        for col in dict.fromkeys(cols):
            if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                continue
            series = df[col].astype(float)
            series = series[np.isfinite(series)]
            rows.append({
                "变量": col, "观测值": len(series), "均值": series.mean(),
                "标准差": series.std(), "最小值": series.min(),
                "中位数": series.median(), "最大值": series.max()
            })
        return pd.DataFrame(rows)

    @staticmethod
    def regression_sample(panel_df, dep_var, exog_vars):
        if dep_var in exog_vars or len(set(exog_vars)) != len(exog_vars):
            raise ValueError("Y 与 X 需要使用不同变量，每个 X 只选一次。")
        if not dep_var or not exog_vars:
            raise ValueError("请选择一个 Y 和至少一个 X。")
        sample = panel_df[[dep_var, *exog_vars]].astype(float)
        if sample.empty:
            raise ValueError("面板没有可用观测。")
        return sample.where(np.isfinite(sample))

    @staticmethod
    def _add_intercept(x):
        name = "常数项"
        while name in x.columns:
            name += "_"
        return x.assign(**{name: 1.0})

    @classmethod
    def fit_panel_model(cls, panel_df, dep_var, exog_vars, model_type, se_type, custom_title=None):
        kind = cls.MODEL_TYPES.index(model_type)
        vce = cls.SE_TYPES.index(se_type)
        sample = cls.regression_sample(panel_df, dep_var, exog_vars)
        if kind == 6:
            # 缺失值先保留，防止差分跨过中间缺值。时间编号保留整个面板的期次。
            period_codes = sample.index.get_level_values(1).factorize(sort=True)[0]
            adjacent = pd.Series(period_codes, index=sample.index).groupby(level=0).diff().eq(1)
            sample = sample.groupby(level=0).diff().loc[adjacent]
        sample = sample.dropna()
        if len(sample) <= len(exog_vars) + (kind != 6):
            raise ValueError("有效观测太少，请检查缺失值、期数和解释变量数量。")
        y, x = sample[dep_var], sample[exog_vars]
        if y.nunique() <= 1:
            raise ValueError("有效样本的 Y 没有变化，无法回归。")
        if kind != 6:
            x = cls._add_intercept(x)

        entity_fe = kind in (0, 1)
        time_fe = kind in (0, 2)
        if entity_fe or time_fe:
            model = PanelOLS(y, x, entity_effects=entity_fe, time_effects=time_fe, drop_absorbed=True)
        else:
            model = {3: PooledOLS, 4: RandomEffects, 5: BetweenOLS, 6: PooledOLS}[kind](y, x)

        entities = sample.index.get_level_values(0)
        periods = sample.index.get_level_values(1)
        if kind == 5 and vce == 1:
            raise ValueError("组间估计按个体取均值，每个个体只有一条记录。请选择个体聚类、异方差稳健或普通标准误。")
        if vce in (0, 1) and (entities.nunique() < 2 or (vce == 1 and periods.nunique() < 2)):
            raise ValueError("聚类维度至少需要两组。")
        if vce in (0, 1):
            clusters = pd.DataFrame({"entity": entities.factorize()[0]}, index=sample.index)
            if vce == 1:
                clusters["period"] = periods.factorize()[0]
            result = model.fit(cov_type="clustered", clusters=clusters, group_debias=True)
        else:
            result = model.fit(cov_type="robust" if vce == 2 else "unadjusted")

        if not any(name in result.params for name in exog_vars):
            raise ValueError("所选解释变量全部被固定效应吸收，无法报告系数。")
        if result.df_resid <= 0:
            raise ValueError("模型没有剩余自由度，请减少解释变量或增加观测。")
        residuals = result.resids
        observed = y.groupby(level=0).mean() if kind == 5 else y
        fitted = observed.reindex(residuals.index) - residuals
        ci = result.conf_int()
        test = result.f_statistic_robust
        return ModelResultWrapper(
            model_title=custom_title or model_type.split(" (")[0],
            model_type=model_type, dep_var=dep_var, exog_vars=exog_vars,
            params=result.params, std_errors=result.std_errors, tstats=result.tstats,
            pvalues=result.pvalues, nobs=int(result.nobs),
            n_entities=entities.nunique(), n_periods=periods.nunique(),
            r2_within=result.rsquared_within if kind not in (5, 6) else np.nan,
            r2_between=result.rsquared_between if kind != 6 else np.nan,
            r2_overall=result.rsquared_overall if kind != 6 else np.nan,
            r2_model=result.rsquared,
            f_stat=test.stat, f_pval=test.pval,
            entity_fe=entity_fe, time_fe=time_fe,
            se_type_label=se_type.split(" (")[0], fitted_values=fitted,
            residuals=residuals, conf_int_low=ci["lower"], conf_int_high=ci["upper"],
            sample_index=sample.index
        )

    @classmethod
    def run_hausman_test(cls, panel_df, dep_var, exog_vars):
        sample = cls.regression_sample(panel_df, dep_var, exog_vars).dropna()
        y, x = sample[dep_var], cls._add_intercept(sample[exog_vars])
        fe = PanelOLS(y, x, entity_effects=True, drop_absorbed=True).fit(cov_type="unadjusted")
        re = RandomEffects(y, x).fit(cov_type="unadjusted")
        common = [name for name in exog_vars if name in fe.params and name in re.params]
        if not common or fe.s2 <= 0 or re.s2 <= 0:
            raise ValueError("没有可比较的系数或有效残差方差。")
        difference = (fe.params - re.params).loc[common].to_numpy()
        # 使用 RE 的误差方差作为两套协方差的共同尺度。
        covariance = (fe.cov.loc[common, common] * (re.s2 / fe.s2) - re.cov.loc[common, common]).to_numpy()
        covariance = (covariance + covariance.T) / 2
        eigenvalues = np.linalg.eigvalsh(covariance)
        threshold = np.max(np.abs(eigenvalues)) * 1e-9
        if np.any(eigenvalues <= threshold):
            raise ValueError("协方差差矩阵不满足正定条件，经典 Hausman 检验无法给出可靠结论。")
        statistic = float(difference @ np.linalg.solve(covariance, difference))
        p_value = float(stats.chi2.sf(statistic, len(common)))
        recommendation = (
            "在 5% 水平拒绝随机效应假设，优先考虑个体固定效应。"
            if p_value < 0.05 else "在 5% 水平未拒绝随机效应假设，请结合研究设定选择模型。"
        )
        return {"chi2": statistic, "df": len(common), "pval": p_value,
                "recommendation": recommendation}
