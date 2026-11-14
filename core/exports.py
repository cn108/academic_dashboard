"""Excel (.xlsx) exports for bursars, principals and class teachers.

openpyxl is used directly rather than pandas: the exports are small tabular
reports and this keeps the production image free of a data-science stack.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from statistics import mean

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

BRAND = "0B3D2E"
BRAND_SOFT = "E7F2EE"
HEADER_FILL = PatternFill("solid", start_color=BRAND, end_color=BRAND)
TOTAL_FILL = PatternFill("solid", start_color=BRAND_SOFT, end_color=BRAND_SOFT)
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14, color=BRAND)
THIN = Side(style="thin", color="98A2B3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY_FORMAT = "#,##0.00"
SCORE_FORMAT = "0.00"

STATUS_LABELS = {
    "paid": "Paid",
    "partial": "Part payment",
    "unpaid": "Unpaid",
    "no_fees": "No fees set",
}


def xlsx_response(workbook: Workbook, filename: str) -> HttpResponse:
    """Send a workbook as a download with the headers a bursar's browser expects."""
    buffer = BytesIO()
    workbook.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _write_title(sheet: Worksheet, title: str, subtitle: str, columns: int) -> int:
    sheet.cell(row=1, column=1, value=title).font = TITLE_FONT
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    sheet.cell(row=2, column=1, value=subtitle).font = Font(size=10, color="475467")
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columns)
    return 4  # one blank row between the heading and the column headers


def _write_header(sheet: Worksheet, row: int, headers: list[str]) -> None:
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=column, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[row].height = 28


def _write_row(sheet: Worksheet, row: int, values: list, *, bold: bool = False, fill=None) -> None:
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=column, value=value)
        cell.border = BORDER
        if bold:
            cell.font = Font(bold=True)
        if fill is not None:
            cell.fill = fill


def _fit_columns(sheet: Worksheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def broadsheet_workbook(sheet_data: dict, school_name: str = "") -> Workbook:
    """Students × subjects totals, averages, positions and the class average row."""
    subjects = sheet_data["subjects"]
    students = sheet_data["students"]
    class_name = sheet_data["class"]["name"]
    session_name = sheet_data["session"]["name"]
    term_name = sheet_data["term"]["name"]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Broadsheet"

    headers = ["Student", "Admission No"] + [subject["name"] for subject in subjects]
    headers += ["Total", "Average", "Position"]
    header_row = _write_title(
        sheet,
        f"{class_name} broadsheet — {term_name}, {session_name}",
        school_name or "Published results only",
        len(headers),
    )
    _write_header(sheet, header_row, headers)

    row_number = header_row
    for student in students:
        row_number += 1
        score_for = {score["subject"]: score["total"] for score in student["scores"]}
        values = [student["full_name"], student["admission_number"] or ""]
        values += [score_for.get(subject["id"]) for subject in subjects]
        values += [student["total"], student["average"], student["position"]]
        _write_row(sheet, row_number, values)
        for column in range(3, 3 + len(subjects)):
            sheet.cell(row=row_number, column=column).alignment = Alignment(horizontal="center")
        sheet.cell(row=row_number, column=len(headers) - 1).number_format = SCORE_FORMAT
        sheet.cell(row=row_number, column=len(headers)).alignment = Alignment(horizontal="center")

    averages = [student["average"] for student in students if student["average"] is not None]
    class_average = round(mean(averages), 2) if averages else None
    row_number += 1
    _write_row(
        sheet,
        row_number,
        ["Class Average", ""]
        + [subject["class_average"] for subject in subjects]
        + [None, class_average, None],
        bold=True,
        fill=TOTAL_FILL,
    )
    for column in range(3, 3 + len(subjects)):
        sheet.cell(row=row_number, column=column).alignment = Alignment(horizontal="center")
    sheet.cell(row=row_number, column=len(headers) - 1).number_format = SCORE_FORMAT

    _fit_columns(sheet, [30, 16] + [18] * len(subjects) + [10, 10, 10])
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=3)
    return workbook


def ledger_workbook(
    positions: list[dict], session_name: str, term_name: str, school_name: str = ""
) -> Workbook:
    """Every student's expected fees, payments and balance for one term."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Fee ledger"

    headers = ["Admission No", "Student", "Class", "Expected fees", "Amount paid", "Balance", "Status"]
    header_row = _write_title(
        sheet,
        f"Fee ledger — {term_name}, {session_name}",
        school_name or "All students",
        len(headers),
    )
    _write_header(sheet, header_row, headers)

    row_number = header_row
    expected_total = Decimal("0.00")
    paid_total = Decimal("0.00")
    balance_total = Decimal("0.00")
    for position in positions:
        row_number += 1
        expected_total += position["expected"]
        paid_total += position["paid"]
        balance_total += position["balance"]
        _write_row(
            sheet,
            row_number,
            [
                position["admission_number"] or "",
                position["full_name"],
                position["class_name"] or "",
                float(position["expected"]),
                float(position["paid"]),
                float(position["balance"]),
                STATUS_LABELS.get(position["status"], position["status"]),
            ],
        )
        for column in (4, 5, 6):
            sheet.cell(row=row_number, column=column).number_format = MONEY_FORMAT

    row_number += 1
    _write_row(
        sheet,
        row_number,
        ["", "TOTAL", "", float(expected_total), float(paid_total), float(balance_total), ""],
        bold=True,
        fill=TOTAL_FILL,
    )
    for column in (4, 5, 6):
        sheet.cell(row=row_number, column=column).number_format = MONEY_FORMAT

    _fit_columns(sheet, [16, 30, 14, 16, 14, 14, 16])
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=3)
    return workbook
