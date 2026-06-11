"""数据存储层 - JSON 文件持久化"""
import json
import os
from pathlib import Path
from typing import List, Optional

from .models import SongProject, CoverPlan


DEFAULT_DATA_DIR = Path.home() / ".cover_manager"
DEFAULT_SONGS_FILE = "songs.json"
DEFAULT_PLANS_FILE = "plans.json"


class DataStore:
    """数据存储管理器"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.songs_path = self.data_dir / DEFAULT_SONGS_FILE
        self.plans_path = self.data_dir / DEFAULT_PLANS_FILE
        self._songs: List[SongProject] = []
        self._plans: List[CoverPlan] = []
        self._load()

    def _load(self):
        """从文件加载数据"""
        if self.songs_path.exists():
            with open(self.songs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._songs = [SongProject.from_dict(s) for s in data]
        else:
            self._songs = []

        if self.plans_path.exists():
            with open(self.plans_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._plans = [CoverPlan.from_dict(p) for p in data]
        else:
            self._plans = []

    def _save_songs(self):
        """保存歌曲数据到文件"""
        with open(self.songs_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self._songs], f,
                      ensure_ascii=False, indent=2)

    def _save_plans(self):
        """保存计划数据到文件"""
        with open(self.plans_path, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in self._plans], f,
                      ensure_ascii=False, indent=2)

    def list_songs(self) -> List[SongProject]:
        """获取所有歌曲项目"""
        return list(self._songs)

    def get_song(self, song_id: str) -> Optional[SongProject]:
        """根据ID获取歌曲项目"""
        for song in self._songs:
            if song.id == song_id:
                return song
        return None

    def add_song(self, song: SongProject) -> SongProject:
        """添加歌曲项目"""
        self._songs.append(song)
        self._save_songs()
        return song

    def update_song(self, song: SongProject) -> Optional[SongProject]:
        """更新歌曲项目"""
        for i, s in enumerate(self._songs):
            if s.id == song.id:
                from datetime import datetime
                song.updated_at = datetime.now().isoformat()
                self._songs[i] = song
                self._save_songs()
                return song
        return None

    def delete_song(self, song_id: str) -> bool:
        """删除歌曲项目"""
        for i, song in enumerate(self._songs):
            if song.id == song_id:
                del self._songs[i]
                self._save_songs()
                return True
        return False

    def find_songs_by_tag(self, tag: str) -> List[SongProject]:
        """根据标签筛选歌曲"""
        return [s for s in self._songs if tag in s.tags]

    def search_songs(self, keyword: str) -> List[SongProject]:
        """搜索歌曲"""
        keyword = keyword.lower()
        return [
            s for s in self._songs
            if keyword in s.title.lower()
            or keyword in s.original_artist.lower()
            or keyword in s.original_song.lower()
        ]

    def list_plans(self) -> List[CoverPlan]:
        """获取所有翻唱计划"""
        return list(self._plans)

    def get_plan(self, plan_id: str) -> Optional[CoverPlan]:
        """根据ID获取翻唱计划"""
        for plan in self._plans:
            if plan.id == plan_id:
                return plan
        return None

    def add_plan(self, plan: CoverPlan) -> CoverPlan:
        """添加翻唱计划"""
        self._plans.append(plan)
        self._save_plans()
        return plan

    def update_plan(self, plan: CoverPlan) -> Optional[CoverPlan]:
        """更新翻唱计划"""
        for i, p in enumerate(self._plans):
            if p.id == plan.id:
                from datetime import datetime
                plan.updated_at = datetime.now().isoformat()
                self._plans[i] = plan
                self._save_plans()
                return plan
        return None

    def delete_plan(self, plan_id: str) -> bool:
        """删除翻唱计划"""
        for i, plan in enumerate(self._plans):
            if plan.id == plan_id:
                del self._plans[i]
                self._save_plans()
                return True
        return False
