from cold_chain_checker.models import Waybill, Receipt, ValidationIssue


def generate_handover_checklist(waybill: Waybill, receipt: Receipt, issues: list) -> str:
    lines = []
    lines.append(f"运单号：{waybill.waybill_id}")
    lines.append(f"承运车辆：{waybill.vehicle_plate}")
    lines.append(f"线路：{waybill.route}")
    lines.append("-" * 50)
    lines.append("司机补资料待办：")
    lines.append("")

    todo_index = 1
    has_items = False

    if not receipt.signed:
        lines.append(f"  {todo_index}. [签字页] 签收单缺少签字，需补签并拍照上传")
        todo_index += 1
        has_items = True
    elif not receipt.signature_photo:
        lines.append(f"  {todo_index}. [签字页] 签收单已签字但缺签字页照片，需补拍上传")
        todo_index += 1
        has_items = True

    waybill_box_codes = {b.box_code for b in waybill.vaccine_boxes}
    receipt_map = {bc.box_code: bc for bc in receipt.box_checks}

    missing_codes = waybill_box_codes - set(receipt_map.keys())
    for code in sorted(missing_codes):
        lines.append(f"  {todo_index}. [箱码] 箱码 {code} 缺少核对记录，需补拍箱码照片并确认")
        todo_index += 1
        has_items = True

    for bc in receipt.box_checks:
        if not bc.checked:
            lines.append(f"  {todo_index}. [箱码] 箱码 {bc.box_code} 未勾选确认，需确认并补充")
            todo_index += 1
            has_items = True
        if not bc.photo:
            lines.append(f"  {todo_index}. [箱码] 箱码 {bc.box_code} 缺少箱码照片，需补拍上传")
            todo_index += 1
            has_items = True

    temp_issues = [i for i in issues if i.category in ("temperature_continuity", "temperature_range")]
    if temp_issues:
        lines.append(f"  {todo_index}. [异常说明] 温度记录存在异常，需填写异常说明：")
        for ti in temp_issues:
            prefix = "⛔" if ti.severity == "error" else "⚠️"
            lines.append(f"      {prefix} {ti.message}")
        todo_index += 1
        has_items = True

    location_issues = [i for i in issues if i.category == "arrival_location"]
    if location_issues:
        lines.append(f"  {todo_index}. [异常说明] 到达地点存在偏差，需填写异常说明：")
        for li in location_issues:
            lines.append(f"      ⚠️ {li.message}")
        todo_index += 1
        has_items = True

    departure_issues = [i for i in issues if i.category == "departure_time"]
    if departure_issues:
        lines.append(f"  {todo_index}. [异常说明] 发车时间异常，需填写异常说明：")
        for di in departure_issues:
            lines.append(f"      ⛔ {di.message}")
        todo_index += 1
        has_items = True

    if not has_items:
        lines.append("  无需补充资料 ✅")

    return "\n".join(lines)
