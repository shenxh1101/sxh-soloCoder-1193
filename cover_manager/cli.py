"""命令行入口"""
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click

# 终端安全符号（避免 Windows GBK 编码下 emoji 输出错误）
SYM_OK = "[OK]"
SYM_ERR = "[ERR]"
SYM_WARN = "[WARN]"
SYM_MUSIC = "[MUSIC]"
SYM_MIC = "[MIC]"
SYM_VOL = "[VOL]"
SYM_STATS = "[STATS]"
SYM_DIR = "[DIR]"
SYM_CELEB = "[YAY]"

E_OK = SYM_OK
E_ERR = SYM_ERR
E_WARN = SYM_WARN

from .models import SongProject, CoverPlan, MixVersion, TAGS
from .storage import DataStore
from .audio_utils import (
    check_ffmpeg, mix_audio, get_audio_info,
    format_duration, format_file_size, generate_output_path, FFmpegError,
    collect_song_audio_stats,
)
from .export_html import export_songs_html, export_plan_html
from .checklist import generate_check_package


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
        vocal_mark = f"{SYM_OK}" if vocal_info["exists"] else f"{SYM_ERR}"
        inst_mark = f"{SYM_OK}" if inst_info["exists"] else f"{SYM_ERR}"
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
        click.echo(f"{E_ERR} 无效标签: {', '.join(invalid_tags)}，可用标签: {', '.join(TAGS)}", err=True)
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
    click.echo(f"{E_OK} 已添加歌曲：{song_obj.title} (ID: {song_obj.id})")

    # 提示文件是否存在
    if vocal and not os.path.exists(vocal):
        click.echo(f"   {E_WARN} 干声路径不存在：{vocal}")
    if instrumental and not os.path.exists(instrumental):
        click.echo(f"   {E_WARN} 伴奏路径不存在：{instrumental}")


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
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
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
            mark = f"{E_OK}" if exists else f"{E_ERR}"
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
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
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
    click.echo(f"{E_OK} 已更新歌曲：{song.title}")


@song.command("delete")
@click.argument("song_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def song_delete(song_id, yes):
    """删除歌曲项目"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(f"确定要删除歌曲「{song.title}」吗？", abort=True)

    store.delete_song(song_id)
    click.echo(f"{E_OK} 已删除歌曲：{song.title}")


@song.command("collect")
@click.argument("song_id")
@click.option("--output-dir", "-o", required=True, help="目标收集目录")
@click.option("--copy-mixes/--no-copy-mixes", default=True, help="是否同时复制混音文件，默认是")
@click.option("--yes", is_flag=True, help="跳过确认")
@click.option("--dry-run", is_flag=True, help="预览模式：只显示将要复制的文件，不实际复制")
@click.option("--zip", "zip_output", is_flag=True, help="打包为 zip 文件")
def song_collect(song_id, output_dir, copy_mixes, yes, dry_run, zip_output):
    """
    收集单首歌曲的素材到指定目录

    按歌曲名创建子文件夹，复制干声、伴奏、混音文件，并生成整理清单
    """
    import shutil
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    # 安全的文件夹名
    safe_chars = set(' -_')
    safe_name = "".join(c for c in song.title if c.isalnum() or c in safe_chars).strip()
    safe_name = safe_name or f"song_{song.id}"
    song_dir = os.path.join(output_dir, f"{safe_name}_{song.id}")

    zip_path = None
    if zip_output:
        zip_path = song_dir + ".zip"

    stats = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)

    # 显示将复制的内容
    mode_label = "[DRY-RUN] 预览" if dry_run else "即将收集"
    if zip_output and not dry_run:
        mode_label = "即将打包"
    click.echo(f"{mode_label}歌曲「{song.title}」的素材：")
    if zip_output:
        click.echo(f"  目标文件: {zip_path}")
    else:
        click.echo(f"  目标目录: {song_dir}")

    files_to_copy = []
    if stats["vocal"]["exists"]:
        files_to_copy.append(("干声", stats["vocal"]["path"]))
    if stats["instrumental"]["exists"]:
        files_to_copy.append(("伴奏", stats["instrumental"]["path"]))
    if copy_mixes:
        for m in stats["mixes"]:
            if m["exists"]:
                files_to_copy.append((f"混音 v{m['version']:03d}", m["path"]))

    missing_files = []
    if not stats["vocal"]["exists"] and song.vocal_path:
        missing_files.append(f"干声: {song.vocal_path}")
    if not stats["instrumental"]["exists"] and song.instrumental_path:
        missing_files.append(f"伴奏: {song.instrumental_path}")

    click.echo(f"  将复制 {len(files_to_copy)} 个文件：")
    total_size = 0
    for label, src in files_to_copy:
        size = os.path.getsize(src)
        total_size += size
        click.echo(f"    - {label}: {os.path.basename(src)} ({format_file_size(size)})")

    if missing_files:
        click.echo(f"\n  {E_WARN}  缺失 {len(missing_files)} 个文件（不会复制）：")
        for m in missing_files:
            click.echo(f"    - {m}")

    if not files_to_copy:
        click.echo(f"\n{E_ERR} 没有可复制的文件", err=True)
        sys.exit(1)

    click.echo(f"\n  合计: {len(files_to_copy)} 个文件, {format_file_size(total_size)}")

    if dry_run:
        click.echo(f"\n{SYM_STATS} 预览模式，未执行实际操作")
        return

    if not yes:
        target_desc = zip_path if zip_output else song_dir
        click.confirm(f"\n确定要复制到 {target_desc} 吗？", abort=True)

    # 如果是 zip 模式，创建临时目录然后打包
    work_dir = song_dir
    temp_dir = None
    if zip_output:
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="cover_collect_")
        work_dir = os.path.join(temp_dir, f"{safe_name}_{song.id}")

    os.makedirs(work_dir, exist_ok=True)

    # 复制文件
    copied = []
    for label, src in files_to_copy:
        dst = os.path.join(work_dir, os.path.basename(src))
        if os.path.abspath(src) == os.path.abspath(dst):
            copied.append((label, src, dst, "跳过（源和目标相同）"))
            continue
        shutil.copy2(src, dst)
        size = format_file_size(os.path.getsize(dst))
        copied.append((label, src, dst, size))

    # 生成整理清单
    manifest_path = os.path.join(work_dir, "MANIFEST.md")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(f"# {song.title} - 素材整理清单\n\n")
        f.write(f"- **原唱**: {song.original_artist}\n")
        f.write(f"- **原曲**: {song.original_song}\n")
        f.write(f"- **歌曲ID**: {song.id}\n")
        f.write(f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        if song.tags:
            f.write(f"- **标签**: {', '.join(song.tags)}\n\n")
        if song.post_processing_params:
            f.write("## 后期参数\n\n")
            for k, v in song.post_processing_params.items():
                f.write(f"- {k}: {v}\n")
            f.write("\n")
        f.write("## 文件清单\n\n")
        f.write("| 类型 | 文件名 | 大小 | 状态 |\n")
        f.write("|------|--------|------|------|\n")
        for label, src, dst, size in copied:
            f.write(f"| {label} | {os.path.basename(dst)} | {size} | {E_OK} |\n")
        for m in missing_files:
            f.write(f"| {m.split(':')[0]} | - | - | {E_ERR} 缺失 |\n")
        if song.notes:
            f.write(f"\n## 备注\n\n{song.notes}\n")

    total_size_val = sum(os.path.getsize(dst) for _, _, dst, _ in copied if os.path.exists(dst))

    import csv as csv_mod
    archive_csv_path = os.path.join(work_dir, "归档索引.csv")
    with open(archive_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv_mod.writer(f)
        writer.writerow(["歌曲ID", "歌曲名称", "素材类型", "原路径", "包内路径", "大小", "状态"])
        for label, src, dst, size in copied:
            arc = f"{safe_name}_{song.id}/{os.path.basename(dst)}"
            writer.writerow([song.id, song.title, label, src, arc, size, "已收入"])
        for m in missing_files:
            m_label = m.split(":")[0]
            m_path = m.split(":", 1)[1].strip() if ":" in m else ""
            writer.writerow([song.id, song.title, m_label, m_path, "", "", "缺失"])

    # 如果是 zip 模式，打包并清理临时目录
    final_output = song_dir
    if zip_output:
        import zipfile
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for label, src, dst, size in copied:
                arcname = os.path.relpath(dst, temp_dir)
                zf.write(dst, arcname)
            zf.write(manifest_path, os.path.relpath(manifest_path, temp_dir))
            zf.write(archive_csv_path, os.path.relpath(archive_csv_path, temp_dir))
        final_output = zip_path
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

    click.echo(f"\n{E_OK} 收集完成！")
    if zip_output:
        click.echo(f"   压缩包: {zip_path}")
        click.echo(f"   压缩包大小: {format_file_size(os.path.getsize(zip_path))}")
    else:
        click.echo(f"   目录: {song_dir}")
    click.echo(f"   复制了 {len(copied)} 个文件，总计 {format_file_size(total_size_val)}")
    click.echo(f"   整理清单: MANIFEST.md")


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
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
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
        click.echo(f"{E_ERR} 格式错误（应为 KEY=VALUE）：{', '.join(errors)}", err=True)
        sys.exit(1)

    for k, v in parsed.items():
        song.post_processing_params[k] = v
    store.update_song(song)

    summary = ", ".join(f"{k}={v}" for k, v in parsed.items())
    click.echo(f"{E_OK} 已设置后期参数：{summary}")


@param.command("list")
@click.argument("song_id")
def param_list(song_id):
    """查看歌曲的后期参数"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
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
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
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
        click.echo(f"{E_OK} 已删除参数：{', '.join(removed)}")
    if missing:
        click.echo(f"{E_WARN}  不存在的参数：{', '.join(missing)}")


@param.command("clear")
@click.argument("song_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def param_clear(song_id, yes):
    """清空所有后期参数"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not song.post_processing_params:
        click.echo("没有可清除的后期参数")
        return

    if not yes:
        click.confirm(f"确定清空「{song.title}」的所有后期参数？", abort=True)

    count = len(song.post_processing_params)
    song.post_processing_params.clear()
    store.update_song(song)
    click.echo(f"{E_OK} 已清除 {count} 个后期参数")


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
        click.echo(f"{E_ERR} 无效标签：{tag_name}，可用标签：{', '.join(TAGS)}", err=True)
        sys.exit(1)

    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if tag_name not in song.tags:
        song.tags.append(tag_name)
        store.update_song(song)
        click.echo(f"{E_OK} 已为「{song.title}」添加标签：{tag_name}")
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
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if tag_name in song.tags:
        song.tags.remove(tag_name)
        store.update_song(song)
        click.echo(f"{E_OK} 已从「{song.title}」移除标签：{tag_name}")
    else:
        click.echo(f"歌曲「{song.title}」不包含标签：{tag_name}")


@tag.command("filter")
@click.argument("tag_name")
def tag_filter(tag_name):
    """按标签筛选歌曲"""
    if tag_name not in TAGS:
        click.echo(f"{E_ERR} 无效标签：{tag_name}，可用标签：{', '.join(TAGS)}", err=True)
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
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
        sys.exit(1)

    if not song.vocal_path:
        click.echo(f"{E_ERR} 未设置干声文件路径", err=True)
        sys.exit(1)
    if not song.instrumental_path:
        click.echo(f"{E_ERR} 未设置伴奏文件路径", err=True)
        sys.exit(1)

    if not os.path.exists(song.vocal_path):
        click.echo(f"{E_ERR} 干声文件不存在: {song.vocal_path}", err=True)
        sys.exit(1)
    if not os.path.exists(song.instrumental_path):
        click.echo(f"{E_ERR} 伴奏文件不存在: {song.instrumental_path}", err=True)
        sys.exit(1)

    if not check_ffmpeg():
        click.echo(f"{E_ERR} 未找到 ffmpeg，请先安装 ffmpeg 并添加到 PATH", err=True)
        sys.exit(1)

    version = len(song.mix_versions) + 1
    if output_dir:
        out_dir = output_dir
    elif song.vocal_path and os.path.dirname(song.vocal_path):
        out_dir = os.path.join(os.path.dirname(song.vocal_path), "mixes")
    else:
        out_dir = os.path.join(os.getcwd(), "mixes")

    output_path = generate_output_path(song.title, version, out_dir)

    click.echo(f"{SYM_MUSIC} 正在混音：{song.title}")
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

        click.echo(f"{E_OK} 混音完成！输出文件：{result_path}")
        click.echo(f"   时长：{format_duration(duration)}")
        click.echo(f"   大小：{format_file_size(file_size)}")
    except FFmpegError as e:
        click.echo(f"{E_ERR} 混音失败：{e}", err=True)
        sys.exit(1)


@mix.command("list")
@click.argument("song_id")
def mix_list(song_id):
    """查看歌曲的混音版本历史（输出文件、时间、增益参数）"""
    store = get_store()
    song = store.get_song(song_id)
    if not song:
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
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
        mark = f"{E_OK}" if exists else f"{E_ERR}"
        click.echo(f"\n  v{mv.version:03d}  {mark}")
        click.echo(f"    输出文件 : {mv.output_path}")
        click.echo(f"    创建时间 : {mv.created_at[:19].replace('T', ' ')}")
        click.echo(f"    增益参数 : 干声 {mv.dry_gain}dB / 伴奏 {mv.instrumental_gain}dB")
        click.echo(f"    时长/大小: {dur} / {size}")
        if mv.notes:
            click.echo(f"    版本备注 : {mv.notes}")
        if not exists:
            click.echo(f"    {E_WARN}  提示: 文件不存在或路径已变动")


# ============ 检查功能 ============

@cli.command()
@click.option("--song", "song_id", default=None, help="检查指定歌曲")
def check(song_id):
    """检查项目完整性"""
    store = get_store()

    if song_id:
        songs = [store.get_song(song_id)]
        if not songs[0]:
            click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}", err=True)
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
        click.echo(f"{E_OK} 所有项目检查通过！")
        return

    if errors:
        click.echo(f"{E_ERR} 发现 {len(errors)} 个错误：")
        for song, err in errors:
            click.echo(f"  [{song.id}] {song.title}: {err}")

    if warnings:
        click.echo(f"\n{E_WARN}  发现 {len(warnings)} 个警告：")
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

    click.echo(f"{SYM_STATS} 统计信息（基于已配置的音频文件实时计算）")
    click.echo("=" * 50)
    click.echo(f"歌曲总数          ：{len(songs)} 首")
    click.echo(f"总时长            ：{format_duration(total_duration)}")
    click.echo(f"总占用空间        ：{format_file_size(total_size)}")
    click.echo(f"混音版本总数      ：{total_mixes} 个")
    if missing_vocal:
        click.echo(f"缺少干声的歌曲    ：{missing_vocal} 首 {E_WARN}")
    if missing_instrumental:
        click.echo(f"缺少伴奏的歌曲    ：{missing_instrumental} 首 {E_WARN}")

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
@click.option("--missing-only", is_flag=True, help="只导出含有缺失文件的歌曲")
@click.option("--exists-only", is_flag=True, help="只导出含有已存在文件的歌曲")
def export_cmd(output, tag, title, missing_only, exists_only):
    """
    导出项目清单为 HTML（含后期参数和文件明细，支持按存在性过滤）

    示例：
        cover-mgr export --missing-only   # 只看缺什么
        cover-mgr export --exists-only    # 只看已有什么
    """
    store = get_store()
    songs = store.list_songs()

    if missing_only and exists_only:
        click.echo(f"{E_ERR} --missing-only 和 --exists-only 不能同时使用", err=True)
        sys.exit(1)

    if tag:
        songs = [s for s in songs if tag in s.tags]

    if not songs:
        click.echo("没有可导出的歌曲", err=True)
        sys.exit(1)

    filter_type = None
    if missing_only:
        filter_type = "missing"
    elif exists_only:
        filter_type = "exists"

    result = export_songs_html(songs, output, title=title, filter_type=filter_type)

    filter_msg = ""
    if filter_type == "missing":
        filter_msg = "（仅含缺失文件的歌曲）"
    elif filter_type == "exists":
        filter_msg = "（仅含已存在文件的歌曲）"

    click.echo(f"{E_OK} 已导出到：{output} {filter_msg}")
    click.echo(f"   筛选后歌曲: {result['total_songs']} 首, 总时长: {format_duration(result['total_duration'])}, "
               f"总大小: {format_file_size(result['total_size'])}, 文件项: {result['total_files']} 个")
    if filter_type == "missing":
        click.echo(f"   缺失文件: {result['missing_files']} 个 {E_WARN}")
    elif filter_type == "exists":
        click.echo(f"   存在文件: {result['total_files'] - result['missing_files']} 个 {E_OK}")


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
    """创建翻唱计划（关联的歌曲ID必须存在，自动去重）"""
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
            f"{E_ERR} 创建失败，以下歌曲 ID 不存在：{', '.join(invalid_ids)}",
            err=True,
        )
        click.echo("   请先创建歌曲或检查 ID 是否正确。可使用 'cover-mgr song list' 查看现有 ID。", err=True)
        sys.exit(1)

    plan_obj = CoverPlan.create(name=name, description=description, song_ids=valid_ids)
    store.add_plan(plan_obj)
    original_count = len(valid_ids)
    final_count = len(plan_obj.song_ids)
    dups = original_count - final_count

    click.echo(f"{E_OK} 已创建计划：{plan_obj.name} (ID: {plan_obj.id})")
    if final_count:
        dup_msg = f"（自动去重，移除 {dups} 个重复）" if dups else ""
        click.echo(f"   已关联 {final_count} 首歌曲 {dup_msg}")


@plan.command("list")
def plan_list():
    """列出所有翻唱计划（自动去重统计）"""
    store = get_store()
    plans = store.list_plans()

    if not plans:
        click.echo("暂无翻唱计划")
        return

    click.echo(f"共 {len(plans)} 个翻唱计划：")
    for p in plans:
        # 先确保去重
        p.set_song_ids(p.song_ids)
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
    """显示翻唱计划详情（含素材汇总，自动去重）"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    # 先确保去重
    final_count = plan_obj.set_song_ids(plan_obj.song_ids)
    store.update_plan(plan_obj)

    click.echo(f"计划：{plan_obj.name}")
    click.echo(f"ID：{plan_obj.id}")
    if plan_obj.description:
        click.echo(f"描述：{plan_obj.description}")

    invalid_ids = [sid for sid in plan_obj.song_ids if not store.get_song(sid)]
    valid_total = final_count - len(invalid_ids)
    click.echo(f"歌曲数量：{valid_total} 首" + (f"（另有 {len(invalid_ids)} 个失效引用）" if invalid_ids else ""))
    if invalid_ids:
        click.echo(f"  失效引用 ID: {', '.join(invalid_ids)}（使用 'plan clean' 清理）")
    click.echo("")

    songs_data = []
    missing_count = 0
    total_dur = 0.0
    total_size = 0
    vocal_missing = 0
    instrumental_missing = 0
    mix_missing = 0

    for sid in plan_obj.song_ids:
        song = store.get_song(sid)
        if not song:
            click.echo(f"  [{sid}] <歌曲已删除 - 失效引用>")
            continue
        songs_data.append(song)
        s_stats = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
        total_dur += s_stats["total_duration"]
        total_size += s_stats["total_size"]

        v_miss = not s_stats["vocal"]["exists"]
        i_miss = not s_stats["instrumental"]["exists"]
        m_miss = any(not m["exists"] for m in s_stats["mixes"])

        if v_miss:
            vocal_missing += 1
        if i_miss:
            instrumental_missing += 1
        if m_miss:
            mix_missing += len([m for m in s_stats["mixes"] if not m["exists"]])

        missing_count = vocal_missing + instrumental_missing + mix_missing

        # 每首歌的状态图标
        status_parts = []
        status_parts.append(f"{SYM_MIC}{E_OK}" if not v_miss else f"{SYM_MIC}{E_ERR}")
        status_parts.append(f"{SYM_MUSIC}{E_OK}" if not i_miss else f"{SYM_MUSIC}{E_ERR}")
        if song.mix_versions:
            m_total = len(song.mix_versions)
            m_ok = m_total - len([m for m in s_stats["mixes"] if not m["exists"]])
            status_parts.append(f"{SYM_VOL} {m_ok}/{m_total}")
        else:
            status_parts.append(f"{SYM_VOL} 0")

        status_str = " ".join(status_parts)
        click.echo(f"  {status_str}  [{song.id}] {song.title}")

    click.echo(f"\n{SYM_DIR} 素材汇总：")
    click.echo(f"  有效歌曲        : {len(songs_data)} 首")
    click.echo(f"  总时长          : {format_duration(total_dur)}")
    click.echo(f"  总大小          : {format_file_size(total_size)}")
    if missing_count:
        click.echo(f"  缺失文件数      : {missing_count} 个 {E_WARN}")
        click.echo(f"    - 缺少干声    : {vocal_missing} 首")
        click.echo(f"    - 缺少伴奏    : {instrumental_missing} 首")
        click.echo(f"    - 缺少混音    : {mix_missing} 个文件")
    else:
        click.echo(f"  素材完整性      : {E_OK} 全部齐备")


@plan.command("status")
@click.argument("plan_id")
def plan_status(plan_id):
    """终端查看计划的素材准备状态（录音前检查专用）"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    plan_obj.set_song_ids(plan_obj.song_ids)

    # 统计失效引用
    invalid_ids = [sid for sid in plan_obj.song_ids if not store.get_song(sid)]
    valid_count = len(plan_obj.song_ids) - len(invalid_ids)

    click.echo(f"\n{SYM_MIC}  计划「{plan_obj.name}」素材准备状态")
    click.echo("=" * 60)
    if invalid_ids:
        click.echo(f"  {E_WARN}  有 {len(invalid_ids)} 首歌曲引用已失效，使用 'plan clean' 可清理")
        click.echo(f"  失效引用 ID: {', '.join(invalid_ids)}")
        click.echo("")

    ready_count = 0
    partial_count = 0
    not_ready_count = 0

    for sid in plan_obj.song_ids:
        song = store.get_song(sid)
        if not song:
            continue
        st = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
        v_ok = st["vocal"]["exists"]
        i_ok = st["instrumental"]["exists"]
        has_mix = len(st["mixes"]) > 0 and any(m["exists"] for m in st["mixes"])

        # 状态判定
        if v_ok and i_ok:
            status = f"{E_OK} 素材齐备"
            ready_count += 1
        elif v_ok or i_ok:
            status = f"{E_WARN}  部分缺失"
            partial_count += 1
        else:
            status = f"{E_ERR} 完全未准备"
            not_ready_count += 1

        parts = []
        parts.append(f"{SYM_MIC}{E_OK}" if v_ok else f"{SYM_MIC}{E_ERR}")
        parts.append(f"{SYM_MUSIC}{E_OK}" if i_ok else f"{SYM_MUSIC}{E_ERR}")
        parts.append(f"{SYM_VOL}{E_OK}" if has_mix else f"{SYM_VOL}{E_ERR}")

        duration = format_duration(st["total_duration"]) if st["total_duration"] > 0 else "未知"
        size = format_file_size(st["total_size"]) if st["total_size"] > 0 else "未知"

        click.echo(f"  {status}  [{song.id}] {song.title}")
        click.echo(f"     {' '.join(parts)}  时长:{duration}  大小:{size}")

    click.echo("\n" + "=" * 60)
    click.echo(f"{E_OK} 齐备: {ready_count}  |  {E_WARN}  部分: {partial_count}  |  {E_ERR} 未准备: {not_ready_count}")
    total = valid_count
    if total > 0 and ready_count == total:
        click.echo(f"{SYM_CELEB} 全部素材已准备完成！")
    else:
        click.echo(f"{SYM_STATS} 还差 {total - ready_count} 首歌素材完全齐备")
    if invalid_ids:
        click.echo(f"{E_WARN}  失效引用: {len(invalid_ids)} 首（使用 'plan clean' 清理）")


@plan.command("add-song")
@click.argument("plan_id")
@click.argument("song_id")
def plan_add_song(plan_id, song_id):
    """向计划添加歌曲（ID必须已存在，自动去重）"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    song = store.get_song(song_id)
    if not song:
        click.echo(f"{E_ERR} 未找到歌曲 ID: {song_id}（请先创建歌曲或检查 ID）", err=True)
        sys.exit(1)

    added = plan_obj.add_song_id(song_id)
    if added:
        store.update_plan(plan_obj)
        click.echo(f"{E_OK} 已向计划「{plan_obj.name}」添加歌曲：{song.title}")
    else:
        click.echo(f"{SYM_STATS} 歌曲「{song.title}」已在计划中，跳过重复添加")


@plan.command("remove-song")
@click.argument("plan_id")
@click.argument("song_id")
def plan_remove_song(plan_id, song_id):
    """从计划移除歌曲"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    removed = plan_obj.remove_song_id(song_id)
    if removed:
        store.update_plan(plan_obj)
        song = store.get_song(song_id)
        name = song.title if song else song_id
        click.echo(f"{E_OK} 已从计划「{plan_obj.name}」移除歌曲：{name}")
    else:
        click.echo("该歌曲不在计划中")


@plan.command("clean")
@click.argument("plan_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def plan_clean(plan_id, yes):
    """清理计划中已失效的歌曲引用（歌曲已删除的）"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    # 先去重
    plan_obj.set_song_ids(plan_obj.song_ids)

    # 找出失效引用
    invalid_ids = []
    valid_ids = []
    for sid in plan_obj.song_ids:
        if store.get_song(sid):
            valid_ids.append(sid)
        else:
            invalid_ids.append(sid)

    if not invalid_ids:
        click.echo(f"{E_OK} 计划「{plan_obj.name}」没有失效引用")
        return

    click.echo(f"计划「{plan_obj.name}」中有 {len(invalid_ids)} 个失效引用：")
    for sid in invalid_ids:
        click.echo(f"  - {sid}")

    if not yes:
        click.confirm(f"\n确定要清理这些失效引用吗？", abort=True)

    plan_obj.song_ids = valid_ids
    store.update_plan(plan_obj)

    click.echo(f"{E_OK} 已清理 {len(invalid_ids)} 个失效引用")
    click.echo(f"   清理后歌曲数: {len(valid_ids)} 首")


@plan.command("delete")
@click.argument("plan_id")
@click.option("--yes", is_flag=True, help="跳过确认")
def plan_delete(plan_id, yes):
    """删除翻唱计划"""
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(f"确定要删除计划「{plan_obj.name}」吗？", abort=True)

    store.delete_plan(plan_id)
    click.echo(f"{E_OK} 已删除计划：{plan_obj.name}")


@plan.command("export")
@click.argument("plan_id")
@click.option("--output", "-o", default=None, help="输出文件路径")
@click.option("--missing-only", is_flag=True, help="只导出含有缺失文件的歌曲")
@click.option("--exists-only", is_flag=True, help="只导出含有已存在文件的歌曲")
def plan_export(plan_id, output, missing_only, exists_only):
    """
    导出计划素材清单为 HTML（支持按文件存在性过滤）

    示例：
        cover-mgr plan export <ID> --missing-only   # 只看缺什么
        cover-mgr plan export <ID> --exists-only    # 只看已有什么
    """
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    if missing_only and exists_only:
        click.echo(f"{E_ERR} --missing-only 和 --exists-only 不能同时使用", err=True)
        sys.exit(1)

    # 去重
    plan_obj.set_song_ids(plan_obj.song_ids)

    filter_type = None
    if missing_only:
        filter_type = "missing"
    elif exists_only:
        filter_type = "exists"

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
    result = export_plan_html(plan_obj, songs, output_path, filter_type=filter_type, missing_refs=missing_refs, invalid_ids=[sid for sid in plan_obj.song_ids if not store.get_song(sid)])

    filter_msg = ""
    if filter_type == "missing":
        filter_msg = "（仅含缺失文件的歌曲）"
    elif filter_type == "exists":
        filter_msg = "（仅含已存在文件的歌曲）"

    click.echo(f"{E_OK} 已导出计划「{plan_obj.name}」到：{output_path} {filter_msg}")
    if missing_refs:
        click.echo(f"   失效引用: {missing_refs} 首（使用 'plan clean {plan_id}' 清理）")
    click.echo(f"   歌曲数: {result['total_songs']} 首, 总时长: {format_duration(result['total_duration'])}, 总大小: {format_file_size(result['total_size'])}")
    if filter_type == "missing":
        click.echo(f"   缺失文件项: {result['missing_files']} 个 {E_WARN}")
    elif filter_type == "exists":
        click.echo(f"   存在文件项: {result['total_files'] - result['missing_files']} 个 {E_OK}")
    else:
        if result["missing_files"]:
            click.echo(f"   缺失文件: {result['missing_files']} 个 {E_WARN}")


@plan.command("check")
@click.argument("plan_id")
@click.option("--output-dir", "-o", default=None, help="输出目录，默认当前目录")
@click.option("--name", "-n", default=None, help="文件名前缀（不含扩展名）")
def plan_check(plan_id, output_dir, name):
    """
    生成录音前检查包（Markdown + HTML + CSV 三份清单）

    按歌曲列出干声、伴奏、混音是否齐备，并标注下一步（补录/混音）
    """
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    # 去重
    plan_obj.set_song_ids(plan_obj.song_ids)

    # 获取有效歌曲
    songs = []
    missing_refs = 0
    invalid_ids = []
    for sid in plan_obj.song_ids:
        song = store.get_song(sid)
        if song:
            songs.append(song)
        else:
            missing_refs += 1
            invalid_ids.append(sid)

    if not songs:
        click.echo(f"{E_ERR} 计划中没有可检查的有效歌曲", err=True)
        sys.exit(1)

    output_dir = output_dir or os.getcwd()
    base_name = name or f"plan_{plan_obj.id}_checklist"

    result = generate_check_package(
        songs,
        output_dir,
        base_name=base_name,
        plan=plan_obj,
    )

    click.echo(f"{E_OK} 录音前检查包已生成！")
    click.echo(f"   计划: {plan_obj.name}")
    click.echo(f"   有效歌曲: {result['total_songs']} 首" + (f"（{missing_refs} 首引用已删除）" if missing_refs else ""))
    click.echo(f"   素材齐备: {result['ready_songs']} 首")
    if result["vocal_missing"]:
        click.echo(f"   缺少干声: {result['vocal_missing']} 首 {E_WARN}")
    if result["inst_missing"]:
        click.echo(f"   缺少伴奏: {result['inst_missing']} 首 {E_WARN}")
    click.echo(f"")
    click.echo(f"   Markdown: {result['md_path']}")
    click.echo(f"   CSV:      {result['csv_path']}")
    click.echo(f"   HTML:     {result['html_path']}")

    if missing_refs:
        click.echo(f"\n{E_WARN}  有 {missing_refs} 首歌曲引用已失效，可使用 'plan clean {plan_id}' 清理")
        click.echo(f"   失效引用 ID: {', '.join(invalid_ids)}")


@plan.command("collect")
@click.argument("plan_id")
@click.option("--output-dir", "-o", required=True, help="目标收集目录")
@click.option("--copy-mixes/--no-copy-mixes", default=True, help="是否同时复制混音文件，默认是")
@click.option("--yes", is_flag=True, help="跳过确认")
@click.option("--dry-run", is_flag=True, help="预览模式：只显示将要复制的文件，不实际复制")
@click.option("--zip", "zip_output", is_flag=True, help="打包为 zip 文件")
def plan_collect(plan_id, output_dir, copy_mixes, yes, dry_run, zip_output):
    """
    收集整个计划的素材到指定目录

    每首歌单独创建子文件夹，复制所有相关文件，并生成总清单和HTML报告
    """
    import shutil
    store = get_store()
    plan_obj = store.get_plan(plan_id)
    if not plan_obj:
        click.echo(f"{E_ERR} 未找到计划 ID: {plan_id}", err=True)
        sys.exit(1)

    # 去重
    plan_obj.set_song_ids(plan_obj.song_ids)

    # 获取有效歌曲
    songs = []
    missing_refs = 0
    invalid_ids = []
    for sid in plan_obj.song_ids:
        s = store.get_song(sid)
        if s:
            songs.append(s)
        else:
            missing_refs += 1
            invalid_ids.append(sid)

    if not songs:
        click.echo(f"{E_ERR} 计划中没有可收集的有效歌曲", err=True)
        sys.exit(1)

    safe_chars = set(' -_')
    safe_plan_name = "".join(c for c in plan_obj.name if c.isalnum() or c in safe_chars).strip()
    safe_plan_name = safe_plan_name or f"plan_{plan_obj.id}"
    plan_dir = os.path.join(output_dir, f"{safe_plan_name}_{plan_obj.id}")

    zip_path = None
    if zip_output:
        zip_path = plan_dir + ".zip"

    # 预览
    total_files = 0
    total_size = 0
    per_song_info = []
    missing_summary = []

    for song in songs:
        st = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
        song_files = []
        if st["vocal"]["exists"]:
            song_files.append(("干声", st["vocal"]["path"]))
        if st["instrumental"]["exists"]:
            song_files.append(("伴奏", st["instrumental"]["path"]))
        if copy_mixes:
            for m in st["mixes"]:
                if m["exists"]:
                    song_files.append((f"混音 v{m['version']:03d}", m["path"]))

        song_missing = []
        if not st["vocal"]["exists"] and song.vocal_path:
            song_missing.append("干声")
        if not st["instrumental"]["exists"] and song.instrumental_path:
            song_missing.append("伴奏")

        song_size = sum(os.path.getsize(src) for _, src in song_files)
        total_files += len(song_files)
        total_size += song_size
        per_song_info.append((song, song_files, song_missing, song_size))

        if song_missing:
            missing_summary.append(f"{song.title}: 缺少 {', '.join(song_missing)}")

    mode_label = "[DRY-RUN] 预览" if dry_run else "即将收集"
    if zip_output and not dry_run:
        mode_label = "即将打包"

    click.echo(f"{mode_label}计划「{plan_obj.name}」的素材：")
    if zip_output:
        click.echo(f"  目标文件: {zip_path}")
    else:
        click.echo(f"  目标目录: {plan_dir}")
    click.echo(f"  歌曲数量: {len(songs)} 首" + (f"（{missing_refs} 首引用已删除）" if missing_refs else ""))
    if invalid_ids:
        click.echo(f"  失效引用 ID: {', '.join(invalid_ids)}")
    click.echo(f"  文件总数: {total_files} 个")
    click.echo(f"  总大小: {format_file_size(total_size)}")

    if missing_summary:
        click.echo(f"\n  {E_WARN}  {len(missing_summary)} 首歌存在缺失文件：")
        for m in missing_summary:
            click.echo(f"    - {m}")

    if dry_run:
        click.echo(f"\n{SYM_STATS} 预览模式，未执行实际操作")
        return

    if not yes:
        target_desc = zip_path if zip_output else plan_dir
        click.confirm(f"\n确定要收集到 {target_desc} 吗？", abort=True)

    # 如果是 zip 模式，创建临时目录
    work_dir = plan_dir
    temp_dir = None
    if zip_output:
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="cover_collect_")
        work_dir = os.path.join(temp_dir, f"{safe_plan_name}_{plan_obj.id}")

    os.makedirs(work_dir, exist_ok=True)

    # 逐个收集歌曲
    collected = []
    for song, song_files, song_missing, _ in per_song_info:
        safe_name = "".join(c for c in song.title if c.isalnum() or c in safe_chars).strip()
        safe_name = safe_name or f"song_{song.id}"
        song_dir = os.path.join(work_dir, f"{safe_name}_{song.id}")
        os.makedirs(song_dir, exist_ok=True)

        song_copied = []
        for label, src in song_files:
            dst = os.path.join(song_dir, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst)
            size = format_file_size(os.path.getsize(dst))
            song_copied.append((label, os.path.basename(src), size))

        # 每首歌的清单
        manifest_path = os.path.join(song_dir, "MANIFEST.md")
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(f"# {song.title} - 素材整理清单\n\n")
            f.write(f"- **原唱**: {song.original_artist}\n")
            f.write(f"- **原曲**: {song.original_song}\n")
            f.write(f"- **歌曲ID**: {song.id}\n")
            f.write(f"- **所属计划**: {plan_obj.name}\n")
            f.write(f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            if song.tags:
                f.write(f"- **标签**: {', '.join(song.tags)}\n\n")
            if song.post_processing_params:
                f.write("## 后期参数\n\n")
                for k, v in song.post_processing_params.items():
                    f.write(f"- {k}: {v}\n")
                f.write("\n")
            f.write("## 文件清单\n\n")
            f.write("| 类型 | 文件名 | 大小 | 状态 |\n")
            f.write("|------|--------|------|------|\n")
            for label, basename, size in song_copied:
                f.write(f"| {label} | {basename} | {size} | {E_OK} |\n")
            for m in song_missing:
                f.write(f"| {m} | - | - | {E_ERR} 缺失 |\n")
            if song.notes:
                f.write(f"\n## 备注\n\n{song.notes}\n")

        collected.append((song, song_dir, len(song_copied), manifest_path))

    # 总清单 + 归档索引
    total_manifest = os.path.join(work_dir, "00_计划总清单.md")
    archive_csv = os.path.join(work_dir, "00_归档索引.csv")
    archive_md = os.path.join(work_dir, "00_归档索引.md")
    with open(total_manifest, "w", encoding="utf-8") as f:
        f.write(f"# {plan_obj.name} - 完整素材总清单\n\n")
        if plan_obj.description:
            f.write(f"> {plan_obj.description}\n\n")
        f.write(f"- **计划ID**: {plan_obj.id}\n")
        f.write(f"- **歌曲数量**: {len(songs)} 首\n")
        f.write(f"- **文件总数**: {total_files} 个\n")
        f.write(f"- **总大小**: {format_file_size(total_size)}\n")
        f.write(f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## 歌曲列表\n\n")
        f.write("| 序号 | 歌曲 | 素材状态 | 文件数 | 子目录 |\n")
        f.write("|------|------|----------|--------|--------|\n")
        for i, (song, song_dir, file_count, _) in enumerate(collected, 1):
            st = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
            v_ok = st["vocal"]["exists"]
            i_ok = st["instrumental"]["exists"]
            if v_ok and i_ok:
                status = f"{E_OK} 齐备"
            elif v_ok or i_ok:
                status = f"{E_WARN} 部分"
            else:
                status = f"{E_ERR} 缺失"
            dir_name = os.path.basename(song_dir)
            f.write(f"| {i} | {song.title} | {status} | {file_count} | {dir_name} |\n")

        if missing_summary:
            f.write(f"\n## 缺失文件提醒\n\n")
            for m in missing_summary:
                f.write(f"- {E_WARN}  {m}\n")

    import csv as csv_mod
    with open(archive_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv_mod.writer(f)
        writer.writerow(["歌曲ID", "歌曲名称", "素材类型", "原路径", "包内路径", "大小", "状态"])
        for song, song_dir, _, _ in collected:
            st = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
            safe_name = "".join(c for c in song.title if c.isalnum() or c in safe_chars).strip()
            safe_name = safe_name or f"song_{song.id}"
            rel_dir = f"{safe_name}_{song.id}"
            if st["vocal"]["exists"]:
                writer.writerow([song.id, song.title, "干声", st["vocal"]["path"],
                                 f"{rel_dir}/{os.path.basename(st['vocal']['path'])}",
                                 format_file_size(st["vocal"]["size"]), "已收入"])
            elif song.vocal_path:
                writer.writerow([song.id, song.title, "干声", song.vocal_path, "", "", "缺失"])
            if st["instrumental"]["exists"]:
                writer.writerow([song.id, song.title, "伴奏", st["instrumental"]["path"],
                                 f"{rel_dir}/{os.path.basename(st['instrumental']['path'])}",
                                 format_file_size(st["instrumental"]["size"]), "已收入"])
            elif song.instrumental_path:
                writer.writerow([song.id, song.title, "伴奏", song.instrumental_path, "", "", "缺失"])
            if copy_mixes:
                for m in st["mixes"]:
                    if m["exists"]:
                        writer.writerow([song.id, song.title, f"混音v{m['version']:03d}", m["path"],
                                         f"{rel_dir}/{os.path.basename(m['path'])}",
                                         format_file_size(m["size"]), "已收入"])

    with open(archive_md, "w", encoding="utf-8") as f:
        f.write(f"# {plan_obj.name} - 归档索引\n\n")
        f.write(f"- **计划ID**: {plan_obj.id}\n")
        f.write(f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for song, song_dir, _, _ in collected:
            st = collect_song_audio_stats(song.vocal_path, song.instrumental_path, song.mix_versions)
            safe_name = "".join(c for c in song.title if c.isalnum() or c in safe_chars).strip()
            safe_name = safe_name or f"song_{song.id}"
            rel_dir = f"{safe_name}_{song.id}"
            f.write(f"## {song.title} [{song.id}]\n\n")
            f.write("| 类型 | 原路径 | 包内路径 | 大小 | 状态 |\n")
            f.write("|------|--------|----------|------|------|\n")
            if st["vocal"]["exists"]:
                f.write(f"| 干声 | {st['vocal']['path']} | {rel_dir}/{os.path.basename(st['vocal']['path'])} | {format_file_size(st['vocal']['size'])} | 已收入 |\n")
            elif song.vocal_path:
                f.write(f"| 干声 | {song.vocal_path} | - | - | 缺失 |\n")
            if st["instrumental"]["exists"]:
                f.write(f"| 伴奏 | {st['instrumental']['path']} | {rel_dir}/{os.path.basename(st['instrumental']['path'])} | {format_file_size(st['instrumental']['size'])} | 已收入 |\n")
            elif song.instrumental_path:
                f.write(f"| 伴奏 | {song.instrumental_path} | - | - | 缺失 |\n")
            if copy_mixes:
                for m in st["mixes"]:
                    if m["exists"]:
                        f.write(f"| 混音v{m['version']:03d} | {m['path']} | {rel_dir}/{os.path.basename(m['path'])} | {format_file_size(m['size'])} | 已收入 |\n")
            f.write("\n")

    # 生成 HTML 报告
    html_path = os.path.join(work_dir, "00_素材清单.html")
    export_plan_html(plan_obj, songs, html_path, invalid_ids=[sid for sid in plan_obj.song_ids if not store.get_song(sid)])

    # zip 模式：打包并清理临时目录
    if zip_output:
        import zipfile
        click.echo(f"\n正在打包为 zip 文件...")
        os.makedirs(output_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(work_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, temp_dir)
                    zf.write(full_path, arcname)
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

        final_size = format_file_size(os.path.getsize(zip_path))
        click.echo(f"\n{E_OK} 计划素材打包完成！")
        click.echo(f"   Zip文件: {zip_path}")
        click.echo(f"   包含 {len(collected)} 首歌，{total_files} 个文件")
        click.echo(f"   压缩后大小: {final_size}")
    else:
        click.echo(f"\n{E_OK} 计划素材收集完成！")
        click.echo(f"   目录: {plan_dir}")
        click.echo(f"   收集了 {len(collected)} 首歌，{total_files} 个文件")
        click.echo(f"   总清单: {total_manifest}")
        click.echo(f"   归档索引: {archive_csv}")
        click.echo(f"   HTML报告: {html_path}")

    if missing_refs:
        click.echo(f"   {E_WARN}  有 {missing_refs} 首歌曲引用已删除，已跳过（ID: {', '.join(invalid_ids)}）")


def main():
    """主入口函数"""
    cli()


if __name__ == "__main__":
    main()
