"""Preferências persistidas entre execuções (pastas e opções da última sessão)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import shortcuts

CONFIG_PATH = Path.home() / ".config" / "video_manager" / "config.json"


@dataclass
class Config:
    # pastas
    videos_dir: str = ""
    thumbs_dir: str = ""
    trash_dir: str = ""
    maybe_dir: str = ""

    # geração de thumbnails
    generate_thumbs: bool = False
    only_missing: bool = True
    n_rows: int = 5
    n_cols: int = 5
    cell_height: int = 200
    margin: float = 0.05
    workers: int = 6
    add_timestamp: bool = True

    # sessão de revisão
    random_session: bool = False
    session_size: int = 30
    skip_reviewed: bool = True
    include_maybe: bool = True
    #: sessão restrita ao que ficou no "talvez" (tem precedência sobre a de cima)
    only_maybe: bool = False
    #: ordem de exibição aleatória em vez de alfabética
    shuffle_order: bool = False

    # atalhos da tela de revisão: ação -> tecla
    key_bindings: dict = field(default_factory=lambda: dict(shortcuts.DEFAULTS))

    @property
    def scans_maybe(self) -> bool:
        """A pasta “talvez” precisa entrar na varredura?"""
        return self.include_maybe or self.only_maybe

    @classmethod
    def load(cls) -> "Config":
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        config = cls(**{k: v for k, v in raw.items() if k in known})
        # configs antigas não têm a chave, e uma ação nova precisa do padrão
        config.key_bindings = shortcuts.normalize(config.key_bindings)
        return config

    def save(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass  # preferências são conveniência, nunca motivo para quebrar o app
