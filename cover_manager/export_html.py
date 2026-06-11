"""HTML 导出功能"""
import html
from datetime import datetime
from typing import List, Dict, Any, Optional
import os

from .models import SongProject, CoverPlan
from .audio_utils import (
    format_duration, format_file_size, collect_song_audio_stats,
)


def h(text: Any) -> str:
    """HTML 转义：将任意值转换为安全的 HTML 文本
    防止用户输入的特殊字符（<, >, &, ", '）破坏页面结构
    """
    return html.escape(str(text), quote=True)

BASE_CSS = """
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background: #f5f5f5;
        color: #333;
        padding: 20px;
        line-height: 1.5;
    }
    .container { max-width: 1280px; margin: 0 auto; }
    header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 30px;
        border-radius: 12px;
        margin-bottom: 20px;
    }
    header h1 { font-size: 28px; margin-bottom: 8px; }
    header .subtitle, header .meta { opacity: 0.9; font-size: 14px; margin-top: 6px; }
    .stats-bar {
        display: flex;
        gap: 16px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }
    .stat-card {
        background: white;
        padding: 20px;
        border-radius: 8px;
        flex: 1;
        min-width: 160px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .stat-card .label { font-size: 13px; color: #888; margin-bottom: 6px; }
    .stat-card .value { font-size: 24px; font-weight: 600; color: #333; }
    .stat-card.warn .value { color: #e67e22; }
    .stat-card.good .value { color: #27ae60; }
    .song-card {
        background: white;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .song-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        flex-wrap: wrap;
        gap: 12px;
        margin-bottom: 16px;
        padding-bottom: 14px;
        border-bottom: 1px solid #f0f0f0;
    }
    .song-title {
        font-size: 18px;
        font-weight: 600;
        color: #222;
    }
    .song-original {
        color: #888;
        font-size: 13px;
        margin-top: 4px;
    }
    .tag {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        margin-right: 4px;
        margin-bottom: 4px;
    }
    .tag-done { background: #d4edda; color: #155724; }
    .tag-mixing { background: #fff3cd; color: #856404; }
    .tag-tuning { background: #f8d7da; color: #721c24; }
    .section-title {
        font-size: 14px;
        font-weight: 600;
        color: #555;
        margin: 14px 0 8px;
        padding-left: 8px;
        border-left: 3px solid #667eea;
    }
    .file-list {
        margin: 0;
        padding: 0;
        list-style: none;
    }
    .file-list li {
        padding: 10px 12px;
        border-radius: 6px;
        margin-bottom: 6px;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        flex-wrap: wrap;
        gap: 8px;
        background: #fafafa;
    }
    .file-list li.file-ok { border-left: 3px solid #27ae60; }
    .file-list li.file-missing { border-left: 3px solid #e74c3c; background: #fff5f5; }
    .file-meta {
        font-family: monospace;
        font-size: 12px;
        color: #555;
    }
    .file-label {
        font-weight: 600;
        font-size: 13px;
        margin-bottom: 2px;
    }
    .file-path {
        font-family: monospace;
        font-size: 12px;
        color: #444;
        word-break: break-all;
    }
    .missing-badge {
        background: #e74c3c;
        color: white;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 11px;
        font-weight: 600;
    }
    .ok-badge {
        background: #27ae60;
        color: white;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 11px;
        font-weight: 600;
    }
    .params-table {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 8px;
    }
    .param-item {
        background: #f8f9fa;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 13px;
        border: 1px solid #eee;
    }
    .param-key { color: #888; font-size: 11px; }
    .param-value { font-weight: 600; }
    .no-params { color: #aaa; font-size: 13px; padding: 8px; }
    .song-notes {
        background: #fffbe6;
        padding: 10px 14px;
        border-left: 3px solid #f0c36d;
        border-radius: 4px;
        color: #7a5c00;
        font-size: 13px;
    }
    footer {
        text-align: center;
        color: #999;
        font-size: 12px;
        margin-top: 20px;
        padding: 12px;
    }
    .plan-summary {
        background: white;
        padding: 16px 20px;
        border-radius: 8px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
</style>
"""


def _tag_class(tag: str) -> str:
    tag_map = {"已完成": "tag-done", "混音中": "tag-mixing", "待修音": "tag-tuning"}
    return tag_map.get(tag, "")


def _render_status_badge(exists: bool) -> str:
    return '<span class="ok-badge">存在</span>' if exists else '<span class="missing-badge">缺失</span>'


def _render_file_item(label: str, file_info: Dict[str, Any], extra_label: str = "") -> str:
    """渲染单个文件条目"""
    exists = file_info.get("exists", False)
    path = file_info.get("path", "") or "（未设置）"
    duration = file_info.get("duration", 0.0)
    size = file_info.get("size", 0)

    duration_str = format_duration(duration) if duration > 0 else "未知"
    size_str = format_file_size(size) if size > 0 else "未知"

    cls = "file-ok" if exists else "file-missing"

    extra_html = f" <span style='color:#888'>{h(extra_label)}</span>" if extra_label else ""

    return f"""
    <li class="{cls}">
        <div style="flex: 1; min-width: 280px;">
            <div class="file-label">
                {_render_status_badge(exists)} {h(label)} {extra_html}
            </div>
            <div class="file-path">{h(path)}</div>
        </div>
        <div class="file-meta">
            时长: {h(duration_str)} · 大小: {h(size_str)}
        </div>
    </li>
    """


def _render_params(post_processing_params: Dict[str, Any]) -> str:
    """渲染后期参数块"""
    if not post_processing_params:
        return '<div class="no-params">暂无后期参数</div>'

    items = []
    for k, v in post_processing_params.items():
        items.append(f"""
        <div class="param-item">
            <div class="param-key">{h(k)}</div>
            <div class="param-value">{h(v)}</div>
        </div>
        """)
    return f'<div class="params-table">{"".join(items)}</div>'


def _render_song_card(song: SongProject, show_plan_context: bool = False, filter_type: Optional[str] = None) -> Dict[str, Any]:
    """
    渲染歌曲卡片 HTML

    filter_type: None=全部, "missing"=只显示缺失文件, "exists"=只显示存在文件
    返回 (html_string, stats_dict)
    """
    tags_html = "".join(
        f'<span class="tag {_tag_class(t)}">{h(t)}</span>'
        for t in song.tags
    )
    if not tags_html:
        tags_html = '<span class="tag" style="background:#eee; color:#888;">无标签</span>'

    # 实时计算音频统计
    stats = collect_song_audio_stats(
        vocal_path=song.vocal_path,
        instrumental_path=song.instrumental_path,
        mix_versions=song.mix_versions,
    )

    # 收集需要显示的文件条目
    file_items = []

    # 干声
    vocal_visible = True
    if filter_type == "missing":
        vocal_visible = not stats["vocal"]["exists"]
    elif filter_type == "exists":
        vocal_visible = stats["vocal"]["exists"]
    if vocal_visible:
        file_items.append(("干声 (Vocal)", stats["vocal"], ""))

    # 伴奏
    inst_visible = True
    if filter_type == "missing":
        inst_visible = not stats["instrumental"]["exists"]
    elif filter_type == "exists":
        inst_visible = stats["instrumental"]["exists"]
    if inst_visible:
        file_items.append(("伴奏 (Instrumental)", stats["instrumental"], ""))

    # 混音版本
    mixes_visible = []
    if stats["mixes"]:
        for mv_info in stats["mixes"]:
            mv_visible = True
            if filter_type == "missing":
                mv_visible = not mv_info["exists"]
            elif filter_type == "exists":
                mv_visible = mv_info["exists"]
            if not mv_visible:
                continue

            mv_obj = None
            for m in song.mix_versions:
                if m.version == mv_info["version"]:
                    mv_obj = m
                    break
            version_extra = ""
            if mv_obj:
                version_extra = (
                    f"干声+{mv_obj.dry_gain}dB / 伴奏+{mv_obj.instrumental_gain}dB"
                )
                if mv_obj.notes:
                    version_extra += f" · {mv_obj.notes}"
            mixes_visible.append((f"混音 v{mv_info['version']:03d}", mv_info, version_extra))

    file_items.extend(mixes_visible)

    # 如果没有混音且在非过滤模式，显示"暂无混音版本"提示
    show_no_mix_hint = (not stats["mixes"]) and (filter_type is None)
    show_no_mix_missing = (not stats["mixes"]) and (filter_type == "missing")

    # 渲染文件列表
    files_html = '<ul class="file-list">'

    for label, info, extra in file_items:
        files_html += _render_file_item(label, info, extra_label=extra)

    if show_no_mix_hint:
        files_html += """
        <li class="file-missing">
            <div style="flex:1; min-width:280px;">
                <div class="file-label"><span class="missing-badge">缺失</span> 混音文件</div>
                <div class="file-path">暂无混音版本</div>
            </div>
        </li>
        """
    elif show_no_mix_missing:
        files_html += """
        <li class="file-missing">
            <div style="flex:1; min-width:280px;">
                <div class="file-label"><span class="missing-badge">缺失</span> 混音文件</div>
                <div class="file-path">暂无混音版本</div>
            </div>
        </li>
        """

    files_html += "</ul>"

    # 如果过滤后没有任何文件可显示，返回空
    if not file_items and not show_no_mix_hint and not show_no_mix_missing:
        return {"html": "", "stats": stats, "visible": False}

    # 后期参数
    params_html = _render_params(song.post_processing_params)

    # 备注
    notes_html = ""
    if song.notes:
        notes_html = f'<div class="song-notes" style="margin-top:12px;">[NOTE] {h(song.notes)}</div>'

    updated_at_str = song.updated_at[:19].replace('T', ' ') if song.updated_at else "未知"

    card = f"""
    <div class="song-card">
        <div class="song-header">
            <div>
            <div class="song-title">{h(song.title)}</div>
            <div class="song-original">原唱: {h(song.original_artist)} · 原曲: {h(song.original_song)}</div>
            </div>
            <div>{tags_html}</div>
        </div>
        <div style="font-size:12px; color:#aaa;">ID: {h(song.id)} · 更新于 {h(updated_at_str)}</div>
        <div class="section-title">文件清单</div>
        {files_html}
        <div class="section-title">后期处理参数</div>
        {params_html}
        {notes_html}
    </div>
    """

    return {"html": card, "stats": stats, "visible": True}


def _compute_filtered_stats(songs: List[SongProject], filter_type: Optional[str] = None) -> Dict[str, Any]:
    """
    计算过滤后的统计数据

    filter_type: None=全部, "missing"=只统计缺失文件, "exists"=只统计存在文件
    """
    total_songs = 0
    total_duration = 0.0
    total_size = 0
    total_mixes = 0
    total_files = 0
    missing_files = 0

    for s in songs:
        st = collect_song_audio_stats(
            vocal_path=s.vocal_path,
            instrumental_path=s.instrumental_path,
            mix_versions=s.mix_versions,
        )

        # 检查这首歌是否在过滤后还有可见的文件
        has_visible = False
        song_duration = 0.0
        song_size = 0
        song_files = 0
        song_missing = 0

        # 干声
        vocal_visible = True
        if filter_type == "missing":
            vocal_visible = not st["vocal"]["exists"]
        elif filter_type == "exists":
            vocal_visible = st["vocal"]["exists"]
        if vocal_visible:
            has_visible = True
            song_files += 1
            if st["vocal"]["exists"]:
                song_duration = max(song_duration, st["vocal"]["duration"])
                song_size += st["vocal"]["size"]
            else:
                song_missing += 1

        # 伴奏
        inst_visible = True
        if filter_type == "missing":
            inst_visible = not st["instrumental"]["exists"]
        elif filter_type == "exists":
            inst_visible = st["instrumental"]["exists"]
        if inst_visible:
            has_visible = True
            song_files += 1
            if st["instrumental"]["exists"]:
                song_duration = max(song_duration, st["instrumental"]["duration"])
                song_size += st["instrumental"]["size"]
            else:
                song_missing += 1

        # 混音
        mix_count_visible = 0
        for mv in st["mixes"]:
            mv_visible = True
            if filter_type == "missing":
                mv_visible = not mv["exists"]
            elif filter_type == "exists":
                mv_visible = mv["exists"]
            if mv_visible:
                has_visible = True
                mix_count_visible += 1
                song_files += 1
                if mv["exists"]:
                    song_duration = max(song_duration, mv["duration"])
                    song_size += mv["size"]
                else:
                    song_missing += 1

        # 如果没有混音版本，且在缺失过滤模式，也算有一个缺失项
        if not st["mixes"] and filter_type == "missing":
            has_visible = True
            song_files += 1
            song_missing += 1

        if has_visible:
            total_songs += 1
            total_duration += song_duration
            total_size += song_size
            total_files += song_files
            missing_files += song_missing
            total_mixes += mix_count_visible

    return {
        "total_songs": total_songs,
        "total_duration": total_duration,
        "total_size": total_size,
        "total_mixes": total_mixes,
        "total_files": total_files,
        "missing_files": missing_files,
    }


def _compute_global_stats(songs: List[SongProject]) -> Dict[str, Any]:
    """计算所有歌曲的全局统计（全量）"""
    return _compute_filtered_stats(songs, filter_type=None)


def export_songs_html(
    songs: List[SongProject],
    output_path: str,
    title: str = "翻唱歌曲项目清单",
    subtitle_extra: str = "",
    filter_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    导出歌曲列表为 HTML

    filter_type: None=全部, "missing"=仅缺失文件, "exists"=仅已有文件
    返回统计数据字典，供调用方使用
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filtered_stats = _compute_filtered_stats(songs, filter_type=filter_type)

    # 渲染每首歌（应用文件级过滤）
    cards_html = ""
    visible_count = 0
    for s in songs:
        render_result = _render_song_card(s, filter_type=filter_type)
        if render_result.get("visible", True):
            cards_html += render_result["html"]
            visible_count += 1

    subtitle_html = f'<p class="subtitle">{h(subtitle_extra)}</p>' if subtitle_extra else ""
    missing_cls_1 = "warn" if filtered_stats["missing_files"] > 0 else "good"

    filter_note = ""
    if filter_type == "missing":
        filter_note = '<p class="meta">[FILTER] 仅显示缺失的素材项</p>'
    elif filter_type == "exists":
        filter_note = '<p class="meta">[FILTER] 仅显示已存在的素材项</p>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{h(title)}</title>
    {BASE_CSS}
</head>
<body>
    <div class="container">
        <header>
            <h1>{h(title)}</h1>
            <p class="subtitle">生成时间：{h(generated_at)}</p>
            {subtitle_html}
            {filter_note}
        </header>
        <div class="stats-bar">
            <div class="stat-card good">
                <div class="label">歌曲数量</div>
                <div class="value">{filtered_stats["total_songs"]} 首</div>
            </div>
            <div class="stat-card good">
                <div class="label">总时长（{h("筛选范围内") if filter_type else "所有素材合计"}）</div>
                <div class="value">{format_duration(filtered_stats["total_duration"])}</div>
            </div>
            <div class="stat-card good">
                <div class="label">总占用空间</div>
                <div class="value">{format_file_size(filtered_stats["total_size"])}</div>
            </div>
            <div class="stat-card good">
                <div class="label">混音版本数</div>
                <div class="value">{filtered_stats["total_mixes"]} 个</div>
            </div>
            <div class="stat-card {missing_cls_1}">
                <div class="label">文件项数</div>
                <div class="value">{filtered_stats["total_files"]} 个</div>
            </div>
        </div>
        {cards_html if cards_html else '<div style="background:white; padding:40px; border-radius:8px; text-align:center; color:#888;">暂无匹配的歌曲项目</div>'}
        <footer>由 Cover Song Manager 生成</footer>
    </div>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    result = dict(filtered_stats)
    result["output_path"] = output_path
    result["visible_songs"] = visible_count
    return result


def export_plan_html(
    plan: CoverPlan,
    songs: List[SongProject],
    output_path: str,
    filter_type: Optional[str] = None,
    missing_refs: int = 0,
) -> Dict[str, Any]:
    """
    导出翻唱计划为 HTML（增强版：列出所有相关文件路径、大小、缺失状态）

    filter_type: None=全部, "missing"=仅缺失文件, "exists"=仅已有文件
    missing_refs: 失效引用的歌曲数量
    返回统计数据字典，供调用方使用
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filtered_stats = _compute_filtered_stats(songs, filter_type=filter_type)

    # 渲染每首歌（应用文件级过滤）
    cards_html = ""
    visible_count = 0
    for s in songs:
        render_result = _render_song_card(s, show_plan_context=True, filter_type=filter_type)
        if render_result.get("visible", True):
            cards_html += render_result["html"]
            visible_count += 1

    desc_html = f'<p class="meta">[DESC] {h(plan.description)}</p>' if plan.description else ""
    missing_cls_2 = "warn" if filtered_stats["missing_files"] > 0 else "good"
    missing_color = "#e74c3c" if filtered_stats["missing_files"] > 0 else "#27ae60"

    filter_note = ""
    if filter_type == "missing":
        filter_note = '<p class="meta">[FILTER] 仅显示缺失的素材项</p>'
    elif filter_type == "exists":
        filter_note = '<p class="meta">[FILTER] 仅显示已存在的素材项</p>'

    # 计划的整体素材汇总
    missing_refs_html = ""
    if missing_refs > 0:
        missing_refs_html = f' &nbsp;|&nbsp; <span style="color:#e67e22;">失效引用: {missing_refs} 首</span>'

    plan_summary = f"""
    <div class="plan-summary">
        <div style="font-weight:600; font-size:15px; margin-bottom:10px;">[DIR] 素材整理清单 (ID: {h(plan.id)})</div>
        <div style="font-size:13px; color:#666; line-height:1.8;">
            歌曲数: {len(songs)} 首{missing_refs_html} &nbsp;|&nbsp;
            筛选后歌曲: {filtered_stats["total_songs"]} 首 &nbsp;|&nbsp;
            总时长: {format_duration(filtered_stats["total_duration"])} &nbsp;|&nbsp;
            总大小: {format_file_size(filtered_stats["total_size"])} &nbsp;|&nbsp;
            文件项: <strong style="color:{missing_color};">{filtered_stats["total_files"]} 个</strong>
        </div>
    </div>
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>翻唱计划：{h(plan.name)}</title>
    {BASE_CSS}
</head>
<body>
    <div class="container">
        <header>
            <h1>[MUSIC] 翻唱计划：{h(plan.name)}</h1>
            <p class="subtitle">生成时间：{h(generated_at)}</p>
            {desc_html}
            {filter_note}
        </header>
        {plan_summary}
        <div class="stats-bar">
            <div class="stat-card good">
                <div class="label">歌曲数量</div>
                <div class="value">{filtered_stats["total_songs"]} 首</div>
            </div>
            <div class="stat-card good">
                <div class="label">总时长</div>
                <div class="value">{format_duration(filtered_stats["total_duration"])}</div>
            </div>
            <div class="stat-card good">
                <div class="label">总占用空间</div>
                <div class="value">{format_file_size(filtered_stats["total_size"])}</div>
            </div>
            <div class="stat-card good">
                <div class="label">混音版本数</div>
                <div class="value">{filtered_stats["total_mixes"]} 个</div>
            </div>
            <div class="stat-card {missing_cls_2}">
                <div class="label">文件项数</div>
                <div class="value">{filtered_stats["total_files"]} 个</div>
            </div>
        </div>
        {cards_html if cards_html else '<div style="background:white; padding:40px; border-radius:8px; text-align:center; color:#888;">暂无匹配的歌曲项目</div>'}
        <footer>由 Cover Song Manager 生成</footer>
    </div>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    result = dict(filtered_stats)
    result["output_path"] = output_path
    result["visible_songs"] = visible_count
    result["missing_refs"] = missing_refs
    return result
