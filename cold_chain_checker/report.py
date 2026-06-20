import csv
import os
from collections import defaultdict

from cold_chain_checker.models import ValidationIssue


CATEGORY_LABELS = {
    "departure_time": "发车时间",
    "arrival_location": "到达地点",
    "temperature_continuity": "温度断点",
    "temperature_range": "温度超限",
    "receipt_signature": "签收签字",
    "receipt_box_check": "箱码核对",
    "receipt_box_photo": "箱码照片",
    "load_failed": "加载失败",
}


def _summarize_issues(issues: list) -> str:
    if not issues:
        return ""
    parts = []
    for issue in issues[:3]:
        label = CATEGORY_LABELS.get(issue.category, issue.category)
        parts.append(f"[{label}] {issue.message}")
    if len(issues) > 3:
        parts.append(f"...等共 {len(issues)} 项")
    return "；".join(parts)


def generate_daily_report_csv(
    results: list,
    output_path: str,
) -> str:
    rows = []
    headers = [
        "序号",
        "运单号/文件夹",
        "承运车辆",
        "线路",
        "承运商",
        "状态",
        "错误数",
        "警告数",
        "主要异常",
    ]

    for idx, item in enumerate(results, 1):
        if item["load_failed"]:
            row = {
                "序号": idx,
                "运单号/文件夹": item["folder_name"],
                "承运车辆": "-",
                "线路": "-",
                "承运商": "-",
                "状态": "加载失败",
                "错误数": 1,
                "警告数": 0,
                "主要异常": item["error_message"],
            }
        else:
            waybill = item["waybill"]
            issues = item["issues"]
            error_count = sum(1 for i in issues if i.severity == "error")
            warning_count = sum(1 for i in issues if i.severity == "warning")
            status = "通过" if not issues else "异常"
            row = {
                "序号": idx,
                "运单号/文件夹": waybill.waybill_id,
                "承运车辆": waybill.vehicle_plate,
                "线路": waybill.route,
                "承运商": waybill.carrier,
                "状态": status,
                "错误数": error_count,
                "警告数": warning_count,
                "主要异常": _summarize_issues(issues),
            }
        rows.append(row)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def generate_daily_report_excel(
    results: list,
    output_path: str,
) -> str:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        raise ImportError("未安装 openpyxl，请先安装：pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = "每日校验日报"

    headers = [
        "序号",
        "运单号/文件夹",
        "承运车辆",
        "线路",
        "承运商",
        "状态",
        "错误数",
        "警告数",
        "主要异常",
    ]

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    pass_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    fail_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    load_fail_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    for idx, item in enumerate(results, 2):
        if item["load_failed"]:
            row_data = [
                idx - 1,
                item["folder_name"],
                "-",
                "-",
                "-",
                "加载失败",
                1,
                0,
                item["error_message"],
            ]
            status_fill = load_fail_fill
        else:
            waybill = item["waybill"]
            issues = item["issues"]
            error_count = sum(1 for i in issues if i.severity == "error")
            warning_count = sum(1 for i in issues if i.severity == "warning")
            status = "通过" if not issues else "异常"
            row_data = [
                idx - 1,
                waybill.waybill_id,
                waybill.vehicle_plate,
                waybill.route,
                waybill.carrier,
                status,
                error_count,
                warning_count,
                _summarize_issues(issues),
            ]
            status_fill = pass_fill if not issues else fail_fill

        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=idx, column=col_idx, value=value)
            cell.border = thin_border
            if col_idx == 6:
                cell.fill = status_fill
            if col_idx in (1, 3, 6, 7, 8):
                cell.alignment = center_align
            else:
                cell.alignment = left_align

    column_widths = [6, 22, 14, 28, 12, 10, 8, 8, 50]
    for col_idx, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + col_idx)].width = width

    ws.row_dimensions[1].height = 28

    wb.save(output_path)
    return output_path


def export_daily_report(
    results: list,
    output_path: str,
) -> str:
    ext = os.path.splitext(output_path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return generate_daily_report_excel(results, output_path)
    else:
        return generate_daily_report_csv(results, output_path)
