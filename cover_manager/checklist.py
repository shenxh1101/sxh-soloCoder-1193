"""录音前检查包生成模块：Markdown、HTML、CSV 三份清单"""
import csv
import html as html_module
import os
from datetime import datetime
from typing import List, Dict, Any

from .models import SongProject, CoverPlan
from .audio_utils import collect_song_audio_stats, format_duration, format_file_size


def _determine_next_step(vocal_ok: bool, inst_ok: bool, has_mix: bool) -> str:
    if not vocal_ok and not inst_ok:
        return "补录干声+伴奏"
    elif not vocal_ok:
        return "补录干声"
    elif not inst_ok:
        return "补录伴奏"
    elif not has_mix:
        return "待混音"
    else:
        return "已完成"


def _next_step_sort_key(step: str) -> int:
    order = {"补录干声+伴奏": 0, "补录干声": 1, "补录伴奏": 2, "待混音": 3, "已完成": 4}
    return order.get(step, 99)


def _next_step_badge_color(step: str) -> str:
    colors = {
        "补录干声+伴奏": "#e74c3c",
        "补录干声": "#e67e22",
        "补录伴奏": "#e67e22",
        "待混音": "#3498db",
        "已完成": "#27ae60",
    }
    return colors.get(step, "#888")


def _collect_check_data(songs: List[SongProject]) -> List[Dict[str, Any]]:
    rows = []
    for song in songs:
        st = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
        v_ok = st["vocal"]["exists"]
        i_ok = st["instrumental"]["exists"]
        has_mix = any(m["exists"] for m in st["mixes"])
        mix_count = sum(1 for m in st["mixes"] if m["exists"])
        next_step = _determine_next_step(v_ok, i_ok, has_mix)

        total_dur = st["total_duration"]
        total_size = st["total_size"]

        rows.append({
            "song_id": song.id,
            "title": song.title,
            "artist": song.original_artist,
            "original_song": song.original_song,
            "vocal_ok": v_ok,
            "vocal_path": song.vocal_path,
            "inst_ok": i_ok,
            "inst_path": song.instrumental_path,
            "has_mix": has_mix,
            "mix_count": mix_count,
            "total_duration": total_dur,
            "total_size": total_size,
            "next_step": next_step,
            "tags": ", ".join(song.tags),
            "notes": song.notes,
        })
    return rows


def _h(text: Any) -> str:
    return html_module.escape(str(text), quote=True)


CHECK_CSS = """
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background: #f5f5f5;
        color: #333;
        padding: 20px;
        line-height: 1.5;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 30px;
        border-radius: 12px;
        margin-bottom: 20px;
    }
    header h1 { font-size: 26px; margin-bottom: 8px; }
    header .meta { opacity: 0.9; font-size: 14px; margin-top: 6px; }
    .stats-bar {
        display: flex;
        gap: 12px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }
    .stat-card {
        background: white;
        padding: 16px 20px;
        border-radius: 8px;
        flex: 1;
        min-width: 140px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .stat-card .label { font-size: 12px; color: #888; margin-bottom: 4px; }
    .stat-card .value { font-size: 22px; font-weight: 600; color: #333; }
    .stat-card.warn .value { color: #e67e22; }
    .stat-card.good .value { color: #27ae60; }
    .stat-card.err .value { color: #e74c3c; }
    .stat-card.info .value { color: #3498db; }
    .group-section {
        margin-bottom: 24px;
    }
    .group-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 2px solid #eee;
    }
    .group-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 16px;
        color: white;
        font-size: 13px;
        font-weight: 600;
    }
    .group-count {
        font-size: 14px;
        color: #888;
    }
    .check-card {
        background: white;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 10px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        display: flex;
        align-items: flex-start;
        gap: 20px;
        flex-wrap: wrap;
    }
    .check-card-info {
        flex: 1;
        min-width: 200px;
    }
    .check-card-title {
        font-size: 16px;
        font-weight: 600;
        color: #222;
        margin-bottom: 4px;
    }
    .check-card-subtitle {
        font-size: 12px;
        color: #888;
    }
    .check-card-statuses {
        display: flex;
        gap: 10px;
        align-items: center;
        flex-wrap: wrap;
    }
    .status-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 12px;
        border-radius: 14px;
        font-size: 12px;
        font-weight: 600;
    }
    .status-chip.ok { background: #d4edda; color: #155724; }
    .status-chip.missing { background: #f8d7da; color: #721c24; }
    .next-step-chip {
        padding: 4px 12px;
        border-radius: 14px;
        font-size: 12px;
        font-weight: 600;
        color: white;
    }
    .missing-detail {
        font-size: 12px;
        color: #721c24;
        margin-top: 6px;
        padding-left: 8px;
        border-left: 2px solid #e74c3c;
    }
    footer {
        text-align: center;
        color: #999;
        font-size: 12px;
        margin-top: 20px;
        padding: 12px;
    }
</style>
"""


def generate_checklist_html(
    songs: List[SongProject],
    output_path: str,
    title: str = "录音前检查清单",
    plan_name: str = "",
    plan_desc: str = "",
) -> str:
    rows = _collect_check_data(songs)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ready_count = sum(1 for r in rows if r["vocal_ok"] and r["inst_ok"])
    vocal_missing = sum(1 for r in rows if not r["vocal_ok"])
    inst_missing = sum(1 for r in rows if not r["inst_ok"])
    mix_count = sum(1 for r in rows if r["has_mix"])
    total_dur = sum(r["total_duration"] for r in rows)
    total_size = sum(r["total_size"] for r in rows)
    need_record = sum(1 for r in rows if r["next_step"].startswith("补录"))
    need_mix = sum(1 for r in rows if r["next_step"] == "待混音")
    completed = sum(1 for r in rows if r["next_step"] == "已完成")

    steps = {}
    for r in rows:
        steps.setdefault(r["next_step"], []).append(r)

    desc_html = f'<p class="meta">{_h(plan_desc)}</p>' if plan_desc else ""

    def _status_chip(label: str, ok: bool) -> str:
        cls = "ok" if ok else "missing"
        icon = "&#10003;" if ok else "&#10007;"
        return f'<span class="status-chip {cls}">{icon} {_h(label)}</span>'

    groups_html = ""
    for step in sorted(steps.keys(), key=_next_step_sort_key):
        step_rows = steps[step]
        color = _next_step_badge_color(step)
        group_cards = ""
        for r in step_rows:
            v_chip = _status_chip("干声", r["vocal_ok"])
            i_chip = _status_chip("伴奏", r["inst_ok"])
            m_chip = _status_chip("混音", r["has_mix"])

            missing_parts = []
            if not r["vocal_ok"]:
                missing_parts.append(f"干声: {_h(r['vocal_path'] or '未设置')}")
            if not r["inst_ok"]:
                missing_parts.append(f"伴奏: {_h(r['inst_path'] or '未设置')}")
            missing_html = ""
            if missing_parts:
                missing_html = f'<div class="missing-detail">{" &middot; ".join(missing_parts)}</div>'

            dur = format_duration(r["total_duration"]) if r["total_duration"] > 0 else "未知"
            siz = format_file_size(r["total_size"]) if r["total_size"] > 0 else "未知"

            group_cards += f"""
            <div class="check-card">
                <div class="check-card-info">
                    <div class="check-card-title">{_h(r['title'])}</div>
                    <div class="check-card-subtitle">{_h(r['artist'])} - {_h(r['original_song'])} &nbsp;|&nbsp; ID: {_h(r['song_id'])} &nbsp;|&nbsp; {_h(dur)} / {_h(siz)}</div>
                    {missing_html}
                </div>
                <div class="check-card-statuses">
                    {v_chip}
                    {i_chip}
                    {m_chip}
                    <span class="next-step-chip" style="background:{color};">{_h(step)}</span>
                </div>
            </div>
            """

        groups_html += f"""
        <div class="group-section">
            <div class="group-header">
                <span class="group-badge" style="background:{color};">{_h(step)}</span>
                <span class="group-count">{len(step_rows)} 首</span>
            </div>
            {group_cards}
        </div>
        """

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_h(title)}</title>
    {CHECK_CSS}
</head>
<body>
    <div class="container">
        <header>
            <h1>{_h(title)}</h1>
            <p class="meta">生成时间：{_h(generated_at)}</p>
            {desc_html}
        </header>
        <div class="stats-bar">
            <div class="stat-card good">
                <div class="label">歌曲总数</div>
                <div class="value">{len(rows)} 首</div>
            </div>
            <div class="stat-card err">
                <div class="label">需补录</div>
                <div class="value">{need_record} 首</div>
            </div>
            <div class="stat-card info">
                <div class="label">待混音</div>
                <div class="value">{need_mix} 首</div>
            </div>
            <div class="stat-card good">
                <div class="label">已完成</div>
                <div class="value">{completed} 首</div>
            </div>
            <div class="stat-card warn">
                <div class="label">缺干声</div>
                <div class="value">{vocal_missing} 首</div>
            </div>
            <div class="stat-card warn">
                <div class="label">缺伴奏</div>
                <div class="value">{inst_missing} 首</div>
            </div>
        </div>
        {groups_html}
        <footer>由 Cover Song Manager 录音前检查包生成</footer>
    </div>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    return output_path


def generate_checklist_markdown(
    songs: List[SongProject],
    output_path: str,
    title: str = "录音前检查清单",
    plan_name: str = "",
    plan_desc: str = "",
) -> str:
    rows = _collect_check_data(songs)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ready_count = sum(1 for r in rows if r["vocal_ok"] and r["inst_ok"])
    vocal_missing = sum(1 for r in rows if not r["vocal_ok"])
    inst_missing = sum(1 for r in rows if not r["inst_ok"])
    mix_count = sum(1 for r in rows if r["has_mix"])
    total_dur = sum(r["total_duration"] for r in rows)
    total_size = sum(r["total_size"] for r in rows)

    lines = []
    lines.append(f"# {title}")
    lines.append("")
    if plan_name:
        lines.append(f"**计划名称**: {plan_name}")
        lines.append("")
    if plan_desc:
        lines.append(f"**计划描述**: {plan_desc}")
        lines.append("")
    lines.append(f"**生成时间**: {generated_at}")
    lines.append("")

    lines.append("## 汇总统计")
    lines.append("")
    lines.append(f"- 歌曲总数: {len(rows)} 首")
    lines.append(f"- 素材齐备: {ready_count} 首")
    lines.append(f"- 缺少干声: {vocal_missing} 首")
    lines.append(f"- 缺少伴奏: {inst_missing} 首")
    lines.append(f"- 已有混音: {mix_count} 首")
    lines.append(f"- 总时长: {format_duration(total_dur)}")
    lines.append(f"- 总大小: {format_file_size(total_size)}")
    lines.append("")

    steps = {}
    for r in rows:
        steps.setdefault(r["next_step"], []).append(r)

    lines.append("## 按下一步分组")
    lines.append("")
    for step in sorted(steps.keys(), key=_next_step_sort_key):
        step_rows = steps[step]
        lines.append(f"### {step}（{len(step_rows)} 首）")
        lines.append("")
        for r in step_rows:
            lines.append(f"- [{r['song_id']}] {r['title']}")
        lines.append("")

    lines.append("## 详细清单")
    lines.append("")
    lines.append("| 序号 | 歌曲 | 干声 | 伴奏 | 混音 | 时长 | 大小 | 下一步 |")
    lines.append("|------|------|------|------|------|------|------|--------|")

    for i, r in enumerate(rows, 1):
        v_mark = "[OK]" if r["vocal_ok"] else "[ERR]"
        i_mark = "[OK]" if r["inst_ok"] else "[ERR]"
        m_mark = f"[OK] x{r['mix_count']}" if r["has_mix"] else "[ERR]"
        dur = format_duration(r["total_duration"]) if r["total_duration"] > 0 else "未知"
        siz = format_file_size(r["total_size"]) if r["total_size"] > 0 else "未知"
        lines.append(f"| {i} | {r['title']} | {v_mark} | {i_mark} | {m_mark} | {dur} | {siz} | {r['next_step']} |")

    lines.append("")

    lines.append("## 缺失文件详情")
    lines.append("")
    missing_rows = [r for r in rows if not r["vocal_ok"] or not r["inst_ok"]]
    if not missing_rows:
        lines.append("[OK] 所有歌曲素材齐备！")
    else:
        for r in missing_rows:
            lines.append(f"### [{r['song_id']}] {r['title']}")
            lines.append("")
            if not r["vocal_ok"]:
                lines.append(f"- [ERR] 干声: {r['vocal_path'] or '（未设置）'}")
            if not r["inst_ok"]:
                lines.append(f"- [ERR] 伴奏: {r['inst_path'] or '（未设置）'}")
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def generate_checklist_csv(
    songs: List[SongProject],
    output_path: str,
) -> str:
    rows = _collect_check_data(songs)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "歌曲ID", "歌曲名称", "原唱", "原曲",
            "干声状态", "干声路径",
            "伴奏状态", "伴奏路径",
            "混音版本数", "总时长", "总大小",
            "标签", "下一步", "备注",
        ])

        for r in rows:
            v_status = "齐备" if r["vocal_ok"] else "缺失"
            i_status = "齐备" if r["inst_ok"] else "缺失"
            dur = format_duration(r["total_duration"]) if r["total_duration"] > 0 else "未知"
            siz = format_file_size(r["total_size"]) if r["total_size"] > 0 else "未知"
            writer.writerow([
                r["song_id"], r["title"], r["artist"], r["original_song"],
                v_status, r["vocal_path"],
                i_status, r["inst_path"],
                r["mix_count"], dur, siz,
                r["tags"], r["next_step"], r["notes"],
            ])

    return output_path


def generate_check_package(
    songs: List[SongProject],
    output_dir: str,
    base_name: str = "recording_checklist",
    plan: CoverPlan = None,
) -> Dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)

    md_path = os.path.join(output_dir, f"{base_name}.md")
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    html_path = os.path.join(output_dir, f"{base_name}.html")

    title = "录音前检查清单"
    plan_name = ""
    plan_desc = ""
    if plan:
        title = f"计划「{plan.name}」录音前检查清单"
        plan_name = plan.name
        plan_desc = plan.description

    generate_checklist_markdown(songs, md_path, title=title,
                                plan_name=plan_name, plan_desc=plan_desc)

    generate_checklist_csv(songs, csv_path)

    generate_checklist_html(songs, html_path, title=title,
                            plan_name=plan_name, plan_desc=plan_desc)

    rows = _collect_check_data(songs)
    ready = sum(1 for r in rows if r["vocal_ok"] and r["inst_ok"])
    vocal_missing = sum(1 for r in rows if not r["vocal_ok"])
    inst_missing = sum(1 for r in rows if not r["inst_ok"])

    return {
        "md_path": md_path,
        "csv_path": csv_path,
        "html_path": html_path,
        "total_songs": len(songs),
        "ready_songs": ready,
        "vocal_missing": vocal_missing,
        "inst_missing": inst_missing,
    }
