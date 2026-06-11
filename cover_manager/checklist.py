"""录音前检查包生成模块：Markdown、HTML、CSV 三份清单"""
import csv
import os
from datetime import datetime
from typing import List, Dict, Any

from .models import SongProject, CoverPlan
from .audio_utils import collect_song_audio_stats, format_duration, format_file_size
from .export_html import export_plan_html, export_songs_html


def _determine_next_step(vocal_ok: bool, inst_ok: bool, has_mix: bool) -> str:
    """判断下一步动作"""
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


def _collect_check_data(songs: List[SongProject]) -> List[Dict[str, Any]]:
    """收集每首歌的检查数据"""
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


def generate_checklist_markdown(
    songs: List[SongProject],
    output_path: str,
    title: str = "录音前检查清单",
    plan_name: str = "",
    plan_desc: str = "",
) -> str:
    """生成 Markdown 格式的检查清单"""
    rows = _collect_check_data(songs)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 统计
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

    # 汇总
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

    # 按下一步分组
    lines.append("## 按下一步分组")
    lines.append("")
    steps = {}
    for r in rows:
        step = r["next_step"]
        steps.setdefault(step, []).append(r)

    for step, step_rows in sorted(steps.items()):
        lines.append(f"### {step}（{len(step_rows)} 首）")
        lines.append("")
        for r in step_rows:
            lines.append(f"- [{r['song_id']}] {r['title']}")
        lines.append("")

    # 详细清单
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

    # 缺失文件详情
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
    """生成 CSV 格式的检查清单"""
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
    """
    生成录音前检查包（Markdown + HTML + CSV）

    返回生成的文件路径字典
    """
    os.makedirs(output_dir, exist_ok=True)

    md_path = os.path.join(output_dir, f"{base_name}.md")
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    html_path = os.path.join(output_dir, f"{base_name}.html")

    # 生成 Markdown
    title = "录音前检查清单"
    plan_name = ""
    plan_desc = ""
    if plan:
        title = f"计划「{plan.name}」录音前检查清单"
        plan_name = plan.name
        plan_desc = plan.description

    generate_checklist_markdown(songs, md_path, title=title,
                                plan_name=plan_name, plan_desc=plan_desc)

    # 生成 CSV
    generate_checklist_csv(songs, csv_path)

    # 生成 HTML
    if plan:
        export_plan_html(plan, songs, html_path, filter_type=None)
    else:
        export_songs_html(songs, html_path, title=title)

    # 汇总数据
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
