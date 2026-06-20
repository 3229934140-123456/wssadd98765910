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

CATEGORY_ORDER = [
    "load_failed",
    "temperature_continuity",
    "temperature_range",
    "departure_time",
    "arrival_location",
    "receipt_signature",
    "receipt_box_check",
    "receipt_box_photo",
]


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

        for cat in CATEGORY_ORDER:
            if cat not in category_groups:
                continue
            cat_issues = category_groups[cat]
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
        "waybill_ids": set(),
        "waybill_details": {},
    })

    for item in results:
        waybill = item.get("waybill")
        if not waybill:
            continue
        issues = item.get("issues", [])

        unique_products_in_waybill = set()
        for box in waybill.vaccine_boxes:
            unique_products_in_waybill.add(box.product)

        for product in unique_products_in_waybill:
            entry = product_data[product]
            entry["vehicles"].add(waybill.vehicle_plate)
            entry["routes"].add(waybill.route)
            entry["waybill_ids"].add(waybill.waybill_id)

            if waybill.waybill_id not in entry["waybill_details"]:
                entry["waybill_details"][waybill.waybill_id] = {
                    "vehicle": waybill.vehicle_plate,
                    "route": waybill.route,
                    "issues": [],
                }
                if issues:
                    for r_issue in issues:
                        entry["waybill_details"][waybill.waybill_id]["issues"].append(r_issue)

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

        has_anomaly = any(
            details["issues"]
            for details in data["waybill_details"].values()
        )
        status_tag = "⚠️ 有异常" if has_anomaly else "✅ 正常"

        lines.append("")
        lines.append(f"💉 {product}  {status_tag}")
        lines.append(f"   涉及运单：{waybill_count} 单")
        lines.append(f"   承运车辆：{vehicle_list}")
        lines.append(f"   运输线路：{route_list}")

        for wb_id in sorted(data["waybill_details"].keys()):
            details = data["waybill_details"][wb_id]
            if not details["issues"]:
                lines.append(f"   ├── [{wb_id}] {details['vehicle']} | {details['route']} — 通过 ✅")
                continue

            by_category = defaultdict(list)
            for issue in details["issues"]:
                by_category[issue.category].append(issue)

            issue_parts = []
            for cat in CATEGORY_ORDER:
                if cat not in by_category:
                    continue
                cat_issues = by_category[cat]
                label = CATEGORY_LABELS.get(cat, cat)
                issue_parts.append(f"{label}")

            lines.append(f"   ├── [{wb_id}] {details['vehicle']} | {details['route']} — {'，'.join(issue_parts)}")
            for cat in CATEGORY_ORDER:
                if cat not in by_category:
                    continue
                cat_issues = by_category[cat]
                for issue in cat_issues:
                    prefix = "⛔" if issue.severity == "error" else "⚠️"
                    lines.append(f"   │   {prefix} {issue.message}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def generate_anomaly_type_summary(results: list) -> str:
    category_data = defaultdict(lambda: {
        "waybills": {},
    })

    for item in results:
        waybill = item.get("waybill")
        issues = item.get("issues", [])
        if not issues:
            continue

        if waybill:
            wb_id = waybill.waybill_id
            vehicle = waybill.vehicle_plate
            route = waybill.route
            products = list(set(b.product for b in waybill.vaccine_boxes))
        else:
            wb_id = item.get("folder_name", "未知")
            vehicle = "未知"
            route = "未知"
            products = []

        for issue in issues:
            cat = issue.category
            entry = category_data[cat]
            if wb_id not in entry["waybills"]:
                entry["waybills"][wb_id] = {
                    "vehicle": vehicle,
                    "route": route,
                    "products": products,
                    "issues": [],
                }
            entry["waybills"][wb_id]["issues"].append(issue)

    if not category_data:
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("异常类型汇总")
    lines.append("=" * 70)

    for cat in CATEGORY_ORDER:
        if cat not in category_data:
            continue
        data = category_data[cat]
        label = CATEGORY_LABELS.get(cat, cat)
        wb_count = len(data["waybills"])
        total_issues = sum(len(w["issues"]) for w in data["waybills"].values())

        lines.append("")
        lines.append(f"📋 {label}（涉及 {wb_count} 单，共 {total_issues} 条）")

        for wb_id in sorted(data["waybills"].keys()):
            wb_info = data["waybills"][wb_id]
            product_str = "、".join(wb_info["products"]) if wb_info["products"] else "未知"
            lines.append(f"   ├── [{wb_id}] {wb_info['vehicle']} | {wb_info['route']}")
            lines.append(f"   │   品种：{product_str}")
            for issue in wb_info["issues"]:
                prefix = "⛔" if issue.severity == "error" else "⚠️"
                lines.append(f"   │   {prefix} {issue.message}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def generate_vehicle_summary(results: list) -> str:
    vehicle_data = defaultdict(lambda: {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "load_failed_count": 0,
        "routes": set(),
        "issues": [],
    })

    for item in results:
        waybill = item.get("waybill")
        is_load_failed = item.get("load_failed", False)

        if not waybill:
            if is_load_failed:
                key = "（未知车辆）"
                entry = vehicle_data[key]
                entry["total"] += 1
                entry["failed"] += 1
                entry["load_failed_count"] += 1
                for issue in item.get("issues", []):
                    entry["issues"].append((item.get("folder_name", "未知"), issue))
            continue

        key = waybill.vehicle_plate
        entry = vehicle_data[key]
        entry["total"] += 1
        entry["routes"].add(waybill.route)

        if is_load_failed:
            entry["failed"] += 1
            entry["load_failed_count"] += 1
            for issue in item.get("issues", []):
                entry["issues"].append((waybill.waybill_id, issue))
        else:
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

        load_failed_tag = f"，其中加载失败 {data['load_failed_count']} 单" if data["load_failed_count"] > 0 else ""

        lines.append("")
        lines.append(f"🚛 {vehicle}")
        lines.append(f"   当天运单：{data['total']} 单 | 通过 {data['passed']} 单 | 异常 {data['failed']} 单{load_failed_tag}")
        lines.append(f"   运输线路：{route_list}")

        if data["issues"]:
            by_category = defaultdict(list)
            for wb_id, issue in data["issues"]:
                by_category[issue.category].append((wb_id, issue))

            summary_parts = []
            for cat in CATEGORY_ORDER:
                if cat not in by_category:
                    continue
                cat_items = by_category[cat]
                label = CATEGORY_LABELS.get(cat, cat)
                summary_parts.append(f"{label} {len(cat_items)} 条")
            lines.append(f"   主要问题：{'，'.join(summary_parts)}")

            for cat in CATEGORY_ORDER:
                if cat not in by_category:
                    continue
                cat_items = by_category[cat]
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


def generate_unmatched_summary(results: list) -> str:
    unmatched = [r for r in results if r.get("filter_unmatched", False)]
    if not unmatched:
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("⚠️  补数据区域 — 无法匹配筛选条件")
    lines.append("=" * 70)
    lines.append("")
    lines.append("以下运单因 waybill.json 无法读取，无法判断是否属于当前筛选条件。")
    lines.append("补齐 waybill.json 后，这些运单将按车牌、线路、日期正常归组。")
    lines.append("")

    for item in unmatched:
        folder = item.get("folder_name", "未知")
        error_msg = item.get("error_message", "")
        lines.append(f"   📂 {folder}")
        lines.append(f"      原因：{error_msg}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


RECTIFICATION_BUCKETS = {
    "待补数据": {
        "desc": "数据文件缺失或格式损坏，需重新补数据",
        "categories": {"load_failed"},
    },
    "待司机补签": {
        "desc": "签收资料不全，需司机补签字、补拍照片",
        "categories": {"receipt_signature", "receipt_box_check", "receipt_box_photo"},
    },
    "待质控复核": {
        "desc": "冷链过程异常，需质控复核并填写异常说明",
        "categories": {"temperature_continuity", "temperature_range", "departure_time", "arrival_location"},
    },
}


def generate_rectification_list(results: list) -> str:
    bucket_waybills = defaultdict(lambda: {})

    for item in results:
        waybill = item.get("waybill")
        issues = item.get("issues", [])
        if not issues:
            continue

        if waybill:
            wb_id = waybill.waybill_id
            vehicle = waybill.vehicle_plate
            route = waybill.route
            carrier = waybill.carrier
        else:
            wb_id = item.get("folder_name", "未知")
            vehicle = "未知"
            route = "未知"
            carrier = "未知"

        for issue in issues:
            for bucket_name, bucket_def in RECTIFICATION_BUCKETS.items():
                if issue.category in bucket_def["categories"]:
                    if wb_id not in bucket_waybills[bucket_name]:
                        bucket_waybills[bucket_name][wb_id] = {
                            "vehicle": vehicle,
                            "route": route,
                            "carrier": carrier,
                            "issues": [],
                        }
                    bucket_waybills[bucket_name][wb_id]["issues"].append(issue)

    if not bucket_waybills:
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("整改跟踪清单")
    lines.append("=" * 70)

    for bucket_name in ["待补数据", "待司机补签", "待质控复核"]:
        if bucket_name not in bucket_waybills:
            continue
        bucket_def = RECTIFICATION_BUCKETS[bucket_name]
        waybills = bucket_waybills[bucket_name]
        wb_count = len(waybills)
        total_issues = sum(len(w["issues"]) for w in waybills.values())

        lines.append("")
        lines.append(f"📌 {bucket_name}（{wb_count} 单，共 {total_issues} 条）— {bucket_def['desc']}")

        for wb_id in sorted(waybills.keys()):
            info = waybills[wb_id]
            lines.append(f"   ├── [{wb_id}] {info['vehicle']} | {info['route']} | {info['carrier']}")
            by_category = defaultdict(list)
            for issue in info["issues"]:
                by_category[issue.category].append(issue)
            for cat in CATEGORY_ORDER:
                if cat not in by_category:
                    continue
                cat_issues = by_category[cat]
                label = CATEGORY_LABELS.get(cat, cat)
                lines.append(f"   │   {label}（{len(cat_issues)} 条）：")
                for issue in cat_issues:
                    prefix = "⛔" if issue.severity == "error" else "⚠️"
                    lines.append(f"   │     {prefix} {issue.message}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def generate_liability_summary(results: list) -> str:
    carrier_stats = defaultdict(lambda: {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "load_failed": 0,
        "vehicles": set(),
        "issues": [],
    })
    anomaly_type_count = defaultdict(lambda: defaultdict(int))
    carrier_anomaly_type_count = defaultdict(lambda: defaultdict(int))

    for item in results:
        waybill = item.get("waybill")
        issues = item.get("issues", [])
        is_load_failed = item.get("load_failed", False)

        if waybill:
            carrier = waybill.carrier
            vehicle = waybill.vehicle_plate
        else:
            carrier = "（未知承运商）"
            vehicle = "（未知车辆）"

        entry = carrier_stats[carrier]
        entry["total"] += 1
        entry["vehicles"].add(vehicle)

        if is_load_failed:
            entry["failed"] += 1
            entry["load_failed"] += 1
        else:
            if issues:
                entry["failed"] += 1
            else:
                entry["passed"] += 1

        for issue in issues:
            entry["issues"].append((vehicle, issue))
            label = CATEGORY_LABELS.get(issue.category, issue.category)
            anomaly_type_count[label][carrier] += 1
            carrier_anomaly_type_count[carrier][label] += 1

    if not carrier_stats:
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("追责责任口径小结")
    lines.append("=" * 70)

    lines.append("")
    lines.append("📊 承运商排名（按异常单数量降序）：")
    lines.append("")

    sorted_carriers = sorted(
        carrier_stats.items(),
        key=lambda kv: (kv[1]["failed"], kv[1]["total"]),
        reverse=True,
    )
    rank = 1
    for carrier, data in sorted_carriers:
        vehicles = "、".join(sorted(data["vehicles"]))
        rate = (data["failed"] / data["total"] * 100) if data["total"] > 0 else 0
        rate_tag = f"（异常率 {rate:.0f}%）"

        anomaly_parts = []
        for label, count in sorted(
            carrier_anomaly_type_count[carrier].items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            anomaly_parts.append(f"{label} {count}")
        anomaly_str = "，".join(anomaly_parts) if anomaly_parts else "无"

        load_fail_tag = f"，其中加载失败 {data['load_failed']} 单" if data["load_failed"] > 0 else ""
        lines.append(
            f"   {rank}. {carrier}：{data['total']} 单 | 通过 {data['passed']} | 异常 {data['failed']}{load_fail_tag} {rate_tag}"
        )
        lines.append(f"      车辆：{vehicles}")
        lines.append(f"      主要问题：{anomaly_str}")
        rank += 1

    lines.append("")
    lines.append("📋 异常类型分布（按涉及承运商数降序）：")
    lines.append("")

    sorted_anomaly = sorted(
        anomaly_type_count.items(),
        key=lambda kv: (sum(kv[1].values()), len(kv[1])),
        reverse=True,
    )
    for label, carrier_map in sorted_anomaly:
        total = sum(carrier_map.values())
        carrier_count = len(carrier_map)
        top_carriers = sorted(carrier_map.items(), key=lambda x: x[1], reverse=True)[:3]
        top_str = "，".join(f"{c} {n}条" for c, n in top_carriers)
        lines.append(f"   - {label}：{total} 条，涉及 {carrier_count} 家承运商（{top_str}）")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def _find_waybill(waybills: list, waybill_id: str):
    for wb in waybills:
        if wb.waybill_id == waybill_id:
            return wb
    return None
