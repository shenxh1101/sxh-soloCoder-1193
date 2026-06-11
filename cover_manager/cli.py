"""命令行入口"""
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click

from .models import SongProject, CoverPlan, MixVersion, TAGS
from .storage import DataStore
from .audio_utils import (
    check_ffmpeg, mix_audio, get_audio_info,
    format_duration, format_file_size, generate_output_path, FFmpegError,
    collect_song_audio_stats,
)
from .export_html import export_songs_html, export_plan_html


def get_store() -> DataStore:
    """获取数据存储实例"""
    return DataStore()


def _print_song(song: SongProject, verbose: bool = False):
    """打印歌曲信息（使用实时音频统计）"""
    tags_str = " ".join(f"[{t}]" for t in song.tags) if song.tags else "无标签"
    stats = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)

    click.echo(f"  [{song.id}] {song.title}  {tags_str}")
    if verbose:
        click.echo(f"    原曲：{song.original_artist} - {song.original_song}")
        vocal_info = stats["vocal"]
        inst_info = stats["instrumental"]
        vocal_mark = "✅" if vocal_info["exists"] else "❌"
        inst_mark = "✅" if inst_info["exists"] else "❌"
        click.echo(
            f"    干声：{vocal_mark} {song.vocal_path or '未设置'}"
            f"  ({format_duration(vocal_info['duration'])} / {format_file_size(vocal_info['size'])})"
        )
        click.echo(
            f"    伴奏：{inst_mark} {song.instrumental_path or '未设置'}"
            f"  ({format_duration(inst_info['duration'])} / {format_file_size(inst_info['size'])})"
        )
        click.echo(
            f"    时长：{format_duration(stats['total_duration'])}"
            f"  总大小：{format_file_size(stats['total_size'])}"
        )
        click.echo(f"    混音版本：{len(song.mix_versions)} 个")
        # 后期参数
        if song.post_processing_params:
            pp_str = ", ".join(f"{k}={v}" for k, v in song.post_processing_params.items())
            click.echo(f"    后期参数：{pp_str}")
        else:
            click.echo(f"    后期参数：未设置")
        if song.notes:
            click.echo(f"    备注：{song.notes}")


@click.group()
@click.version_option()
def cli():
    """翻唱歌曲项目管理工具"""
    pass


# ============ 歌曲管理 ============

@cli.group()
def song():
    """歌曲项目管理"""
    pass


@song.command("add")
@click.option("--title", "-t", required=True, help="歌曲标题")
@click.option("--artist", "-a", required=True, help="原唱歌手")
@click.option("--original", "-o", required=True, help="原曲名称")
@click.option("--vocal", "-v", default="", help="干声文件路径")
@click.option("--instrumental", "-i", default="", help="伴奏文件路径")
@click.option("--tag", multiple=True, help="标签（可多次指定）")
@click.option("--notes", "-n", default="", help="备注")
def song_add(title, artist, original, vocal, instrumental, tag, notes):
    """添加新歌曲项目"""
    invalid_tags = [t for t in tag if t not in TAGS]
    if invalid_tags:
        click.echo(f"❌ 无效标签: {', '.join(invalid_tags)}，可用标签: {', '.join(TAGS)}", err=True)
        sys.exit(1)

    store = get_store()
    song_obj = SongProject.create(
        title=title,
        original_artist=artist,
        original_song=original,
        vocal_path=vocal,
        instrumental_path=instrumental,
        tags=list(tag),
        notes=notes,
    )
    store.add_song(song_obj)
    click.echo(f"✅ 已添加歌曲：{song_obj.title} (ID: {song_obj.id})")

    # 提示文件是否存在
    if vocal and not os.path.exists(vocal):
        click.echo(f"   ⚠️  干声路径不存在：{vocal}")
    if instrumental and not os.path.exists(instrumental):
        click.echo(f"   ⚠️  伴奏路径不存在：{instrumental}")


@song.command("list")
@click.option("--tag", "-t", default=None, help="按标签筛选")
@click.option("--search", "-s", default=None, help="搜索关键词")
@click.option("--verbose", "-v", is_flag=True, help="显示详细信息")
def song_list(tag, search, verbose):
    """列出所有歌曲项目"""
    store = get_store()
    songs = store.list_songs()

    if tag:
        songs = [s for s in songs if tag in s.tags]

    if search:
        keyword = search.lower()
        songs = [
            s for s in songs
            if keyword in s.title.lower()
            or keyword in s.original_artist.lower()
            or keyword in s.original_song.lower()
        ]

    if not songs:
        click.echo("暂无歌曲项目")
        return

    click.echo(f"共 {len(songs)} 首歌曲：")
    for s in songs:
        _print_song(s, verbose)


@song.command("show")
@click.argument("song_id")
def song_show(song_id):
    """显示歌曲项目详情（含后期参数、文件明细、混音版本历史）"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    _print_song(song, verbose=True)

    # 后期参数块
    click.echo("\n  后期处理参数：")
    if song.post_processing_params:
        for k, v in song.post_processing_params.items():
            click.echo(f"    {k} = {v}")
    else:
        click.echo("    （未设置，使用 'cover-mgr param set' 命令添加）")

    # 混音版本历史
    if song.mix_versions:
        click.echo("\n  混音版本历史：")
        stats = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
        mv_stats = {m["version"]: m for m in stats["mixes"]}
        for mv in song.mix_versions:
            extra = mv_stats.get(mv.version, {})
            exists = extra.get("exists", False)
            dur = format_duration(extra.get("duration", 0.0))
            size = format_file_size(extra.get("size", 0))
            mark = "✅" if exists else "❌"
            click.echo(f"    v{mv.version:03d} {mark} {mv.output_path}")
            click.echo(f"      时间: {mv.created_at[:19].replace('T', ' ')}")
            click.echo(f"      增益: 干声 {mv.dry_gain}dB / 伴奏 {mv.instrumental_gain}dB")
            click.echo(f"      时长/大小: {dur} / {size}")
            if mv.notes:
                click.echo(f"      备注: {mv.notes}")
    else:
        click.echo("\n  混音版本：暂无（使用 'cover-mgr mix run' 生成）")


@song.command("update")
@click.argument("song_id")
@click.option("--title", default=None, help="歌曲标题")
@click.option("--artist", default=None, help="原唱歌手")
@click.option("--original", default=None, help="原曲名称")
@click.option("--vocal", default=None, help="干声文件路径")
@click.option("--instrumental", default=None, help="伴奏文件路径")
@click.option("--notes", default=None, help="备注")
def song_update(song_id, title, artist, original, vocal, instrumental, notes):
    """更新歌曲项目信息"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if title is not None:
        song.title = title
    if artist is not None:
        song.original_artist = artist
    if original is not None:
        song.original_song = original
    if vocal is not None:
        song.vocal_path = vocal
    if instrumental is not None:
        song.instrumental_path = instrumental
    if notes is not None:
        song.notes = notes

    store.update_song(song)
    click.echo(f"✅ 已更新歌曲：{song.title}")


@song.command("delete")
@click.argument("song_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def song_delete(song_id, yes):
    """删除歌曲项目"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(f"确定要删除歌曲「{song.title}」吗？", abort=True)

    store.delete_song(song_id)
    click.echo(f"✅ 已删除歌曲：{song.title}")


# ============ 后期参数管理 ============

@cli.group()
def param():
    """后期处理参数管理（压缩、混响、EQ 等键值参数）"""
    pass


@param.command("set")
@click.argument("song_id")
@click.argument("key_value", nargs=-1, required=True)
def param_set(song_id, key_value):
    """
    设置后期参数 (可一次设置多个 KEY=VALUE)

    示例:
        cover-mgr param set <ID> 压缩比=4:1 混响=大厅 EQ_高音=+2dB
    """
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    parsed = {}
    errors = []
    for kv in key_value:
        if "=" not in kv:
            errors.append(kv)
            continue
        k, v = kv.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            errors.append(kv)
            continue
        parsed[k] = v

    if errors:
        click.echo(f"❌ 格式错误（应为 KEY=VALUE）：{', '.join(errors)}", err=True)
        sys.exit(1)

    for k, v in parsed.items():
        song.post_processing_params[k] = v
    store.update_song(song)

    summary = ", ".join(f"{k}={v}" for k, v in parsed.items())
    click.echo(f"✅ 已设置后期参数：{summary}")


@param.command("list")
@click.argument("song_id")
def param_list(song_id):
    """查看歌曲的后期参数"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    click.echo(f"歌曲「{song.title}」的后期参数：")
    if not song.post_processing_params:
        click.echo("  （未设置任何参数）")
        return
    for k, v in song.post_processing_params.items():
        click.echo(f"  {k} = {v}")


@param.command("remove")
@click.argument("song_id")
@click.argument("keys", nargs=-1, required=True)
def param_remove(song_id, keys):
    """删除指定的后期参数"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    removed = []
    missing = []
    for k in keys:
        if k in song.post_processing_params:
            del song.post_processing_params[k]
            removed.append(k)
        else:
            missing.append(k)

    store.update_song(song)

    if removed:
        click.echo(f"✅ 已删除参数：{', '.join(removed)}")
    if missing:
        click.echo(f"⚠️  不存在的参数：{', '.join(missing)}")


@param.command("clear")
@click.argument("song_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def param_clear(song_id, yes):
    """清空所有后期参数"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not song.post_processing_params:
        click.echo("没有可清除的后期参数")
        return

    if not yes:
        click.confirm(f"确定清空「{song.title}」的所有后期参数？", abort=True)

    count = len(song.post_processing_params)
    song.post_processing_params.clear()
    store.update_song(song)
    click.echo(f"✅ 已清除 {count} 个后期参数")


# ============ 标签管理 ============

@cli.group()
def tag():
    """标签管理"""
    pass


@tag.command("list")
def tag_list():
    """列出所有可用标签"""
    click.echo("可用标签：")
    for t in TAGS:
        click.echo(f"  - {t}")


@tag.command("add")
@click.argument("song_id")
@click.argument("tag_name")
def tag_add(song_id, tag_name):
    """为歌曲添加标签"""
    if tag_name not in TAGS:
        click.echo(f"❌ 无效标签：{tag_name}，可用标签：{', '.join(TAGS)}", err=True)
        sys.exit(1)

    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if tag_name not in song.tags:
        song.tags.append(tag_name)
        store.update_song(song)
        click.echo(f"✅ 已为「{song.title}」添加标签：{tag_name}")
    else:
        click.echo(f"歌曲「{song.title}」已包含标签：{tag_name}")


@tag.command("remove")
@click.argument("song_id")
@click.argument("tag_name")
def tag_remove(song_id, tag_name):
    """移除歌曲标签"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if tag_name in song.tags:
        song.tags.remove(tag_name)
        store.update_song(song)
        click.echo(f"✅ 已从「{song.title}」移除标签：{tag_name}")
    else:
        click.echo(f"歌曲「{song.title}」不包含标签：{tag_name}")


@tag.command("filter")
@click.argument("tag_name")
def tag_filter(tag_name):
    """按标签筛选歌曲"""
    if tag_name not in TAGS:
        click.echo(f"❌ 无效标签：{tag_name}，可用标签：{', '.join(TAGS)}", err=True)
        sys.exit(1)

    store = get_store()
    songs = store.find_songs_by_tag(tag_name)

    if not songs:
        click.echo(f"标签「{tag_name}」下暂无歌曲")
        return

    click.echo(f"标签「{tag_name}」下共 {len(songs)} 首歌曲：")
    for s in songs:
        _print_song(s)


# ============ 混音功能 ============

@cli.group()
def mix():
    """混音管理"""
    pass


@mix.command("run")
@click.argument("song_id")
@click.option("--output-dir", "-o", default="", help="输出目录")
@click.option("--vocal-gain", default=0.0, type=float, help="干声增益(dB)，默认 0（不调整）")
@click.option("--inst-gain", default=0.0, type=float, help="伴奏增益(dB)，默认 0（不调整）")
@click.option("--notes", default="", help="版本备注")
def mix_run(song_id, output_dir, vocal_gain, inst_gain, notes):
    """执行混音并生成新版本（默认参数即可正常生成）"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not song.vocal_path:
        click.echo("❌ 未设置干声文件路径", err=True)
        sys.exit(1)
    if not song.instrumental_path:
        click.echo("❌ 未设置伴奏文件路径", err=True)
        sys.exit(1)

    if not os.path.exists(song.vocal_path):
        click.echo(f"❌ 干声文件不存在: {song.vocal_path}", err=True)
        sys.exit(1)
    if not os.path.exists(song.instrumental_path):
        click.echo(f"❌ 伴奏文件不存在: {song.instrumental_path}", err=True)
        sys.exit(1)

    if not check_ffmpeg():
        click.echo("❌ 未找到 ffmpeg，请先安装 ffmpeg 并添加到 PATH", err=True)
        sys.exit(1)

    version = len(song.mix_versions) + 1
    if output_dir:
        out_dir = output_dir
    elif song.vocal_path and os.path.dirname(song.vocal_path):
        out_dir = os.path.join(os.path.dirname(song.vocal_path), "mixes")
    else:
        out_dir = os.path.join(os.getcwd(), "mixes")

    output_path = generate_output_path(song.title, version, out_dir)

    click.echo(f"🎵 正在混音：{song.title}")
    click.echo(f"   版本：v{version:03d}")
    click.echo(f"   干声：{song.vocal_path} (增益: {vocal_gain}dB)")
    click.echo(f"   伴奏：{song.instrumental_path} (增益: {inst_gain}dB)")
    click.echo(f"   输出：{output_path}")

    try:
        result_path = mix_audio(
            vocal_path=song.vocal_path,
            instrumental_path=song.instrumental_path,
            output_path=output_path,
            vocal_gain=vocal_gain,
            instrumental_gain=inst_gain,
        )

        duration, file_size = get_audio_info(result_path)
        song.duration = duration
        song.file_size = file_size

        mix_version = MixVersion(
            version=version,
            output_path=result_path,
            created_at=datetime.now().isoformat(),
            dry_gain=vocal_gain,
            instrumental_gain=inst_gain,
            notes=notes,
        )
        song.mix_versions.append(mix_version)
        store.update_song(song)

        click.echo(f"✅ 混音完成！输出文件：{result_path}")
        click.echo(f"   时长：{format_duration(duration)}")
        click.echo(f"   大小：{format_file_size(file_size)}")
    except FFmpegError as e:
        click.echo(f"❌ 混音失败：{e}", err=True)
        sys.exit(1)


@mix.command("list")
@click.argument("song_id")
def mix_list(song_id):
    """查看歌曲的混音版本历史（输出文件、时间、增益参数）"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not song.mix_versions:
        click.echo(f"歌曲「{song.title}」暂无混音版本")
        return

    stats = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
    mv_stats = {m["version"]: m for m in stats["mixes"]}

    click.echo(f"歌曲「{song.title}」的混音版本（共 {len(song.mix_versions)} 个）：")
    for mv in song.mix_versions:
        extra = mv_stats.get(mv.version, {})
        exists = extra.get("exists", False)
        dur = format_duration(extra.get("duration", 0.0))
        size = format_file_size(extra.get("size", 0))
        mark = "✅" if exists else "❌"
        click.echo(f"\n  v{mv.version:03d}  {mark}")
        click.echo(f"    输出文件 : {mv.output_path}")
        click.echo(f"    创建时间 : {mv.created_at[:19].replace('T', ' ')}")
        click.echo(f"    增益参数 : 干声 {mv.dry_gain}dB / 伴奏 {mv.instrumental_gain}dB")
        click.echo(f"    时长/大小: {dur} / {size}")
        if mv.notes:
            click.echo(f"    版本备注 : {mv.notes}")
        if not exists:
            click.echo(f"    ⚠️  提示: 文件不存在或路径已变动")


# ============ 检查功能 ============

@cli.command()
@click.option("--song", "song_id", default=None, help="检查指定歌曲")
def check(song_id):
    """检查项目完整性"""
    store = get_store()

    if song_id:
        songs = [store.get_song(song_id)]
        if not songs[0]:
            click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
            sys.exit(1)
    else:
        songs = store.list_songs()

    errors = []
    warnings = []

    for song in songs:
        if not song:
            continue

        stats = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)

        if not song.vocal_path:
            errors.append((song, "未设置干声文件路径"))
        elif not stats["vocal"]["exists"]:
            errors.append((song, f"干声文件不存在: {song.vocal_path}"))

        if not song.instrumental_path:
            errors.append((song, "未设置伴奏文件路径"))
        elif not stats["instrumental"]["exists"]:
            errors.append((song, f"伴奏文件不存在: {song.instrumental_path}"))

        for m_info in stats["mixes"]:
            if m_info["path"] and not m_info["exists"]:
                warnings.append((song, f"混音文件 v{m_info['version']:03d} 已丢失: {m_info['path']}"))

        if not song.tags:
            warnings.append((song, "未设置标签"))

        if not song.mix_versions:
            warnings.append((song, "暂无混音版本"))

    if not errors and not warnings:
        click.echo("✅ 所有项目检查通过！")
        return

    if errors:
        click.echo(f"❌ 发现 {len(errors)} 个错误：")
        for song, err in errors:
            click.echo(f"  [{song.id}] {song.title}: {err}")

    if warnings:
        click.echo(f"\n⚠️  发现 {len(warnings)} 个警告：")
        for song, warn in warnings:
            click.echo(f"  [{song.id}] {song.title}: {warn}")

    if errors:
        sys.exit(1)


# ============ 统计功能 ============

@cli.command()
@click.option("--tag", "-t", default=None, help="按标签统计")
def stats(tag):
    """统计项目信息（实时计算）"""
    store = get_store()
    songs = store.list_songs()

    if tag:
        songs = [s for s in songs if tag in s.tags]

    if not songs:
        click.echo("暂无数据")
        return

    total_duration = 0.0
    total_size = 0
    total_mixes = 0
    missing_vocal = 0
    missing_instrumental = 0

    for s in songs:
        s_stats = collect_song_audio_stats(s.vocal_path, s.instrumental_path, s.mix_versions)
        total_duration += s_stats["total_duration"]
        total_size += s_stats["total_size"]
        total_mixes += len(s.mix_versions)
        if not s_stats["vocal"]["exists"]:
            missing_vocal += 1
        if not s_stats["instrumental"]["exists"]:
            missing_instrumental += 1

    click.echo("📊 统计信息（基于已配置的音频文件实时计算）")
    click.echo("=" * 50)
    click.echo(f"歌曲总数          ：{len(songs)} 首")
    click.echo(f"总时长            ：{format_duration(total_duration)}")
    click.echo(f"总占用空间        ：{format_file_size(total_size)}")
    click.echo(f"混音版本总数      ：{total_mixes} 个")
    if missing_vocal:
        click.echo(f"缺少干声的歌曲    ：{missing_vocal} 首 ⚠️")
    if missing_instrumental:
        click.echo(f"缺少伴奏的歌曲    ：{missing_instrumental} 首 ⚠️")

    click.echo("\n标签分布：")
    for t in TAGS:
        count = sum(1 for s in songs if t in s.tags)
        bar = "█" * count
        click.echo(f"  {t}: {count} 首  {bar}")


# ============ HTML 导出 ============

@cli.command("export")
@click.option("--output", "-o", default="songs_report.html", help="输出文件路径")
@click.option("--tag", "-t", default=None, help="按标签筛选后导出")
@click.option("--title", default="翻唱歌曲项目清单", help="报告标题")
def export_cmd(output, tag, title):
    """导出项目清单为 HTML（含后期参数和文件明细）"""
    store = get_store()
    songs = store.list_songs()

    if tag:
        songs = [s for s in songs if tag in s.tags]

    if not songs:
        click.echo("没有可导出的歌曲", err=True)
        sys.exit(1)

    export_songs_html(songs, output, title=title)

    stats_result = collect_song_audio_stats.__wrapped__ if hasattr(collect_song_audio_stats, "__wrapped__") else None
    global_size = 0
    global_dur = 0.0
    missing = 0
    for s in songs:
        st = collect_song_audio_stats(s.vocal_path, s.instrumental_path, s.mix_versions)
        global_dur += st["total_duration"]
        global_size += st["total_size"]
        if not st["vocal"]["exists"]:
            missing += 1
        if not st["instrumental"]["exists"]:
            missing += 1
        for m in st["mixes"]:
            if not m["exists"]:
                missing += 1

    click.echo(f"✅ 已导出到：{output}")
    click.echo(f"   歌曲: {len(songs)} 首, 总时长: {format_duration(global_dur)}, "
               f"总大小: {format_file_size(global_size)}, 缺失文件: {missing} 个")


# ============ 翻唱计划 ============

@cli.group()
def plan():
    """翻唱计划管理"""
    pass


@plan.command("create")
@click.option("--name", "-n", required=True, help="计划名称")
@click.option("--description", "-d", default="", help="计划描述")
@click.option("--song", "song_ids", multiple=True, help="关联的歌曲ID（可多次指定；ID必须存在）")
def plan_create(name, description, song_ids):
    """创建翻唱计划（关联的歌曲ID必须存在）"""
    store = get_store()

    valid_ids = []
    invalid_ids = []
    for sid in song_ids:
        if store.get_song(sid):
            valid_ids.append(sid)
        else:
            invalid_ids.append(sid)

    if invalid_ids:
        click.echo(
            f"❌ 创建失败，以下歌曲 ID 不存在：{', '.join(invalid_ids)}",
            err=True,
        )
        click.echo("   请先创建歌曲或检查 ID 是否正确。可使用 'cover-mgr song list' 查看现有 ID。", err=True)
        sys.exit(1)

    plan_obj = CoverPlan.create(name=name, description=description, song_ids=valid_ids)
    store.add_plan(plan_obj)
    click.echo(f"✅ 已创建计划：{plan_obj.name} (ID: {plan_obj.id})")
    if valid_ids:
        click.echo(f"   已关联 {len(valid_ids)} 首歌曲")


@plan.command("list")
def plan_list():
    """列出所有翻唱计划"""
    store = get_store()
    plans = store.list_plans()

    if not plans:
        click.echo("暂无翻唱计划")
        return

    click.echo(f"共 {len(plans)} 个翻唱计划：")
    for p in plans:
        song_count = len(p.song_ids)
        # 统计已删除的引用
        deleted = sum(1 for sid in p.song_ids if not store.get_song(sid))
        deleted_note = f" ({deleted} 首已删除)" if deleted else ""
        click.echo(f"  [{p.id}] {p.name} ({song_count} 首歌{deleted_note})")
        if p.description:
            click.echo(f"    {p.description}")


@plan.command("show")
@click.argument("plan_id")
def plan_show(plan_id):
    """显示翻唱计划详情（含素材汇总）"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"❌ 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    click.echo(f"计划：{plan_obj.name}")
    click.echo(f"ID：{plan_obj.id}")
    if plan_obj.description:
        click.echo(f"描述：{plan_obj.description}")
    click.echo(f"歌曲数量：{len(plan_obj.song_ids)} 首\n")

    songs_data = []
    missing_count = 0
    total_dur = 0.0
    total_size = 0

    for sid in plan_obj.song_ids:
        song = store.get_song(sid)
        if not song:
            click.echo(f"  [{sid}] <歌曲已删除>")
            continue
        songs_data.append(song)
        s_stats = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
        total_dur += s_stats["total_duration"]
        total_size += s_stats["total_size"]
        if not s_stats["vocal"]["exists"]:
            missing_count += 1
        if not s_stats["instrumental"]["exists"]:
            missing_count += 1
        for m in s_stats["mixes"]:
            if not m["exists"]:
                missing_count += 1
        _print_song(song)

    click.echo(f"\n📂 素材汇总：")
    click.echo(f"  有效歌曲        : {len(songs_data)} 首")
    click.echo(f"  总时长          : {format_duration(total_dur)}")
    click.echo(f"  总大小          : {format_file_size(total_size)}")
    if missing_count:
        click.echo(f"  缺失文件数      : {missing_count} 个 ⚠️")


@plan.command("add-song")
@click.argument("plan_id")
@click.argument("song_id")
def plan_add_song(plan_id, song_id):
    """向计划添加歌曲（歌曲ID必须已存在）"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"❌ 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}（请先创建歌曲或检查 ID）", err=True)
        sys.exit(1)

    if song_id not in plan_obj.song_ids:
        plan_obj.song_ids.append(song_id)
        store.update_plan(plan_obj)
        click.echo(f"✅ 已向计划「{plan_obj.name}」添加歌曲：{song.title}")
    else:
        click.echo(f"歌曲「{song.title}」已在计划中")


@plan.command("remove-song")
@click.argument("plan_id")
@click.argument("song_id")
def plan_remove_song(plan_id, song_id):
    """从计划移除歌曲"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"❌ 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    if song_id in plan_obj.song_ids:
        plan_obj.song_ids.remove(song_id)
        store.update_plan(plan_obj)
        song = store.get_song(song_id)
        name = song.title if song else song_id
        click.echo(f"✅ 已从计划「{plan_obj.name}」移除歌曲：{name}")
    else:
        click.echo("该歌曲不在计划中")


@plan.command("delete")
@click.argument("plan_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def plan_delete(plan_id, yes):
    """删除翻唱计划"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"❌ 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(f"确定要删除计划「{plan_obj.name}」吗？", abort=True)

    store.delete_plan(plan_id)
    click.echo(f"✅ 已删除计划：{plan_obj.name}")


@plan.command("export")
@click.argument("plan_id")
@click.option("--output", "-o", default=None, help="输出文件路径")
def plan_export(plan_id, output):
    """导出计划素材清单为 HTML（含所有文件路径、大小、缺失状态）"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"❌ 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    songs = []
    missing_refs = 0
    for sid in plan_obj.song_ids:
        song = store.get_song(sid)
        if song:
            songs.append(song)
        else:
            missing_refs += 1

    if not songs:
        click.echo("计划中没有可导出的歌曲（引用的歌曲已全部删除）", err=True)
        sys.exit(1)

    output_path = output or f"plan_{plan_obj.id}_report.html"
    export_plan_html(plan_obj, songs, output_path)

    # 汇总输出
    global_dur = 0.0
    global_size = 0
    missing = 0
    for s in songs:
        st = collect_song_audio_stats(s.vocal_path, s.instrumental_path, s.mix_versions)
        global_dur += st["total_duration"]
        global_size += st["total_size"]
        if not st["vocal"]["exists"]:
            missing += 1
        if not st["instrumental"]["exists"]:
            missing += 1
        for m in st["mixes"]:
            if not m["exists"]:
                missing += 1

    click.echo(f"✅ 已导出计划「{plan_obj.name}」到：{output_path}")
    click.echo(f"   有效歌曲: {len(songs)} 首" + (f"（{missing_refs} 首引用已删除）" if missing_refs else ""))
    click.echo(f"   总时长: {format_duration(global_dur)}, 总大小: {format_file_size(global_size)}")
    if missing:
        click.echo(f"   缺失文件: {missing} 个 ⚠️")


def main():
    """主入口函数"""
    cli()


if __name__ == "__main__":
    main()
