import argparse
import os
import sys
from datetime import datetime

from cold_chain_checker.models import load_waybill, ValidationIssue
from cold_chain_checker.validator import validate_waybill
from cold_chain_checker.summary import generate_anomaly_summary
from cold_chain_checker.checklist import generate_handover_checklist
from cold_chain_checker.display import format_single_result, format_batch_header, format_batch_footer
from cold_chain_checker.report import export_daily_report


def discover_waybill_dirs(folder: str) -> list:
    dirs = []
    if not os.path.isdir(folder):
        return dirs
    for name in sorted(os.listdir(folder)):
        subdir = os.path.join(folder, name)
        if os.path.isdir(subdir):
            dirs.append(subdir)
    return dirs


def matches_filters(waybill, filters: dict) -> bool:
    if not waybill:
        return True

    if filters.get("vehicle"):
        if filters["vehicle"] not in waybill.vehicle_plate:
            return False

    if filters.get("route"):
        if filters["route"] not in waybill.route:
            return False

    if filters.get("date"):
        target_date = filters["date"]
        wb_date = waybill.departure_time.strftime("%Y-%m-%d")
        if target_date != wb_date:
            return False

    return True


def run_batch_check(folder: str, output_checklist: str = None, output_report: str = None,
                    summary_only: bool = False, filters: dict = None):
    filters = filters or {}
    waybill_dirs = discover_waybill_dirs(folder)
    if not waybill_dirs:
        print(f"未在 {folder} 中找到运单子目录。")
        sys.exit(1)

    total_dirs = len(waybill_dirs)

    results = []
    load_failures = []
    all_waybills = []
    all_issues = {}
    passed = 0
    failed = 0
    skipped = 0

    print(format_batch_header(folder, total_dirs))

    for idx, wdir in enumerate(waybill_dirs, 1):
        folder_name = os.path.basename(wdir)

        load_result = load_waybill(wdir)

        if not load_result.success:
            result_entry = {
                "folder_name": folder_name,
                "load_failed": True,
                "error_message": load_result.error_message,
                "waybill": None,
                "issues": [ValidationIssue(
                    waybill_id=folder_name,
                    category="load_failed",
                    severity="error",
                    message=load_result.error_message,
                )],
            }
            results.append(result_entry)
            load_failures.append({
                "folder_name": folder_name,
                "error_message": load_result.error_message,
            })
            failed += 1

            if not summary_only:
                print(f"  ⚠️ 第 {idx} 单 [{folder_name}] 加载失败：{load_result.error_message}")
            continue

        waybill = load_result.waybill

        if not matches_filters(waybill, filters):
            skipped += 1
            continue

        issues = validate_waybill(
            waybill,
            load_result.trajectory,
            load_result.temperature,
            load_result.receipt,
        )

        result_entry = {
            "folder_name": folder_name,
            "load_failed": False,
            "error_message": "",
            "waybill": waybill,
            "trajectory": load_result.trajectory,
            "temperature": load_result.temperature,
            "receipt": load_result.receipt,
            "issues": issues,
        }
        results.append(result_entry)
        all_waybills.append(waybill)
        all_issues[waybill.waybill_id] = issues

        if not summary_only:
            display_id = waybill.waybill_id
            if folder_name != display_id:
                display_id = f"{waybill.waybill_id}（目录：{folder_name}）"
            print(format_single_result(display_id, issues, idx, total_dirs))

        if issues:
            failed += 1
        else:
            passed += 1

    if summary_only:
        print("  （已启用摘要模式，跳过逐单显示）")

    actual_total = passed + failed
    print(format_batch_footer(actual_total, passed, failed))

    if skipped > 0:
        print(f"  （筛选条件排除了 {skipped} 单）")

    if all_issues or load_failures:
        print(generate_anomaly_summary(all_waybills, all_issues, load_failures))
    else:
        print(generate_anomaly_summary(all_waybills, all_issues, load_failures))

    if output_report:
        report_path = export_daily_report(results, output_report)
        print(f"\n📊 日报已生成：{report_path}")

    if output_checklist:
        checklist_lines = []
        checklist_lines.append("=" * 70)
        checklist_lines.append("交接清单 — 司机补资料待办")
        checklist_lines.append("=" * 70)
        has_any = False

        for result in results:
            if result["load_failed"]:
                has_any = True
                checklist_lines.append("")
                checklist_lines.append(generate_handover_checklist(
                    waybill=None,
                    receipt=None,
                    issues=result["issues"],
                    folder_name=result["folder_name"],
                ))
                checklist_lines.append("")
            else:
                waybill = result["waybill"]
                issues = result["issues"]
                if not issues:
                    continue
                has_any = True
                checklist_lines.append("")
                checklist_lines.append(generate_handover_checklist(
                    waybill=waybill,
                    receipt=result["receipt"],
                    issues=issues,
                    folder_name=result["folder_name"],
                ))
                checklist_lines.append("")

        if not has_any:
            checklist_lines.append("")
            checklist_lines.append("无需补充资料，所有运单均通过校验 ✅")
            checklist_lines.append("")

        checklist_lines.append("=" * 70)

        with open(output_checklist, "w", encoding="utf-8") as f:
            f.write("\n".join(checklist_lines))
        print(f"\n📝 交接清单已生成：{output_checklist}")


def main():
    parser = argparse.ArgumentParser(
        prog="cold-chain-checker",
        description="疫苗冷链轨迹核对器 — 批量校验每日运单的轨迹、温度和签收数据",
    )
    parser.add_argument(
        "folder",
        help="运单数据文件夹路径，每个子目录包含一单数据（waybill.json / trajectory.json / temperature.json / receipt.json）",
    )
    parser.add_argument(
        "-c", "--checklist",
        metavar="FILE",
        help="生成交接清单到指定文件（司机补资料待办列表）",
    )
    parser.add_argument(
        "-r", "--report",
        metavar="FILE",
        help="生成每日校验日报（.csv 或 .xlsx）",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="仅输出异常摘要，不逐单显示详情",
    )
    parser.add_argument(
        "--vehicle",
        metavar="车牌号",
        help="按承运车辆筛选（模糊匹配）",
    )
    parser.add_argument(
        "--route",
        metavar="线路名",
        help="按线路筛选（模糊匹配）",
    )
    parser.add_argument(
        "--date",
        metavar="日期",
        help="按发车日期筛选，格式 YYYY-MM-DD",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"错误：文件夹不存在 — {args.folder}")
        sys.exit(1)

    filters = {}
    if args.vehicle:
        filters["vehicle"] = args.vehicle
    if args.route:
        filters["route"] = args.route
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"错误：日期格式不正确，请使用 YYYY-MM-DD，例如 2026-06-21")
            sys.exit(1)
        filters["date"] = args.date

    run_batch_check(
        args.folder,
        output_checklist=args.checklist,
        output_report=args.report,
        summary_only=args.summary_only,
        filters=filters,
    )


if __name__ == "__main__":
    main()
