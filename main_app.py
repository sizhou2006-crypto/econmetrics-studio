import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QTabWidget, QTextBrowser, QPlainTextEdit,
    QFileDialog, QMessageBox, QRadioButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter, QScrollArea, QFrame, QLineEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QShortcut

from core_econometrics import PanelEconometricsEngine, ModelResultWrapper
from export_engine import AcademicExportEngine
if getattr(sys, "frozen", False):
    os.environ.setdefault("MPLCONFIGDIR", str(Path(sys.executable).parent / ".cache" / "matplotlib"))

from plot_engine import EconometricPlotCanvas


class EconMetricsMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EconMetrics Studio · 经管计量工作台")
        self.resize(1330, 830)
        self.setMinimumSize(860, 590)

        # 核心数据与模型状态
        self.raw_df: pd.DataFrame = pd.DataFrame()
        self.panel_df: pd.DataFrame = pd.DataFrame()
        self.model_cart: list[ModelResultWrapper] = []
        self.desc_df = pd.DataFrame()

        self._init_ui()
        self._apply_stylesheet()
        # 启动后默认加载内置的经管面板数据并演示回归
        self.load_demo_data()

    def _init_ui(self):
        central = QWidget()
        central.setObjectName("Workspace")
        self.setCentralWidget(central)
        workspace = QVBoxLayout(central)
        workspace.setContentsMargins(18, 16, 18, 0)
        workspace.setSpacing(12)
        workspace.addWidget(self._make_header())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._make_sidebar())
        splitter.addWidget(self._make_results())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([318, 960])
        workspace.addWidget(splitter, 1)
        self.statusBar().setSizeGripEnabled(False)

        for sequence, action in (
            ("Ctrl+O", self.load_local_file),
            ("Ctrl+Return", self.run_single_model),
            ("Ctrl+Shift+Return", self.run_benchmark_suite),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(action)

    def _make_header(self):
        header = QFrame()
        header.setObjectName("AppHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 9, 12, 9)
        row.setSpacing(10)

        brand = QLabel("EconMetrics Studio")
        brand.setObjectName("Brand")
        row.addWidget(brand)
        caption = QLabel("计量工作台")
        caption.setObjectName("BrandCaption")
        row.addWidget(caption)
        row.addStretch(1)

        self.source_label = QLabel()
        self.source_label.setTextFormat(Qt.PlainText)
        self.source_label.setObjectName("DataSource")
        self.source_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.source_label.setMaximumWidth(330)
        row.addWidget(self.source_label, 1)

        self.btn_load_demo = QPushButton("载入示例")
        self.btn_load_demo.setObjectName("HeaderButton")
        self.btn_load_demo.clicked.connect(self.load_demo_data)
        self.btn_load_file = QPushButton("导入数据…")
        self.btn_load_file.setObjectName("ImportButton")
        self.btn_load_file.setToolTip("导入 CSV、Excel 或 Stata 文件（Ctrl+O）")
        self.btn_load_file.clicked.connect(self.load_local_file)
        row.addWidget(self.btn_load_demo)
        row.addWidget(self.btn_load_file)
        return header

    def _make_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(296)
        sidebar.setMaximumWidth(410)
        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        settings = QWidget()
        settings.setObjectName("Settings")
        layout = QVBoxLayout(settings)
        layout.setContentsMargins(13, 13, 13, 7)
        layout.setSpacing(7)

        layout.addWidget(self._section_heading("面板设定"))
        self.cmb_entity = QComboBox()
        self.cmb_time = QComboBox()
        self._form_row(layout, "个体列", self.cmb_entity)
        self._form_row(layout, "时间列", self.cmb_time)
        self.lbl_panel_status = QLabel("尚未载入数据")
        self.lbl_panel_status.setObjectName("PanelStatus")
        self.lbl_panel_status.setWordWrap(True)
        self.lbl_panel_status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.lbl_panel_status)
        self.cmb_entity.currentIndexChanged.connect(self.on_xtset_changed)
        self.cmb_time.currentIndexChanged.connect(self.on_xtset_changed)

        layout.addWidget(self._section_heading("回归变量", separated=True))
        self.cmb_dep_y = QComboBox()
        self._form_row(layout, "被解释变量 Y", self.cmb_dep_y)
        x_row = QHBoxLayout()
        x_row.addWidget(QLabel("解释变量 X"))
        x_row.addStretch()
        self.selected_count = QLabel("已选 0 项")
        self.selected_count.setObjectName("Quiet")
        x_row.addWidget(self.selected_count)
        layout.addLayout(x_row)

        self.var_filter = QLineEdit()
        self.var_filter.setPlaceholderText("搜索解释变量")
        self.var_filter.setClearButtonEnabled(True)
        self.var_filter.setAccessibleName("搜索解释变量")
        layout.addWidget(self.var_filter)
        self.lst_exog_x = QListWidget()
        self.lst_exog_x.setAccessibleName("解释变量")
        self.lst_exog_x.setMinimumHeight(112)
        self.lst_exog_x.setMaximumHeight(169)
        layout.addWidget(self.lst_exog_x, 1)
        self.var_filter.textChanged.connect(self._sync_variable_picker)
        self.lst_exog_x.itemChanged.connect(self._sync_variable_picker)
        self.cmb_dep_y.currentTextChanged.connect(self._sync_variable_picker)

        layout.addWidget(self._section_heading("估计设定", separated=True))
        self.cmb_model_type = QComboBox()
        for model in PanelEconometricsEngine.MODEL_TYPES:
            self.cmb_model_type.addItem(model.split(" (")[0], model)
        self._form_row(layout, "模型", self.cmb_model_type)

        self.cmb_se_type = QComboBox()
        for covariance in PanelEconometricsEngine.SE_TYPES:
            self.cmb_se_type.addItem(covariance.split(" (")[0], covariance)
        self._form_row(layout, "标准误", self.cmb_se_type)
        for combo in (self.cmb_entity, self.cmb_time, self.cmb_dep_y, self.cmb_model_type, self.cmb_se_type):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
        scroll.setWidget(settings)
        outer.addWidget(scroll, 1)

        actions = QWidget()
        actions.setObjectName("SidebarActions")
        action_row = QHBoxLayout(actions)
        action_row.setContentsMargins(12, 10, 12, 11)
        action_row.setSpacing(7)
        self.btn_run_single = QPushButton("运行并加入对比")
        self.btn_run_single.setObjectName("SecondaryButton")
        self.btn_run_single.setToolTip("运行当前模型并追加到对比表（Ctrl+Enter）")
        self.btn_run_single.clicked.connect(self.run_single_model)
        self.btn_run_benchmark = QPushButton("生成四列回归")
        self.btn_run_benchmark.setObjectName("PrimaryButton")
        self.btn_run_benchmark.setToolTip("重新生成 OLS、个体 FE、双向 FE 和 RE（Ctrl+Shift+Enter）")
        self.btn_run_benchmark.clicked.connect(self.run_benchmark_suite)
        action_row.addWidget(self.btn_run_single, 1)
        action_row.addWidget(self.btn_run_benchmark, 1)
        outer.addWidget(actions)
        return sidebar

    @staticmethod
    def _section_heading(text, separated=False):
        label = QLabel(text)
        label.setObjectName("DividedHeading" if separated else "SectionHeading")
        return label

    @staticmethod
    def _form_row(layout, text, widget):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(text)
        label.setMinimumWidth(73)
        label.setBuddy(widget)
        widget.setAccessibleName(text)
        row.addWidget(label)
        row.addWidget(widget, 1)
        layout.addLayout(row)

    def _make_results(self):
        panel = QFrame()
        panel.setObjectName("Results")
        right = QVBoxLayout(panel)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.tabs = QTabWidget()
        right.addWidget(self.tabs, 1)

        table_tab = QWidget()
        table = QVBoxLayout(table_tab)
        table.setContentsMargins(13, 10, 13, 11)
        table.setSpacing(7)
        table_head = QHBoxLayout()
        table_head.setSpacing(8)
        title = QLabel("模型对比")
        title.setObjectName("ViewTitle")
        table_head.addWidget(title)
        self.model_count = QLabel()
        self.model_count.setObjectName("ModelCount")
        table_head.addWidget(self.model_count)
        table_head.addStretch(1)
        table_head.addWidget(QLabel("括号内"))
        self.rad_se = QRadioButton("标准误")
        self.rad_se.setChecked(True)
        self.rad_t = QRadioButton("t 值")
        self.rad_se.toggled.connect(self.refresh_outputs)
        table_head.addWidget(self.rad_se)
        table_head.addWidget(self.rad_t)
        table_head.addSpacing(6)
        precision = QLabel("小数位")
        table_head.addWidget(precision)
        self.spn_decimals = QSpinBox()
        self.spn_decimals.setRange(2, 6)
        self.spn_decimals.setValue(3)
        self.spn_decimals.setAccessibleName("小数位")
        precision.setBuddy(self.spn_decimals)
        self.spn_decimals.valueChanged.connect(self.refresh_outputs)
        table_head.addWidget(self.spn_decimals)
        self.btn_clear_cart = QPushButton("清空")
        self.btn_clear_cart.setObjectName("QuietButton")
        self.btn_clear_cart.setToolTip("清空对比表中的模型")
        self.btn_clear_cart.clicked.connect(self.clear_model_cart)
        table_head.addWidget(self.btn_clear_cart)
        table.addLayout(table_head)

        self.html_viewer = QTextBrowser()
        self.html_viewer.setAccessibleName("回归结果表")
        self.html_viewer.setObjectName("RegressionTable")
        table.addWidget(self.html_viewer, 1)
        self.lbl_hausman = QLabel()
        self.lbl_hausman.setObjectName("Hausman")
        self.lbl_hausman.setWordWrap(True)
        self.lbl_hausman.setTextFormat(Qt.PlainText)
        table.addWidget(self.lbl_hausman)
        self.tabs.addTab(table_tab, "回归结果")

        plot_tab = QWidget()
        plot = QVBoxLayout(plot_tab)
        plot.setContentsMargins(8, 7, 8, 7)
        self.plot_canvas = EconometricPlotCanvas()
        plot.addWidget(self.plot_canvas)
        self.tabs.addTab(plot_tab, "诊断图")

        latex_tab = QWidget()
        latex = QVBoxLayout(latex_tab)
        latex.setContentsMargins(13, 10, 13, 10)
        latex_head = QHBoxLayout()
        latex_head.addWidget(self._section_heading("LaTeX 源码"))
        latex_head.addStretch()
        btn_copy_latex = QPushButton("复制源码")
        btn_copy_latex.clicked.connect(self.copy_latex_code)
        latex_head.addWidget(btn_copy_latex)
        latex.addLayout(latex_head)
        self.txt_latex = QPlainTextEdit()
        self.txt_latex.setReadOnly(True)
        self.txt_latex.setFont(QFont("Consolas", 10))
        latex.addWidget(self.txt_latex, 1)
        self.tabs.addTab(latex_tab, "LaTeX")

        data_tab = QWidget()
        data = QVBoxLayout(data_tab)
        data.setContentsMargins(13, 10, 13, 10)
        data.addWidget(self._section_heading("描述性统计"))
        self.html_desc_viewer = QTextBrowser()
        self.html_desc_viewer.setMinimumHeight(120)
        self.html_desc_viewer.setMaximumHeight(220)
        data.addWidget(self.html_desc_viewer)
        data.addWidget(self._section_heading("原始数据（前 100 行）"))
        self.tbl_raw_preview = QTableWidget()
        self.tbl_raw_preview.setAlternatingRowColors(True)
        self.tbl_raw_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_raw_preview.verticalHeader().setDefaultSectionSize(24)
        data.addWidget(self.tbl_raw_preview, 1)
        self.tabs.addTab(data_tab, "数据预览")

        footer = QWidget()
        footer.setObjectName("ExportBar")
        exports = QHBoxLayout(footer)
        exports.setContentsMargins(13, 9, 13, 9)
        exports.setSpacing(7)
        exports.addWidget(self._section_heading("导出"))
        exports.addSpacing(3)
        btn_exp_excel = QPushButton("Excel")
        btn_exp_excel.clicked.connect(self.export_excel_Action)
        btn_exp_word = QPushButton("Word / HTML")
        btn_exp_word.clicked.connect(self.export_word_html_action)
        btn_exp_latex = QPushButton("LaTeX")
        btn_exp_latex.clicked.connect(self.export_latex_action)
        btn_exp_plot = QPushButton("保存诊断图")
        btn_exp_plot.setToolTip("保存为 300 DPI PNG 或 PDF")
        btn_exp_plot.clicked.connect(self.export_plot_action)
        for button in (btn_exp_excel, btn_exp_word, btn_exp_latex):
            exports.addWidget(button)
        exports.addStretch()
        exports.addWidget(btn_exp_plot)
        right.addWidget(footer)
        self.export_buttons = (btn_exp_excel, btn_exp_word, btn_exp_latex, btn_exp_plot, btn_copy_latex)
        return panel

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#Workspace { background: #edf2f1; color: #1e312f; }
            QLabel { color: #263b37; }
            QFrame#AppHeader { background: #173b36; border-radius: 8px; }
            QLabel#Brand { color: #f9fffd; font-size: 25px; font-weight: 700; }
            QLabel#BrandCaption { color: #c5d9d2; font-size: 13px; }
            QLabel#DataSource { color: #d7e9e3; padding: 0 4px; }
            QFrame#Sidebar, QFrame#Results {
                background: #ffffff; border: 1px solid #d2ddda; border-radius: 7px;
            }
            QWidget#Settings, QScrollArea#SettingsScroll { background: #ffffff; }
            QWidget#SidebarActions, QWidget#ExportBar {
                background: #f5f8f7; border-top: 1px solid #dbe5e1;
                border-bottom-left-radius: 6px; border-bottom-right-radius: 6px;
            }
            QLabel#SectionHeading, QLabel#DividedHeading {
                color: #26443d; font-size: 13px; font-weight: 700; padding: 2px 0;
            }
            QLabel#DividedHeading { border-top: 1px solid #dce7e3; padding-top: 8px; margin-top: 4px; }
            QLabel#PanelStatus {
                color: #335d51; background: #edf6f2; border-left: 3px solid #519582;
                padding: 5px 7px; border-top-right-radius: 4px; border-bottom-right-radius: 4px;
            }
            QLabel#Quiet { color: #526b64; }
            QLabel#ViewTitle { font-size: 17px; font-weight: 700; color: #213d37; }
            QLabel#ModelCount {
                color: #34594f; background: #e9f3ee; border-radius: 4px; padding: 3px 6px;
            }
            QLabel#Hausman {
                color: #314c46; background: #f0f6f3; border-left: 3px solid #519582;
                padding: 7px 9px; border-top-right-radius: 4px; border-bottom-right-radius: 4px;
            }
            QComboBox, QSpinBox, QLineEdit, QListWidget, QTableWidget, QTextBrowser, QPlainTextEdit {
                color: #223b35; background: #ffffff; border: 1px solid #cbdad5; border-radius: 5px;
                selection-background-color: #d9eee5; selection-color: #153d33;
            }
            QComboBox, QLineEdit { padding: 4px 7px; min-height: 19px; }
            QSpinBox { padding: 3px 3px 3px 6px; min-height: 18px; }
            QComboBox QAbstractItemView { background: #ffffff; color: #223b35; }
            QComboBox:focus, QSpinBox:focus, QLineEdit:focus, QListWidget:focus, QPushButton:focus {
                border: 1px solid #418775;
            }
            QListWidget { padding: 3px; }
            QListWidget::item { padding: 3px 4px; }
            QListWidget::item:hover { background: #edf5f1; }
            QTextBrowser#RegressionTable { border-color: #d9e5e0; padding: 5px; }
            QPlainTextEdit { background: #f8fbfa; padding: 6px; }
            QTableWidget { alternate-background-color: #f3f8f5; gridline-color: #e3ece8; }
            QHeaderView::section { background: #eaf3ef; color: #274a40; border: 0; padding: 5px; }
            QTabWidget::pane { background: #ffffff; border: 0; border-top: 1px solid #dce7e2; }
            QTabWidget::tab-bar { left: 8px; }
            QTabBar::tab {
                background: transparent; color: #536a62; padding: 10px 14px;
                margin: 0 2px; border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected { color: #1c5a49; border-bottom-color: #267960; font-weight: 700; }
            QTabBar::tab:hover { background: #eff7f3; }
            QPushButton {
                background: #ffffff; color: #23453b; border: 1px solid #c7d8d2;
                border-radius: 5px; padding: 4px 10px; min-height: 20px;
            }
            QPushButton:hover { background: #eaf4ef; border-color: #8ab2a5; }
            QPushButton:pressed { background: #deede7; }
            QPushButton#PrimaryButton {
                background: #216c56; color: white; border-color: #216c56; font-weight: 700;
            }
            QPushButton#PrimaryButton:hover { background: #195540; border-color: #195540; }
            QPushButton#SecondaryButton { font-weight: 700; }
            QPushButton#HeaderButton {
                background: #284e47; border-color: #587972; color: #f0f8f5;
            }
            QPushButton#HeaderButton:hover { background: #386359; }
            QPushButton#ImportButton { background: #e5f3ed; color: #1a463a; border-color: #e5f3ed; font-weight: 700; }
            QPushButton#ImportButton:hover { background: #cfeadd; border-color: #cfeadd; }
            QPushButton#QuietButton { color: #536b62; padding-left: 7px; padding-right: 7px; }
            QPushButton:disabled, QPushButton#PrimaryButton:disabled {
                color: #6c817a; background: #f0f4f2; border-color: #d9e5df;
            }
            QStatusBar { color: #4e6960; padding-left: 18px; background: #edf2f1; }
            QStatusBar::item { border: 0; }
        """)

    def _sync_variable_picker(self, *_):
        search = self.var_filter.text().strip().casefold()
        dep = self.cmb_dep_y.currentText()
        selected = 0
        for index in range(self.lst_exog_x.count()):
            item = self.lst_exog_x.item(index)
            is_exog = item.text() != dep
            item.setHidden(not is_exog or search not in item.text().casefold())
            selected += is_exog and item.checkState() == Qt.Checked
        self.selected_count.setText(f"已选 {selected} 项")
        ready = bool(dep and selected)
        self.btn_run_single.setEnabled(ready)
        self.btn_run_benchmark.setEnabled(ready)


    def load_demo_data(self):
        data = PanelEconometricsEngine.generate_demo_panel_data()
        self._set_data(data, "内置模拟数据 · 120 家企业", "firm_id", "year")
        self.run_benchmark_suite()

    def load_local_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入本地数据", "", "数据文件 (*.csv *.xlsx *.xls *.dta)"
        )
        if not filename:
            return
        try:
            self.load_path(Path(filename))
        except Exception as error:
            QMessageBox.critical(self, "导入失败", str(error))

    def load_path(self, path):
        suffix = path.suffix.lower()
        if suffix == ".csv":
            try:
                data = pd.read_csv(path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                data = pd.read_csv(path, encoding="gb18030")
        elif suffix == ".xlsx":
            data = pd.read_excel(path, engine="openpyxl")
        elif suffix == ".xls":
            data = pd.read_excel(path, engine="xlrd")
        elif suffix == ".dta":
            data = pd.read_stata(path, convert_categoricals=False)
        else:
            raise ValueError("请选择 CSV、XLSX、XLS 或 DTA 文件。")
        if data.empty or len(data.columns) < 2:
            raise ValueError("文件至少需要两列和一条有效记录。")
        data.columns = [str(name).strip() for name in data.columns]
        if not data.columns.is_unique:
            raise ValueError("整理列名后发现重名列，请修改表头。")
        names = {column.casefold(): column for column in data.columns}
        entity = next((names[key] for key in ("firm_id", "entity_id", "id", "企业", "个体") if key in names), None)
        time = next((names[key] for key in ("year", "date", "time", "年份", "日期", "时间") if key in names), None)
        if entity is None:
            entity = next(column for column in data.columns if column != time)
        if time is None:
            time = next(column for column in data.columns if column != entity)
        self._set_data(data, path.name, entity, time)

    def _set_data(self, data, source, entity, time):
        self.raw_df = data
        self.source_label.setText(self.source_label.fontMetrics().elidedText(source, Qt.ElideMiddle, 230))
        self.source_label.setToolTip(source)
        columns = list(data.columns)
        for combo, selected in ((self.cmb_entity, entity), (self.cmb_time, time)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(columns)
            combo.setCurrentText(selected)
            combo.blockSignals(False)
        self.on_xtset_changed()
        self._update_data_preview()
        self.tabs.setCurrentIndex(3)

    def on_xtset_changed(self):
        if self.raw_df.empty:
            return
        self.panel_df = pd.DataFrame()
        self.desc_df = pd.DataFrame()
        self.clear_model_cart()
        self.cmb_dep_y.blockSignals(True)
        self.lst_exog_x.blockSignals(True)
        self.cmb_dep_y.clear()
        self.lst_exog_x.clear()
        entity, time = self.cmb_entity.currentText(), self.cmb_time.currentText()
        try:
            self.panel_df, info = PanelEconometricsEngine.validate_and_set_panel(self.raw_df, entity, time)
            self.lbl_panel_status.setText(info["status_text"])
        except (ValueError, TypeError) as error:
            self.lbl_panel_status.setText(str(error))

        columns = list(self.panel_df.select_dtypes(include=["number", "bool"]).columns)
        self.cmb_dep_y.addItems(columns)
        for index, column in enumerate(columns):
            item = QListWidgetItem(column)
            item.setCheckState(Qt.Checked if 1 <= index <= 5 else Qt.Unchecked)
            self.lst_exog_x.addItem(item)

        self.cmb_dep_y.blockSignals(False)
        self.lst_exog_x.blockSignals(False)
        self.var_filter.clear()
        self._sync_variable_picker()
        self.desc_df = PanelEconometricsEngine.compute_descriptive_stats(self.panel_df, columns)
        if self.desc_df.empty:
            self.html_desc_viewer.setPlainText("设定面板键后显示数值列的描述性统计。")
        else:
            html = self.desc_df.to_html(index=False, float_format=lambda value: f"{value:.3f}", border=0, na_rep="—")
            self.html_desc_viewer.setHtml(
                '<style>table{border-collapse:collapse;width:100%;}'
                'th{border-top:2px solid #528172;border-bottom:1px solid #528172;padding:4px;}'
                'td{padding:4px;text-align:center;}'
                'tr:last-child td{border-bottom:2px solid #528172;}</style>' + html
            )

    def _update_data_preview(self):
        preview = self.raw_df.head(100)
        self.tbl_raw_preview.clearContents()
        self.tbl_raw_preview.setRowCount(len(preview))
        self.tbl_raw_preview.setColumnCount(len(preview.columns))
        self.tbl_raw_preview.setHorizontalHeaderLabels(list(preview.columns))
        for row, values in enumerate(preview.itertuples(index=False, name=None)):
            for column, value in enumerate(values):
                self.tbl_raw_preview.setItem(row, column, QTableWidgetItem("—" if pd.isna(value) else str(value)))
        self.tbl_raw_preview.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def _get_selected_vars(self):
        dep = self.cmb_dep_y.currentText()
        return dep, [
            item.text() for item in (self.lst_exog_x.item(i) for i in range(self.lst_exog_x.count()))
            if item.checkState() == Qt.Checked and item.text() != dep
        ]

    def run_single_model(self):
        if not self.btn_run_single.isEnabled():
            return
        kind = self.cmb_model_type.currentData()
        title = f"({len(self.model_cart) + 1}) {kind.split(' (')[0]}"
        self._run_models([(kind, title)], replace=False)

    def run_benchmark_suite(self):
        if not self.btn_run_benchmark.isEnabled():
            return
        models = PanelEconometricsEngine.MODEL_TYPES
        self._run_models([
            (models[3], "(1) 混合 OLS"), (models[1], "(2) 个体 FE"),
            (models[0], "(3) 双向 FE"), (models[4], "(4) 随机效应 RE")
        ], replace=True)

    def _run_models(self, configurations, replace):
        dep, exog = self._get_selected_vars()
        if not dep or not exog:
            QMessageBox.warning(self, "选择变量", "请选择一个 Y 和至少一个与 Y 不同的 X。")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            results = [
                PanelEconometricsEngine.fit_panel_model(
                    self.panel_df, dep, exog, kind, self.cmb_se_type.currentData(), title
                )
                for kind, title in configurations
            ]
        except Exception as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "回归未完成", str(error))
            return
        else:
            QApplication.restoreOverrideCursor()

        self.model_cart = results if replace else [*self.model_cart, *results]
        active = results[2] if replace else results[0]
        self.refresh_outputs()
        try:
            test = PanelEconometricsEngine.run_hausman_test(self.panel_df, dep, exog)
            self.lbl_hausman.setText(
                f"经典 Hausman 检验（个体 FE / RE）  χ²({test['df']}) = {test['chi2']:.3f}  ·  "
                f"p = {test['pval']:.4g}\n{test['recommendation']}"
            )
        except Exception as error:
            self.lbl_hausman.setText(f"Hausman 检验未完成 · {error}")
        try:
            self.plot_canvas.update_all_plots(active, self.panel_df, exog[0])
            self.export_buttons[3].setEnabled(True)
        except Exception as error:
            self.plot_canvas.clear_plots()
            self.export_buttons[3].setEnabled(False)
            QMessageBox.warning(self, "图表生成失败", str(error))
        self.tabs.setCurrentIndex(0)
        self.statusBar().showMessage(f"诊断图已更新，对应 {active.model_title}", 6500)

    def clear_model_cart(self):
        self.model_cart.clear()
        self.lbl_hausman.setText("回归后自动计算经典 Hausman 检验。")
        self.plot_canvas.clear_plots()
        self.export_buttons[3].setEnabled(False)
        self.refresh_outputs()
        self.statusBar().clearMessage()

    def refresh_outputs(self):
        args = self._table_args()
        self.html_viewer.setHtml(AcademicExportEngine.to_html_three_line_table(*args, screen=True))
        self.model_count.setText(f"{len(self.model_cart)} 列")
        self.txt_latex.setPlainText(AcademicExportEngine.to_latex_booktabs(*args))
        available = bool(self.model_cart)
        self.btn_clear_cart.setEnabled(available)
        for index in (0, 1, 2, 4):
            self.export_buttons[index].setEnabled(available)

    def _table_args(self):
        return self.model_cart, self.spn_decimals.value(), "t" if self.rad_t.isChecked() else "se"

    def copy_latex_code(self):
        QApplication.clipboard().setText(self.txt_latex.toPlainText())
        self.statusBar().showMessage("已复制 LaTeX 源码。", 5000)

    def _save_file(self, title, filename, filters, writers):
        path, selected = QFileDialog.getSaveFileName(self, title, filename, filters)
        if not path:
            return
        target = Path(path)
        suffix = target.suffix.lower()
        if suffix not in writers:
            suffix = next((key for key in writers if key in selected), next(iter(writers)))
            target = target.with_suffix(suffix)
        staged = None
        try:
            with NamedTemporaryFile(dir=target.parent, suffix=suffix, delete=False) as temporary:
                staged = Path(temporary.name)
            writers[suffix](staged)
            staged.replace(target)
            self.statusBar().showMessage(f"已保存 {target.name}", 7000)
        except Exception as error:
            QMessageBox.critical(self, "保存失败", str(error))
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    def export_excel_Action(self):
        self._save_file(
            "导出 Excel", "面板回归结果.xlsx", "Excel 工作簿 (*.xlsx)",
            {".xlsx": lambda path: AcademicExportEngine.export_to_excel_three_line(
                path, *self._table_args(), desc_df=self.desc_df
            )}
        )

    def export_word_html_action(self):
        self._save_file(
            "导出 Word / HTML", "面板回归结果.docx", "Word 文档 (*.docx);;HTML 网页 (*.html)",
            {
                ".docx": lambda path: AcademicExportEngine.export_to_docx(path, *self._table_args(), desc_df=self.desc_df),
                ".html": lambda path: path.write_text(
                    AcademicExportEngine.to_html_three_line_table(*self._table_args()), encoding="utf-8"
                ),
            }
        )

    def export_latex_action(self):
        self._save_file(
            "导出 LaTeX", "面板回归结果.tex", "LaTeX 源码 (*.tex)",
            {".tex": lambda path: path.write_text(self.txt_latex.toPlainText(), encoding="utf-8")}
        )

    def export_plot_action(self):
        self._save_file(
            "导出诊断图", "回归诊断图.png", "PNG 图片 (*.png);;PDF 矢量图 (*.pdf)",
            {".png": self.plot_canvas.save_high_res, ".pdf": self.plot_canvas.save_high_res}
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if "Microsoft YaHei UI" not in QFontDatabase.families():
        font_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / "msyh.ttc"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Microsoft YaHei UI", 9))
    win = EconMetricsMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
