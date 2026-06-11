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
)
from .export_html import export_songs_html, export_plan_html


def get_store() -> DataStore:
    """获取数据存储实例"""
    return DataStore()


def _print_song(song: SongProject, verbose: bool = False):
    """打印歌曲信息"""
    tags_str = " ".join(f"[{t}]" for t in song.tags) if song.tags else "无标签"
    click.echo(f"  [{song.id}] {song.title}  {tags_str}")
    if verbose:
        click.echo(f"    原曲：{song.original_artist} - {song.original_song}")
        click.echo(f"    干声：{song.vocal_path or '未设置'}")
        click.echo(f"    伴奏：{song.instrumental_path or '未设置'}")
        click.echo(f"    时长：{format_duration(song.duration)}")
        click.echo(f"    大小：{format_file_size(song.file_size)}")
        click.echo(f"    混音版本：{len(song.mix_versions)} 个")
        if song.mix_versions:
            latest = song.mix_versions[-1]
            click.echo(f"    最新版本：v{latest.version} ({latest.created_at})")
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
    store = get_store()
    song = SongProject.create(
        title=title,
        original_artist=artist,
        original_song=original,
        vocal_path=vocal,
        instrumental_path=instrumental,
        tags=list(tag),
        notes=notes,
    )
    store.add_song(song)
    click.echo(f"✅ 已添加歌曲：{song.title} (ID: {song.id})")


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
    """显示歌曲项目详情"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    _print_song(song, verbose=True)

    if song.mix_versions:
        click.echo("\n  混音版本历史：")
        for mv in song.mix_versions:
            click.echo(f"    v{mv.version}: {mv.output_path}")
            click.echo(f"      时间: {mv.created_at}")
            if mv.notes:
                click.echo(f"      备注: {mv.notes}")


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
@click.option("--vocal-gain", default=0.0, type=float, help="干声增益(dB)")
@click.option("--inst-gain", default=0.0, type=float, help="伴奏增益(dB)")
@click.option("--notes", default="", help="版本备注")
def mix_run(song_id, output_dir, vocal_gain, inst_gain, notes):
    """执行混音并生成新版本"""
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
    out_dir = output_dir or os.path.join(os.path.dirname(song.vocal_path), "mixes")
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
    """查看歌曲的混音版本历史"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not song.mix_versions:
        click.echo(f"歌曲「{song.title}」暂无混音版本")
        return

    click.echo(f"歌曲「{song.title}」的混音版本（共 {len(song.mix_versions)} 个）：")
    for mv in song.mix_versions:
        click.echo(f"  v{mv.version}: {mv.output_path}")
        click.echo(f"    时间: {mv.created_at}")
        click.echo(f"    干声增益: {mv.dry_gain}dB, 伴奏增益: {mv.instrumental_gain}dB")
        if mv.notes:
            click.echo(f"    备注: {mv.notes}")


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

        song_errors = []
        song_warnings = []

        if not song.vocal_path:
            song_errors.append("未设置干声文件路径")
        elif not os.path.exists(song.vocal_path):
            song_errors.append(f"干声文件不存在: {song.vocal_path}")

        if not song.instrumental_path:
            song_errors.append("未设置伴奏文件路径")
        elif not os.path.exists(song.instrumental_path):
            song_errors.append(f"伴奏文件不存在: {song.instrumental_path}")

        if not song.tags:
            song_warnings.append("未设置标签")

        if not song.mix_versions:
            song_warnings.append("暂无混音版本")

        for e in song_errors:
            errors.append((song, e))
        for w in song_warnings:
            warnings.append((song, w))

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
    """统计项目信息"""
    store = get_store()
    songs = store.list_songs()

    if tag:
        songs = [s for s in songs if tag in s.tags]

    if not songs:
        click.echo("暂无数据")
        return

    total_duration = sum(s.duration for s in songs)
    total_size = sum(s.file_size for s in songs)
    total_mixes = sum(len(s.mix_versions) for s in songs)

    click.echo("📊 统计信息")
    click.echo("=" * 40)
    click.echo(f"歌曲总数：{len(songs)} 首")
    click.echo(f"总时长：{format_duration(total_duration)}")
    click.echo(f"总大小：{format_file_size(total_size)}")
    click.echo(f"混音版本总数：{total_mixes} 个")

    tag_stats = {}
    for t in TAGS:
        tag_stats[t] = sum(1 for s in songs if t in s.tags)

    click.echo("\n标签分布：")
    for t, count in tag_stats.items():
        bar = "█" * count
        click.echo(f"  {t}: {count} 首  {bar}")


# ============ HTML 导出 ============

@cli.command("export")
@click.option("--output", "-o", default="songs_report.html", help="输出文件路径")
@click.option("--tag", "-t", default=None, help="按标签筛选后导出")
@click.option("--title", default="翻唱歌曲项目清单", help="报告标题")
def export_cmd(output, tag, title):
    """导出项目清单为 HTML"""
    store = get_store()
    songs = store.list_songs()

    if tag:
        songs = [s for s in songs if tag in s.tags]

    if not songs:
        click.echo("没有可导出的歌曲", err=True)
        sys.exit(1)

    export_songs_html(songs, output, title=title)
    click.echo(f"✅ 已导出到：{output}")


# ============ 翻唱计划 ============

@cli.group()
def plan():
    """翻唱计划管理"""
    pass


@plan.command("create")
@click.option("--name", "-n", required=True, help="计划名称")
@click.option("--description", "-d", default="", help="计划描述")
@click.option("--song", "song_ids", multiple=True, help="关联的歌曲ID（可多次指定）")
def plan_create(name, description, song_ids):
    """创建翻唱计划"""
    store = get_store()
    plan_obj = CoverPlan.create(name=name, description=description, song_ids=list(song_ids))
    store.add_plan(plan_obj)
    click.echo(f"✅ 已创建计划：{plan_obj.name} (ID: {plan_obj.id})")


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
        click.echo(f"  [{p.id}] {p.name} ({song_count} 首歌)")
        if p.description:
            click.echo(f"    {p.description}")


@plan.command("show")
@click.argument("plan_id")
def plan_show(plan_id):
    """显示翻唱计划详情"""
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

    click.echo("歌曲列表：")
    for sid in plan_obj.song_ids:
        song = store.get_song(sid)
        if song:
            _print_song(song)
        else:
            click.echo(f"  [{sid}] <已删除>")


@plan.command("add-song")
@click.argument("plan_id")
@click.argument("song_id")
def plan_add_song(plan_id, song_id):
    """向计划添加歌曲"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"❌ 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    song = store.get_song(song_id)
    if not song:
        click.echo(f"❌ 未找到歌曲 ID: {song_id}", err=True)
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
        click.echo(f"✅ 已从计划「{plan_obj.name}」移除歌曲 ID: {song_id}")
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
    """导出计划的文件清单为 HTML"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"❌ 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    songs = []
    for sid in plan_obj.song_ids:
        song = store.get_song(sid)
        if song:
            songs.append(song)

    if not songs:
        click.echo("计划中没有可导出的歌曲", err=True)
        sys.exit(1)

    output_path = output or f"plan_{plan_obj.id}_report.html"
    export_plan_html(plan_obj, songs, output_path)
    click.echo(f"✅ 已导出计划「{plan_obj.name}」到：{output_path}")


def main():
    """主入口函数"""
    cli()


if __name__ == "__main__":
    main()
