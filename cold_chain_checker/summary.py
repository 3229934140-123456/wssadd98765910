from collections import defaultdict
from cold_chain_checker.models import ValidationIssue, Waybill


CATEGORY_LABELS = {
    "departure_time": "发车时间",
    "arrival_location": "到达地点",
    "temperature_continuity": "温度断点",
    "temperature_range": "温度超限",
    "receipt_signature": "签收签字",
    "receipt_box_check": "箱码核对",
    "receipt_box_photo": "箱码照片",
    "load_failed": "数据加载失败",
}


def generate_anomaly_summary(waybills: list, all_issues: dict, load_failures: list = None) -> str:
    vehicle_issues = defaultdict(list)
    for waybill_id, issues in all_issues.items():
        wb = _find_waybill(waybills, waybill_id)
        if not wb:
            continue
        key = f"{wb.vehicle_plate} | {wb.route}"
        for issue in issues:
            vehicle_issues[key].append(issue)

    if load_failures:
        for fail in load_failures:
            wb = fail.get("waybill")
            if wb:
                key = f"{wb.vehicle_plate} | {wb.route}"
            else:
                key = "加载失败 | 需补数据"
            vehicle_issues[key].append(ValidationIssue(
                waybill_id=fail["folder_name"],
                category="load_failed",
                severity="error",
                message=fail["error_message"],
            ))

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

        for cat, cat_issues in category_groups.items():
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f"   ├── {label}：{len(cat_issues)} 条")
            for ci in cat_issues:
                prefix = "⛔" if ci.severity == "error" else "⚠️"
                lines.append(f"   │   {prefix} [{ci.waybill_id}] {ci.message}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def generate_product_summary(results: list) -> str:
    product_data = defaultdict(lambda: {
        "vehicles": set(),
        "routes": set(),
        "waybill_ids": [],
        "has_anomaly": False,
        "issues": [],
    })

    for item in results:
        waybill = item.get("waybill")
        if not waybill:
            continue
        issues = item.get("issues", [])
        for box in waybill.vaccine_boxes:
            product = box.product
            entry = product_data[product]
            entry["vehicles"].add(waybill.vehicle_plate)
            entry["routes"].add(waybill.route)
            entry["waybill_ids"].append(waybill.waybill_id)
            if issues:
                entry["has_anomaly"] = True
                relevant = [i for i in issues if i.category in (
                    "temperature_continuity", "temperature_range",
                    "departure_time", "arrival_location",
                )]
                for r_issue in relevant:
                    entry["issues"].append((waybill.waybill_id, waybill.vehicle_plate, r_issue))

    if not product_data:
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("疫苗品种汇总")
    lines.append("=" * 70)

    for product in sorted(product_data.keys()):
        data = product_data[product]
        vehicle_list = "、".join(sorted(data["vehicles"]))
        route_list = "、".join(sorted(data["routes"]))
        waybill_count = len(data["waybill_ids"])

        status_tag = "⚠️ 有异常" if data["has_anomaly"] else "✅ 正常"

        lines.append("")
        lines.append(f"💉 {product}  {status_tag}")
        lines.append(f"   涉及运单：{waybill_count} 单")
        lines.append(f"   承运车辆：{vehicle_list}")
        lines.append(f"   运输线路：{route_list}")

        if data["issues"]:
            by_category = defaultdict(list)
            for wb_id, vehicle, issue in data["issues"]:
                by_category[issue.category].append((wb_id, vehicle, issue))

            for cat, cat_items in by_category.items():
                label = CATEGORY_LABELS.get(cat, cat)
                lines.append(f"   ├── {label}：{len(cat_items)} 条")
                for wb_id, vehicle, issue in cat_items:
                    prefix = "⛔" if issue.severity == "error" else "⚠️"
                    lines.append(f"   │   {prefix} [{wb_id}] {issue.message}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def generate_vehicle_summary(results: list) -> str:
    vehicle_data = defaultdict(lambda: {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "routes": set(),
        "issues": [],
    })

    for item in results:
        waybill = item.get("waybill")
        if not waybill:
            if item.get("load_failed"):
                partial_wb = item.get("waybill")
                if partial_wb:
                    key = partial_wb.vehicle_plate
                else:
                    key = "（未知车辆）"
                entry = vehicle_data[key]
                entry["total"] += 1
                entry["failed"] += 1
                for issue in item.get("issues", []):
                    entry["issues"].append((item["folder_name"], issue))
            continue

        key = waybill.vehicle_plate
        entry = vehicle_data[key]
        entry["total"] += 1
        entry["routes"].add(waybill.route)
        issues = item.get("issues", [])
        if issues:
            entry["failed"] += 1
            for issue in issues:
                entry["issues"].append((waybill.waybill_id, issue))
        else:
            entry["passed"] += 1

    if not vehicle_data:
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("车辆分组小结")
    lines.append("=" * 70)

    for vehicle in sorted(vehicle_data.keys()):
        data = vehicle_data[vehicle]
        route_list = "、".join(sorted(data["routes"]))
        error_count = sum(1 for _, i in data["issues"] if i.severity == "error")
        warning_count = sum(1 for _, i in data["issues"] if i.severity == "warning")

        lines.append("")
        lines.append(f"🚛 {vehicle}")
        lines.append(f"   当天运单：{data['total']} 单 | 通过 {data['passed']} 单 | 异常 {data['failed']} 单")
        lines.append(f"   运输线路：{route_list}")

        if data["issues"]:
            by_category = defaultdict(list)
            for wb_id, issue in data["issues"]:
                by_category[issue.category].append((wb_id, issue))

            summary_parts = []
            for cat, cat_items in by_category.items():
                label = CATEGORY_LABELS.get(cat, cat)
                summary_parts.append(f"{label} {len(cat_items)} 条")
            lines.append(f"   主要问题：{'，'.join(summary_parts)}")

            for cat, cat_items in by_category.items():
                label = CATEGORY_LABELS.get(cat, cat)
                lines.append(f"   ├── {label}：")
                for wb_id, issue in cat_items:
                    prefix = "⛔" if issue.severity == "error" else "⚠️"
                    lines.append(f"   │   {prefix} [{wb_id}] {issue.message}")
        else:
            lines.append(f"   主要问题：无 ✅")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def _find_waybill(waybills: list, waybill_id: str):
    for wb in waybills:
        if wb.waybill_id == waybill_id:
            return wb
    return None
