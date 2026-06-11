"""数据模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import uuid


TAGS = ["已完成", "混音中", "待修音"]


@dataclass
class MixVersion:
    """混音版本记录"""
    version: int
    output_path: str
    created_at: str
    dry_gain: float = 0.0
    instrumental_gain: float = 0.0
    notes: str = ""


@dataclass
class SongProject:
    """翻唱歌曲项目"""
    id: str
    title: str
    original_artist: str
    original_song: str
    vocal_path: str = ""
    instrumental_path: str = ""
    post_processing_params: dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    mix_versions: List[MixVersion] = field(default_factory=list)
    duration: float = 0.0
    file_size: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""

    @classmethod
    def create(cls, title: str, original_artist: str, original_song: str,
               vocal_path: str = "", instrumental_path: str = "",
               tags: Optional[List[str]] = None, notes: str = "") -> "SongProject":
        return cls(
            id=str(uuid.uuid4())[:8],
            title=title,
            original_artist=original_artist,
            original_song=original_song,
            vocal_path=vocal_path,
            instrumental_path=instrumental_path,
            tags=tags or [],
            notes=notes,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "original_artist": self.original_artist,
            "original_song": self.original_song,
            "vocal_path": self.vocal_path,
            "instrumental_path": self.instrumental_path,
            "post_processing_params": self.post_processing_params,
            "tags": self.tags,
            "mix_versions": [mv.__dict__ for mv in self.mix_versions],
            "duration": self.duration,
            "file_size": self.file_size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SongProject":
        mix_versions = [MixVersion(**mv) for mv in data.get("mix_versions", [])]
        return cls(
            id=data["id"],
            title=data["title"],
            original_artist=data["original_artist"],
            original_song=data["original_song"],
            vocal_path=data.get("vocal_path", ""),
            instrumental_path=data.get("instrumental_path", ""),
            post_processing_params=data.get("post_processing_params", {}),
            tags=data.get("tags", []),
            mix_versions=mix_versions,
            duration=data.get("duration", 0.0),
            file_size=data.get("file_size", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            notes=data.get("notes", ""),
        )


@dataclass
class CoverPlan:
    """翻唱计划"""
    id: str
    name: str
    description: str = ""
    song_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def create(cls, name: str, description: str = "",
               song_ids: Optional[List[str]] = None) -> "CoverPlan":
        unique_ids = []
        seen = set()
        for sid in song_ids or []:
            if sid not in seen:
                seen.add(sid)
                unique_ids.append(sid)
        return cls(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            song_ids=unique_ids,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "song_ids": self.song_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def add_song_id(self, song_id: str) -> bool:
        """添加歌曲ID（自动去重），返回 True 表示新增，False 表示已存在"""
        if song_id not in self.song_ids:
            self.song_ids.append(song_id)
            return True
        return False

    def remove_song_id(self, song_id: str) -> bool:
        """移除歌曲ID，返回 True 表示删除成功"""
        if song_id in self.song_ids:
            self.song_ids.remove(song_id)
            return True
        return False

    def set_song_ids(self, song_ids: List[str]) -> int:
        """设置歌曲ID列表（自动去重），返回最终数量"""
        unique_ids = []
        seen = set()
        for sid in song_ids:
            if sid not in seen:
                seen.add(sid)
                unique_ids.append(sid)
        self.song_ids = unique_ids
        return len(unique_ids)

    @classmethod
    def from_dict(cls, data: dict) -> "CoverPlan":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            song_ids=data.get("song_ids", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
