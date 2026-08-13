"""Varredura das pastas, pareamento vídeo↔thumbnail, histórico e quarentena."""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

VIDEO_EXTS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv",
    ".flv", ".m4v", ".mpg", ".mpeg", ".ts", ".3gp",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

STATE_FILE = ".video_manager_state.json"
TRASH_LOG = "_movimentos.jsonl"

KEEP = "keep"
DELETE = "delete"


@dataclass
class VideoEntry:
    """Um vídeo da pasta e a thumbnail correspondente (quando existe)."""

    video: Path
    thumb: Path | None = None
    decision: str | None = None  # None | KEEP | DELETE

    @property
    def name(self) -> str:
        return self.video.name

    @property
    def size_mb(self) -> float:
        try:
            return self.video.stat().st_size / (1024 * 1024)
        except OSError:
            return 0.0


def list_videos(videos_dir: Path) -> list[Path]:
    """Vídeos no primeiro nível da pasta, em ordem alfabética."""
    if not videos_dir.is_dir():
        return []
    videos = [
        p for p in videos_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    ]
    return sorted(videos, key=lambda p: p.name.lower())


def index_thumbs(thumbs_dir: Path) -> dict[str, Path]:
    """Índice de thumbnails aceitando `video.mp4.jpg` (padrão) e `video.jpg`."""
    index: dict[str, Path] = {}
    if not thumbs_dir.is_dir():
        return index
    for p in thumbs_dir.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            index.setdefault(p.stem.lower(), p)
    return index


def find_thumb(video: Path, index: dict[str, Path]) -> Path | None:
    for key in (video.name.lower(), video.stem.lower()):
        if key in index:
            return index[key]
    return None


def thumb_output_name(video: Path) -> str:
    """Nome do arquivo gerado — mantém a convenção do notebook original."""
    return f"{video.name}.jpg"


def scan(videos_dir: Path, thumbs_dir: Path) -> list[VideoEntry]:
    index = index_thumbs(thumbs_dir)
    return [VideoEntry(video=v, thumb=find_thumb(v, index)) for v in list_videos(videos_dir)]


class ReviewState:
    """Histórico de decisões, salvo dentro da pasta de thumbnails.

    Fica junto das thumbs (e não no ~/.config) para que a pasta continue
    autossuficiente se for movida ou acessada de outra máquina.
    """

    def __init__(self, thumbs_dir: Path):
        self.path = thumbs_dir / STATE_FILE
        self.reviewed: dict[str, dict] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw.get("reviewed"), dict):
                self.reviewed = raw["reviewed"]
        except (OSError, ValueError):
            pass

    def was_reviewed(self, name: str) -> bool:
        return name in self.reviewed

    def record(self, name: str, decision: str) -> None:
        self.reviewed[name] = {
            "decision": decision,
            "at": datetime.now().isoformat(timespec="seconds"),
        }

    def forget(self, name: str) -> None:
        self.reviewed.pop(name, None)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"reviewed": self.reviewed}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass


def build_session(
    entries: list[VideoEntry],
    state: ReviewState,
    *,
    random_session: bool,
    session_size: int,
    skip_reviewed: bool,
    require_thumb: bool = True,
) -> list[VideoEntry]:
    """Seleciona o que entra nesta sessão de revisão."""
    pool = list(entries)
    if require_thumb:
        pool = [e for e in pool if e.thumb is not None]
    if skip_reviewed:
        pool = [e for e in pool if not state.was_reviewed(e.name)]
    if random_session and session_size > 0 and len(pool) > session_size:
        pool = random.sample(pool, session_size)
        pool.sort(key=lambda e: e.name.lower())
    return pool


def unique_destination(dest: Path) -> Path:
    """Evita sobrescrever um arquivo homônimo já existente no destino."""
    if not dest.exists():
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    n = 2
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def move_to_trash(video: Path, trash_dir: Path) -> Path:
    """Move o vídeo para a quarentena e registra o movimento em log."""
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_destination(trash_dir / video.name)
    shutil.move(str(video), str(dest))
    _log_move(trash_dir, video, dest)
    return dest


def _log_move(trash_dir: Path, origin: Path, dest: Path) -> None:
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "origem": str(origin),
        "destino": str(dest),
    }
    try:
        with (trash_dir / TRASH_LOG).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def default_trash_dir(videos_dir: Path) -> Path:
    return videos_dir / "_para_apagar"
