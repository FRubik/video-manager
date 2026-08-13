"""Geração de thumbnails em thread separada, para não travar a interface."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import thumbs
from .thumbs import ThumbOptions, ThumbResult


class ThumbWorker(QThread):
    progress = Signal(int, int, str)  # concluídos, total, último nome processado
    finished_with_results = Signal(list)

    def __init__(self, videos: list[Path], output_dir: Path, opts: ThumbOptions, parent=None):
        super().__init__(parent)
        self._videos = videos
        self._output_dir = output_dir
        self._opts = opts
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        def on_progress(done: int, total: int, result: ThumbResult) -> None:
            self.progress.emit(done, total, result.video.name)

        results = thumbs.generate(
            self._videos,
            self._output_dir,
            self._opts,
            progress=on_progress,
            should_cancel=lambda: self._cancelled,
        )
        self.finished_with_results.emit(results)
