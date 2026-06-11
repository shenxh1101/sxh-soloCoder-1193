"""HTML 导出功能"""
from datetime import datetime
from typing import List, Optional

from .models import SongProject, CoverPlan
from .audio_utils import format_duration, format_file_size


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 20px;
        }}
        header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        header .subtitle {{ opacity: 0.9; font-size: 14px; }}
        .stats-bar {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            flex: 1;
            min-width: 180px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .stat-card .label {{ font-size: 13px; color: #888; margin-bottom: 6px; }}
        .stat-card .value {{ font-size: 24px; font-weight: 600; color: #333; }}
        .songs-table {{
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{
            background: #f8f9fa;
            text-align: left;
            padding: 14px 16px;
            font-weight: 600;
            font-size: 13px;
            color: #555;
            border-bottom: 1px solid #eee;
        }}
        td {{
            padding: 14px 16px;
            border-bottom: 1px solid #f0f0f0;
            font-size: 14px;
        }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover {{ background: #fafafa; }}
        .tag {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
            margin-right: 4px;
        }}
        .tag-done {{ background: #d4edda; color: #155724; }}
        .tag-mixing {{ background: #fff3cd; color: #856404; }}
        .tag-tuning {{ background: #f8d7da; color: #721c24; }}
        .song-title {{ font-weight: 600; color: #222; }}
        .original-info {{ color: #888; font-size: 12px; margin-top: 2px; }}
        .file-path {{
            font-family: monospace;
            font-size: 12px;
            color: #666;
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 4px;
        }}
        .mix-count {{
            display: inline-block;
            background: #e7f3ff;
            color: #0066cc;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 12px;
            font-weight: 500;
        }}
        footer {{
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <p class="subtitle">生成时间：{generated_at}</p>
            {subtitle_extra}
        </header>

        <div class="stats-bar">
            <div class="stat-card">
                <div class="label">歌曲数量</div>
                <div class="value">{total_songs} 首</div>
            </div>
            <div class="stat-card">
                <div class="label">总时长</div>
                <div class="value">{total_duration}</div>
            </div>
            <div class="stat-card">
                <div class="label">总大小</div>
                <div class="value">{total_size}</div>
            </div>
            <div class="stat-card">
                <div class="label">混音版本总数</div>
                <div class="value">{total_mixes} 个</div>
            </div>
        </div>

        <div class="songs-table">
            <table>
                <thead>
                    <tr>
                        <th>歌曲</th>
                        <th>标签</th>
                        <th>时长</th>
                        <th>文件大小</th>
                        <th>混音版本</th>
                        <th>干声</th>
                        <th>伴奏</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>

        <footer>
            由 Cover Song Manager 生成
        </footer>
    </div>
</body>
</html>
"""


def _tag_class(tag: str) -> str:
    """获取标签对应的 CSS 类"""
    tag_map = {
        "已完成": "tag-done",
        "混音中": "tag-mixing",
        "待修音": "tag-tuning",
    }
    return tag_map.get(tag, "")


def _generate_row(song: SongProject) -> str:
    """生成表格行 HTML"""
    tags_html = "".join(
        f'<span class="tag {_tag_class(t)}">{t}</span>'
        for t in song.tags
    )

    vocal_status = '<span class="file-path">已配置</span>' if song.vocal_path else '<span style="color:#dc3545;">缺失</span>'
    inst_status = '<span class="file-path">已配置</span>' if song.instrumental_path else '<span style="color:#dc3545;">缺失</span>'

    duration_str = format_duration(song.duration) if song.duration > 0 else "未知"
    size_str = format_file_size(song.file_size) if song.file_size > 0 else "未知"

    return f"""<tr>
        <td>
            <div class="song-title">{song.title}</div>
            <div class="original-info">原唱：{song.original_artist} · 原曲：{song.original_song}</div>
        </td>
        <td>{tags_html}</td>
        <td>{duration_str}</td>
        <td>{size_str}</td>
        <td><span class="mix-count">{len(song.mix_versions)} 个</span></td>
        <td>{vocal_status}</td>
        <td>{inst_status}</td>
    </tr>"""


def export_songs_html(
    songs: List[SongProject],
    output_path: str,
    title: str = "翻唱歌曲项目清单",
    subtitle_extra: str = "",
) -> str:
    """
    导出歌曲列表为 HTML

    Args:
        songs: 歌曲列表
        output_path: 输出文件路径
        title: 页面标题
        subtitle_extra: 额外的副标题内容

    Returns:
        输出文件路径
    """
    total_songs = len(songs)
    total_duration = sum(s.duration for s in songs)
    total_size = sum(s.file_size for s in songs)
    total_mixes = sum(len(s.mix_versions) for s in songs)

    rows = "\n".join(_generate_row(s) for s in songs)

    html = HTML_TEMPLATE.format(
        title=title,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        subtitle_extra=subtitle_extra,
        total_songs=total_songs,
        total_duration=format_duration(total_duration),
        total_size=format_file_size(total_size),
        total_mixes=total_mixes,
        rows=rows,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def export_plan_html(
    plan: CoverPlan,
    songs: List[SongProject],
    output_path: str,
) -> str:
    """
    导出翻唱计划为 HTML

    Args:
        plan: 翻唱计划
        songs: 计划中的歌曲列表
        output_path: 输出文件路径

    Returns:
        输出文件路径
    """
    subtitle = f"<p class='subtitle'>{plan.description}</p>" if plan.description else ""
    title = f"翻唱计划：{plan.name}"
    return export_songs_html(songs, output_path, title=title, subtitle_extra=subtitle)
