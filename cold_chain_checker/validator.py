import math
from datetime import timedelta
from cold_chain_checker.models import (
    Waybill, Trajectory, TemperatureLog, Receipt, ValidationIssue
)


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_departure_time(waybill: Waybill) -> list:
    issues = []
    if waybill.departure_time < waybill.outbound_order_time:
        delta = waybill.outbound_order_time - waybill.departure_time
        minutes = int(delta.total_seconds() / 60)
        issues.append(ValidationIssue(
            waybill_id=waybill.waybill_id,
            category="departure_time",
            severity="error",
            message=f"发车时间 {waybill.departure_time.strftime('%H:%M')} 早于出库单时间 {waybill.outbound_order_time.strftime('%H:%M')}，提前 {minutes} 分钟",
        ))
    return issues


def check_arrival_location(waybill: Waybill, trajectory: Trajectory) -> list:
    issues = []
    if not trajectory.points:
        issues.append(ValidationIssue(
            waybill_id=waybill.waybill_id,
            category="arrival_location",
            severity="error",
            message="无轨迹数据，无法验证到达地点",
        ))
        return issues

    last_point = trajectory.points[-1]
    distance = _haversine_km(
        last_point.latitude, last_point.longitude,
        waybill.vaccination_point.latitude, waybill.vaccination_point.longitude,
    )

    if distance > waybill.vaccination_point.radius_km:
        issues.append(ValidationIssue(
            waybill_id=waybill.waybill_id,
            category="arrival_location",
            severity="warning",
            message=f"到达地点距接种点「{waybill.vaccination_point.name}」{distance:.1f}km，超出 {waybill.vaccination_point.radius_km}km 范围",
        ))
    return issues


def check_temperature_continuity(temperature: TemperatureLog) -> list:
    issues = []
    records = temperature.records
    if len(records) < 2:
        if len(records) == 0:
            issues.append(ValidationIssue(
                waybill_id=temperature.waybill_id,
                category="temperature_continuity",
                severity="error",
                message="无温度记录",
            ))
        return issues

    max_gap_multiplier = 2.5
    expected_interval = timedelta(minutes=temperature.interval_minutes)
    gap_threshold = expected_gap = expected_interval * max_gap_multiplier

    for i in range(1, len(records)):
        gap = records[i].timestamp - records[i - 1].timestamp
        if gap > gap_threshold:
            start_str = records[i - 1].timestamp.strftime("%H:%M")
            end_str = records[i].timestamp.strftime("%H:%M")
            gap_minutes = int(gap.total_seconds() / 60)
            issues.append(ValidationIssue(
                waybill_id=temperature.waybill_id,
                category="temperature_continuity",
                severity="error",
                message=f"缺少 {start_str} 至 {end_str} 温度数据（间隔 {gap_minutes} 分钟，预期 {temperature.interval_minutes} 分钟）",
            ))

    return issues


def _find_gap_indices(records, interval_minutes):
    if len(records) < 2:
        return []
    max_gap_multiplier = 2.5
    expected_interval = timedelta(minutes=interval_minutes)
    gap_threshold = expected_interval * max_gap_multiplier
    indices = []
    for i in range(1, len(records)):
        gap = records[i].timestamp - records[i - 1].timestamp
        if gap > gap_threshold:
            indices.append(i)
    return indices


def _split_by_gaps(records, gap_indices):
    if not gap_indices:
        return [records] if records else []
    segments = []
    prev = 0
    for gi in gap_indices:
        segments.append(records[prev:gi])
        prev = gi
    segments.append(records[prev:])
    return segments


def check_temperature_range(temperature: TemperatureLog) -> list:
    issues = []
    records = temperature.records
    if not records:
        return issues

    gap_indices = _find_gap_indices(records, temperature.interval_minutes)
    segments = _split_by_gaps(records, gap_indices)

    def _add_merged_issue(start_rec, end_rec, direction, peak):
        start_str = start_rec.timestamp.strftime("%H:%M")
        end_str = end_rec.timestamp.strftime("%H:%M")
        if start_rec == end_rec:
            if direction == "above":
                msg = f"{start_str} 温度 {start_rec.temperature}°C 高于上限 {temperature.range_max}°C"
            else:
                msg = f"{start_str} 温度 {start_rec.temperature}°C 低于下限 {temperature.range_min}°C"
        else:
            if direction == "above":
                msg = f"{start_str} 至 {end_str} 温度持续高于上限 {temperature.range_max}°C（最高 {peak}°C）"
            else:
                msg = f"{start_str} 至 {end_str} 温度持续低于下限 {temperature.range_min}°C（最低 {peak}°C）"
        issues.append(ValidationIssue(
            waybill_id=temperature.waybill_id,
            category="temperature_range",
            severity="error",
            message=msg,
        ))

    for segment in segments:
        in_above = False
        in_below = False
        above_start = None
        below_start = None
        above_end = None
        below_end = None
        max_temp = None
        min_temp = None

        for rec in segment:
            if rec.temperature > temperature.range_max:
                if not in_above:
                    in_above = True
                    above_start = rec
                    max_temp = rec.temperature
                else:
                    max_temp = max(max_temp, rec.temperature)
                above_end = rec
            elif rec.temperature < temperature.range_min:
                if not in_below:
                    in_below = True
                    below_start = rec
                    min_temp = rec.temperature
                else:
                    min_temp = min(min_temp, rec.temperature)
                below_end = rec
            else:
                if in_above:
                    _add_merged_issue(above_start, above_end, "above", max_temp)
                    in_above = False
                    above_start = None
                    above_end = None
                    max_temp = None
                if in_below:
                    _add_merged_issue(below_start, below_end, "below", min_temp)
                    in_below = False
                    below_start = None
                    below_end = None
                    min_temp = None

        if in_above:
            _add_merged_issue(above_start, above_end, "above", max_temp)
        if in_below:
            _add_merged_issue(below_start, below_end, "below", min_temp)

    return issues


def check_receipt(waybill: Waybill, receipt: Receipt) -> list:
    issues = []
    if not receipt.signed:
        issues.append(ValidationIssue(
            waybill_id=waybill.waybill_id,
            category="receipt_signature",
            severity="error",
            message="签收单缺少签字",
        ))
    elif not receipt.signature_photo:
        issues.append(ValidationIssue(
            waybill_id=waybill.waybill_id,
            category="receipt_signature",
            severity="warning",
            message="签收单已签字但缺少签字页照片",
        ))

    waybill_box_codes = {b.box_code for b in waybill.vaccine_boxes}
    receipt_box_codes = {bc.box_code for bc in receipt.box_checks}

    missing_boxes = waybill_box_codes - receipt_box_codes
    for code in missing_boxes:
        issues.append(ValidationIssue(
            waybill_id=waybill.waybill_id,
            category="receipt_box_check",
            severity="error",
            message=f"签收清单缺少箱码 {code} 的核对记录",
        ))

    for bc in receipt.box_checks:
        if not bc.checked:
            issues.append(ValidationIssue(
                waybill_id=waybill.waybill_id,
                category="receipt_box_check",
                severity="warning",
                message=f"箱码 {bc.box_code} 未勾选确认",
            ))
        if not bc.photo:
            issues.append(ValidationIssue(
                waybill_id=waybill.waybill_id,
                category="receipt_box_photo",
                severity="warning",
                message=f"箱码 {bc.box_code} 缺少箱码照片",
            ))

    return issues


def validate_waybill(waybill: Waybill, trajectory: Trajectory, temperature: TemperatureLog, receipt: Receipt) -> list:
    issues = []
    issues.extend(check_departure_time(waybill))
    issues.extend(check_arrival_location(waybill, trajectory))
    issues.extend(check_temperature_continuity(temperature))
    issues.extend(check_temperature_range(temperature))
    issues.extend(check_receipt(waybill, receipt))
    return issues
