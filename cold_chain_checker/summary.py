from collections import defaultdict
from cold_chain_checker.models import ValidationIssue, Waybill


def generate_anomaly_summary(waybills: list, all_issues: dict) -> str:
    vehicle_issues = defaultdict(list)
    for waybill_id, issues in all_issues.items():
        wb = _find_waybill(waybills, waybill_id)
        if not wb:
            continue
        key = f"{wb.vehicle_plate} | {wb.route}"
        for issue in issues:
            vehicle_issues[key].append(issue)

    if not vehicle_issues:
        return "✅ 无异常，所有运单均通过校验。"

    lines = []
    lines.append("=" * 70)
    lines.append("异常摘要（按承运车辆 / 线路）")
    lines.append("=" * 70)

    for vehicle_route in sorted(vehicle_issues.keys()):
        issues = vehicle_issues[vehicle_route]
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        lines.append("")
        lines.append(f"🚛 {vehicle_route}")
        lines.append(f"   错误 {error_count} 项 | 警告 {warning_count} 项")

        category_groups = defaultdict(list)
        for issue in issues:
            category_groups[issue.category].append(issue)

        category_labels = {
            "departure_time": "发车时间",
            "arrival_location": "到达地点",
            "temperature_continuity": "温度断点",
            "temperature_range": "温度超限",
            "receipt_signature": "签收签字",
            "receipt_box_check": "箱码核对",
            "receipt_box_photo": "箱码照片",
        }

        for cat, cat_issues in category_groups.items():
            label = category_labels.get(cat, cat)
            lines.append(f"   ├── {label}：{len(cat_issues)} 条")
            for ci in cat_issues:
                prefix = "⛔" if ci.severity == "error" else "⚠️"
                lines.append(f"   │   {prefix} [{ci.waybill_id}] {ci.message}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def _find_waybill(waybills: list, waybill_id: str):
    for wb in waybills:
        if wb.waybill_id == waybill_id:
            return wb
    return None
