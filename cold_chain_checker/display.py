from cold_chain_checker.models import ValidationIssue


SEVERITY_ICONS = {"error": "⛔", "warning": "⚠️"}
SEVERITY_LABELS = {"error": "错误", "warning": "警告"}


def format_single_result(waybill_id: str, issues: list, index: int, total: int) -> str:
    lines = []
    if not issues:
        lines.append(f"  ✅ 第 {index} 单 [{waybill_id}] 校验通过")
    else:
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        lines.append(f"  ❌ 第 {index} 单 [{waybill_id}] 发现 {error_count} 项错误、{warning_count} 项警告：")
        for issue in issues:
            icon = SEVERITY_ICONS.get(issue.severity, "•")
            lines.append(f"     {icon} {issue.message}")
    return "\n".join(lines)


def format_batch_header(folder: str, total: int) -> str:
    lines = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════╗")
    lines.append("║          疫苗冷链轨迹核对器 — 批量校验报告                    ║")
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    lines.append("")
    lines.append(f"  运单文件夹：{folder}")
    lines.append(f"  运单总数：{total}")
    lines.append(f"  {'─' * 60}")
    return "\n".join(lines)


def format_batch_footer(total: int, passed: int, failed: int) -> str:
    lines = []
    lines.append(f"  {'─' * 60}")
    lines.append(f"  校验完成：共 {total} 单 | 通过 {passed} 单 | 异常 {failed} 单")
    lines.append("")
    return "\n".join(lines)
