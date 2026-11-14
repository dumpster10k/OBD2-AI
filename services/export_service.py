from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping


class ExportService:
    """Eksportuje dane sesji diagnostycznej do popularnych formatów."""

    def export_csv(self, rows: Iterable[Mapping], destination: str | Path) -> Path:
        rows = list(rows)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(rows[0].keys()) if rows else []
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                writer.writerows(rows)
        return path

    def export_excel(self, rows: Iterable[Mapping], destination: str | Path) -> Path:
        from openpyxl import Workbook

        rows = list(rows)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Diagnostyka"
        fieldnames = list(rows[0].keys()) if rows else []
        if fieldnames:
            sheet.append(fieldnames)
            for row in rows:
                sheet.append([row.get(name) for name in fieldnames])
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
        workbook.save(path)
        return path

    def export_pdf(self, rows: Iterable[Mapping], destination: str | Path, title="Raport diagnostyczny") -> Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph

        rows = list(rows)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(str(path), pagesize=A4)
        styles = getSampleStyleSheet()
        content = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
        fieldnames = list(rows[0].keys()) if rows else []
        if fieldnames:
            table_data = [fieldnames] + [[str(row.get(name, "")) for name in fieldnames] for row in rows]
            table = Table(table_data, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            content.append(table)
        document.build(content)
        return path
