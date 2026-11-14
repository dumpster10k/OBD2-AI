from pathlib import Path

from services.export_service import ExportService


ROWS = [
    {"timestamp": "2026-01-01T12:00:00Z", "rpm": 850, "coolant_c": 90},
    {"timestamp": "2026-01-01T12:00:01Z", "rpm": 900, "coolant_c": 91},
]


def test_export_csv(tmp_path: Path):
    destination = ExportService().export_csv(ROWS, tmp_path / "session.csv")
    assert destination.exists()
    assert "timestamp" in destination.read_text(encoding="utf-8-sig")


def test_export_excel(tmp_path: Path):
    destination = ExportService().export_excel(ROWS, tmp_path / "session.xlsx")
    assert destination.exists()
    assert destination.stat().st_size > 0


def test_export_pdf(tmp_path: Path):
    destination = ExportService().export_pdf(ROWS, tmp_path / "session.pdf")
    assert destination.exists()
    assert destination.read_bytes().startswith(b"%PDF")
