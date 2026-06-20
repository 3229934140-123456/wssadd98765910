import argparse
import os
import sys

from cold_chain_checker.models import load_waybill
from cold_chain_checker.validator import validate_waybill
from cold_chain_checker.summary import generate_anomaly_summary
from cold_chain_checker.checklist import generate_handover_checklist
from cold_chain_checker.display import format_single_result, format_batch_header, format_batch_footer


def discover_waybills(folder: str) -> list:
    waybills = []
    if not os.path.isdir(folder):
        return waybills
    for name in sorted(os.listdir(folder)):
        subdir = os.path.join(folder, name)
        if os.path.isdir(subdir):
            required = ["waybill.json", "trajectory.json", "temperature.json", "receipt.json"]
            if all(os.path.isfile(os.path.join(subdir, f)) for f in required):
                waybills.append(subdir)
    return waybills


def run_batch_check(folder: str, output_checklist: str = None):
    waybill_dirs = discover_waybills(folder)
    if not waybill_dirs:
        print(f"未在 {folder} 中找到有效的运单数据。")
        print("每个运单需包含：waybill.json、trajectory.json、temperature.json、receipt.json")
        sys.exit(1)

    print(format_batch_header(folder, len(waybill_dirs)))

    all_waybills = []
    all_issues = {}
    passed = 0
    failed = 0

    for idx, wdir in enumerate(waybill_dirs, 1):
        try:
            waybill, trajectory, temperature, receipt = load_waybill(wdir)
        except Exception as e:
            print(f"  ⛔ 第 {idx} 单 加载失败：{e}")
            failed += 1
            continue

        issues = validate_waybill(waybill, trajectory, temperature, receipt)
        all_waybills.append(waybill)
        all_issues[waybill.waybill_id] = issues

        print(format_single_result(waybill.waybill_id, issues, idx, len(waybill_dirs)))

        if issues:
            failed += 1
        else:
            passed += 1

    print(format_batch_footer(len(waybill_dirs), passed, failed))

    if any(all_issues.values()):
        print(generate_anomaly_summary(all_waybills, all_issues))
    else:
        print(generate_anomaly_summary(all_waybills, all_issues))

    if output_checklist:
        checklist_lines = []
        checklist_lines.append("=" * 70)
        checklist_lines.append("交接清单 — 司机补资料待办")
        checklist_lines.append("=" * 70)
        has_any = False
        for waybill in all_waybills:
            issues = all_issues.get(waybill.waybill_id, [])
            receipt_path = os.path.join(
                folder,
                waybill.waybill_id,
                "receipt.json",
            )
            try:
                _, _, _, receipt = load_waybill(os.path.join(folder, waybill.waybill_id))
            except Exception:
                continue
            if issues:
                has_any = True
                checklist_lines.append("")
                checklist_lines.append(generate_handover_checklist(waybill, receipt, issues))
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
        "--summary-only",
        action="store_true",
        help="仅输出异常摘要，不逐单显示详情",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"错误：文件夹不存在 — {args.folder}")
        sys.exit(1)

    run_batch_check(args.folder, output_checklist=args.checklist)


if __name__ == "__main__":
    main()
