"""Render the same comparison table as HTML, LaTeX, Excel and Word."""

from html import escape
from math import isfinite
from numbers import Real

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter


class AcademicExportEngine:
    TITLE = "面板回归结果"

    @staticmethod
    def _stars(p):
        return "***" if p < .01 else "**" if p < .05 else "*" if p < .10 else ""

    @classmethod
    def build_matrix_rows(cls, models, decimals=3, sub_stat="se"):
        def number(value):
            return f"{value:.{decimals}f}" if isfinite(value) else "—"

        headers = ["变量 / 统计量"] + [m.model_title for m in models]
        names = dict.fromkeys(name for m in models for name in m.params.index)
        rows = []
        for name in names:
            estimates, uncertainty = [str(name)], [""]
            for model in models:
                if name in model.params:
                    estimates.append(number(model.params[name]) + cls._stars(model.pvalues[name]))
                    statistic = model.tstats if sub_stat == "t" else model.std_errors
                    uncertainty.append(f"({number(statistic[name])})")
                else:
                    estimates.append("—")
                    uncertainty.append("")
            rows.extend([estimates, uncertainty])

        details = [
            ["被解释变量", *[m.dep_var for m in models]],
            ["个体固定效应", *["是" if m.entity_fe else "否" for m in models]],
            ["时间固定效应", *["是" if m.time_fe else "否" for m in models]],
            ["标准误类型", *[m.se_type_label for m in models]],
            ["观测值", *[f"{m.nobs:,}" for m in models]],
            ["个体数", *[f"{m.n_entities:,}" for m in models]],
            ["模型 R²", *[number(m.r2_model) for m in models]],
            ["组内 R²", *[number(m.r2_within) for m in models]],
            ["总体 R²", *[number(m.r2_overall) for m in models]],
        ]
        stat_label = "t 统计量" if sub_stat == "t" else "标准误"
        note = f"括号内为{stat_label}。* p < 0.10，** p < 0.05，*** p < 0.01。— 表示无估计值或该项不适用。"
        return headers, rows, details, note

    @classmethod
    def to_html_three_line_table(cls, models, decimals=3, sub_stat="se", *, screen=False):
        if not models:
            return '<p style="color:#4f6b62;margin:20px">运行回归后，结果会显示在这里。</p>'
        headers, body, footer, note = cls.build_matrix_rows(models, decimals, sub_stat)
        line_color = "#547d70" if screen else "#192d43"
        header_bg = "#eaf3ef" if screen else "#eef3f8"
        ink = "#203c35" if screen else "#182638"
        muted = "#536e64" if screen else "#53637a"
        padding = 4 if screen else 5
        lines = [
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
            f'<title>{cls.TITLE}</title></head>',
            f'<body style="font-family:Microsoft YaHei,Arial;color:{ink}">',
        ]
        if not screen:
            lines.append(f'<h2 style="color:#173659">{cls.TITLE}</h2>')
        lines.append(f'<table cellspacing="0" cellpadding="{padding}" width="100%" style="border-collapse:collapse">')
        lines.append("<tr>" + "".join(
            f'<th align="{"left" if i == 0 else "center"}" style="border-top:2px solid {line_color};'
            f'border-bottom:1px solid {line_color};background-color:{header_bg}">{escape(value)}</th>'
            for i, value in enumerate(headers)
        ) + "</tr>")
        for index, row in enumerate(body + footer):
            final = index == len(body) + len(footer) - 1
            border = f"border-bottom:2px solid {line_color};" if final else ""
            uncertainty = index < len(body) and index % 2
            color = muted if uncertainty else ink
            background = ""
            if screen:
                if index == len(body):
                    border += f"border-top:1px solid {line_color};"
                if index >= len(body) or (index // 2) % 2:
                    background = "background-color:#f4f8f6;"
            lines.append("<tr>" + "".join(
                f'<td align="{"left" if i == 0 else "center"}" style="{border}{background}color:{color}">'
                f'{escape(value)}</td>'
                for i, value in enumerate(row)
            ) + "</tr>")
        lines.append(f'</table><p style="color:{muted}">{escape(note)}</p></body></html>')
        return "\n".join(lines)

    @classmethod
    def to_latex_booktabs(cls, models, decimals=3, sub_stat="se"):
        if not models:
            return "% 暂无模型结果"
        headers, body, footer, note = cls.build_matrix_rows(models, decimals, sub_stat)
        replacements = {
            "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "&": r"\&",
            "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
            "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
            "<": r"\textless{}", ">": r"\textgreater{}", "²": r"\textsuperscript{2}"
        }

        def tex(value):
            return "".join(replacements.get(char, char) for char in value)

        lines = [
            r"% 使用 XeLaTeX，文档加载 ctex（或使用 ctexart）、booktabs 和 threeparttable。",
            r"\begin{table}[htbp]", r"\centering", rf"\caption{{{cls.TITLE}}}",
            r"\begin{threeparttable}", r"\begin{tabular}{l" + "c" * len(models) + "}",
            r"\toprule", " & ".join(map(tex, headers)) + r" \\", r"\midrule",
        ]
        lines.extend(" & ".join(map(tex, row)) + r" \\" for row in body + footer)
        lines.extend([
            r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}\footnotesize",
            r"\item " + tex(note), r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}",
        ])
        return "\n".join(lines) + "\n"

    @classmethod
    def export_to_excel_three_line(cls, path, models, decimals=3, sub_stat="se", desc_df=None):
        headers, body, footer, note = cls.build_matrix_rows(models, decimals, sub_stat)
        book = Workbook()
        sheet = book.active
        sheet.title = "回归结果"
        cls._write_excel_sheet(sheet, cls.TITLE, [headers, *body, *footer], decimals, note)
        if desc_df is not None and not desc_df.empty:
            stats = book.create_sheet("描述性统计")
            cls._write_excel_sheet(
                stats, "描述性统计", [list(desc_df.columns), *desc_df.itertuples(index=False, name=None)], decimals
            )
        book.save(path)

    @staticmethod
    def _write_excel_sheet(sheet, title, rows, decimals, note=None):
        width = len(rows[0])
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "B3"
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
        sheet["A1"] = title
        sheet["A1"].font = Font(name="Microsoft YaHei", size=13, bold=True, color="173659")
        sheet.row_dimensions[1].height = 25
        for r, values in enumerate(rows, start=2):
            for c, value in enumerate(values, start=1):
                if isinstance(value, Real) and not isfinite(value):
                    value = "—"
                cell = sheet.cell(r, c, value)
                if isinstance(value, str):
                    # 列名等来自数据文件，写成文本而非公式。
                    cell.data_type = "s"
                if isinstance(value, Real) and not float(value).is_integer():
                    cell.number_format = "0." + "0" * decimals if decimals else "0"
                cell.font = Font(name="Microsoft YaHei", size=10, bold=r == 2, color="182638")
                cell.alignment = Alignment(horizontal="left" if c == 1 else "center", vertical="center")
                if r == 2:
                    cell.border = Border(top=Side(style="medium"), bottom=Side(style="thin"))
                elif r == len(rows) + 1:
                    cell.border = Border(bottom=Side(style="medium"))
            sheet.row_dimensions[r].height = 19
        if note:
            r = len(rows) + 2
            sheet.merge_cells(start_row=r, start_column=1, end_row=r, end_column=width)
            cell = sheet.cell(r, 1, note)
            cell.font = Font(name="Microsoft YaHei", size=9, color="53637A")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            sheet.row_dimensions[r].height = 34
        for c in range(1, width + 1):
            sheet.column_dimensions[get_column_letter(c)].width = 28 if c == 1 else 25

    @classmethod
    def export_to_docx(cls, path, models, decimals=3, sub_stat="se", desc_df=None):
        document = Document()
        section = document.sections[0]
        section.left_margin = section.right_margin = Inches(.65)
        font = document.styles["Normal"].font
        font.name = "Times New Roman"
        font.size = Pt(10)
        document.styles["Normal"].element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
        headers, body, footer, note = cls.build_matrix_rows(models, decimals, sub_stat)
        document.add_heading(cls.TITLE, level=1)
        cls._write_word_table(document, [headers, *body, *footer])
        document.add_paragraph(note)
        if desc_df is not None and not desc_df.empty:
            document.add_heading("描述性统计", level=2)
            rows = [
                [
                    "—" if pd.isna(value) else
                    f"{value:.{decimals}f}" if isinstance(value, float) else str(value)
                    for value in row
                ]
                for row in desc_df.itertuples(index=False, name=None)
            ]
            cls._write_word_table(document, [list(desc_df.columns), *rows])
        document.save(path)

    @staticmethod
    def _write_word_table(document, rows):
        table = document.add_table(rows=0, cols=len(rows[0]))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        borders = OxmlElement("w:tblBorders")
        for side in ("top", "bottom"):
            line = OxmlElement(f"w:{side}")
            line.set(qn("w:val"), "single")
            line.set(qn("w:sz"), "12")
            borders.append(line)
        table._tbl.tblPr.append(borders)
        for index, row in enumerate(rows):
            table_row = table.add_row()
            properties = table_row._tr.get_or_add_trPr()
            properties.append(OxmlElement("w:cantSplit"))
            if index == 0:
                properties.append(OxmlElement("w:tblHeader"))
            for col, (cell, value) in enumerate(zip(table_row.cells, row)):
                paragraph = cell.paragraphs[0]
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT if col == 0 else WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.space_after = Pt(2)
                paragraph.paragraph_format.space_before = Pt(2)
                paragraph.add_run(str(value)).bold = index == 0
                if index == 0:
                    cell_borders = OxmlElement("w:tcBorders")
                    line = OxmlElement("w:bottom")
                    line.set(qn("w:val"), "single")
                    line.set(qn("w:sz"), "6")
                    cell_borders.append(line)
                    cell._tc.get_or_add_tcPr().append(cell_borders)
