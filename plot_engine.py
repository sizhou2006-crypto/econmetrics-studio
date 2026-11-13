"""Four diagnostics for the selected regression."""

import numpy as np
import pandas as pd
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

matplotlib.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#adbbb6",
    "axes.labelcolor": "#425c53",
    "xtick.color": "#425c53",
    "ytick.color": "#425c53",
    "pdf.fonttype": 42,
})

BLUE = "#286f59"
TEAL = "#437f75"


class EconometricPlotCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=10, height=7, dpi=110):
        self.fig = Figure(figsize=(width, height), dpi=dpi, layout="constrained")
        super().__init__(self.fig)
        self.setParent(parent)
        self.clear_plots()

    def clear_plots(self):
        self.fig.clear()
        self.fig.text(.5, .5, "运行回归后生成诊断图", ha="center", color="#536e64")
        self.draw_idle()

    def update_all_plots(self, model_res, panel_df, core_x):
        self.fig.clear()
        ax_coef, ax_scatter, ax_resid, ax_time = self.fig.subplots(2, 2).flat
        self.fig.suptitle(model_res.model_title, color="#21463b", fontweight="bold", fontsize=13)
        for ax in (ax_coef, ax_scatter, ax_resid, ax_time):
            ax.grid(alpha=.16, zorder=0)
            ax.set_axisbelow(True)

        params = model_res.params.reindex(model_res.exog_vars).dropna()
        low = model_res.conf_int_low.reindex(params.index)
        high = model_res.conf_int_high.reindex(params.index)
        pos = np.arange(len(params))
        valid = np.isfinite(low) & np.isfinite(high)
        ax_coef.hlines(pos[valid], low[valid], high[valid], color=BLUE, linewidth=1.8)
        ax_coef.scatter(params, pos, color=BLUE, s=26, zorder=3)
        ax_coef.axvline(0, color="#8b9f97", linestyle="--", linewidth=1)
        ax_coef.set_yticks(pos, labels=[name if len(name) <= 26 else name[:25] + "…" for name in params.index])
        ax_coef.invert_yaxis()
        ax_coef.set(title="回归系数与 95% 置信区间", xlabel="系数")

        y = model_res.dep_var
        sample = panel_df.loc[model_res.sample_index, [y, core_x]].astype(float)
        sample = sample.where(np.isfinite(sample)).dropna()
        x_values, y_values = sample[core_x], sample[y]
        if x_values.nunique() > 1:
            labels = pd.qcut(x_values, min(20, x_values.nunique()), duplicates="drop")
            binned = sample.groupby(labels, observed=True).mean()
            ax_scatter.scatter(binned[core_x], binned[y], color=TEAL, s=26, zorder=3)
            slope, offset = np.polyfit(x_values, y_values, 1)
            bounds = np.array([x_values.min(), x_values.max()])
            ax_scatter.plot(bounds, slope * bounds + offset, color="#806145", linewidth=1.4)
        else:
            ax_scatter.scatter(x_values, y_values, color=TEAL, s=12, alpha=.45)
        ax_scatter.set(title="分仓散点图 · 原始水平值", xlabel=core_x, ylabel=y)

        residuals = model_res.residuals
        fitted = model_res.fitted_values.reindex(residuals.index)
        ax_resid.scatter(fitted, residuals, color=BLUE, s=12, alpha=.32)
        ax_resid.axhline(0, color="#8b9f97", linestyle="--", linewidth=1)
        ax_resid.set(title="残差与拟合值", xlabel="拟合值", ylabel="残差")

        by_time = sample[y].groupby(level=1, sort=True)
        means = by_time.mean()
        if not means.empty:
            ax_time.plot(means.index, means, color=BLUE, linewidth=1.7, marker=".", label="期均值")
            ax_time.fill_between(means.index, by_time.quantile(.25).to_numpy(), by_time.quantile(.75).to_numpy(),
                                 color=BLUE, alpha=.15, label="25%–75% 分位带")
            ax_time.legend(loc="best", frameon=False, fontsize=8)
            if isinstance(means.index, pd.DatetimeIndex):
                ax_time.tick_params(axis="x", labelrotation=24)
            else:
                ax_time.ticklabel_format(axis="x", useOffset=False)
        ax_time.set(title="面板时间趋势 · 原始水平值", xlabel="时期", ylabel=y)
        self.draw_idle()

    def save_high_res(self, filepath, dpi=300):
        self.fig.savefig(filepath, dpi=dpi, bbox_inches="tight", facecolor="white")
