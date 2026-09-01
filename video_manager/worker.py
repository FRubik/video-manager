"""Geração de thumbnails em thread separada, para não travar a interface."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import thumbs
from .thumbs import ThumbOptions, ThumbResult


class ThumbWorker(QThread):
    progress = Signal(int, int)  # concluídos, total
    finished_with_results = Signal(list)

    def __init__(self, videos: list[Path], output_dir: Path, opts: ThumbOptions, parent=None):
        super().__init__(parent)
        self._videos = videos
        self._output_dir = output_dir
        self._opts = opts
        self._cancelled = False
        self._frames_done = 0
        #: total de frames do lote — a unidade fina da barra de progresso. Cresce
        #: quando um vídeo cai no ffmpeg (segunda passada, mais frames a fazer).
        self._frames_total = max(1, len(videos) * opts.n_rows * opts.n_cols)
        #: quantos vídeos precisaram do ffmpeg (AV1) — citado no diálogo
        self._ffmpeg_fallbacks = 0
        self._counters_lock = threading.Lock()

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def frames_done(self) -> int:
        """Frames já extraídos no lote inteiro.

        Lido pela interface por amostragem (um QTimer), e não por sinal: o
        contador é incrementado pelas threads do pool, que não são threads do
        Qt e não deveriam emitir sinais.
        """
        return self._frames_done

    @property
    def frames_total(self) -> int:
        return self._frames_total

    @property
    def ffmpeg_fallbacks(self) -> int:
        return self._ffmpeg_fallbacks

    def _count_frame(self) -> None:
        with self._counters_lock:
            self._frames_done += 1

    def _note_ffmpeg_fallback(self, extra_frames: int) -> None:
        with self._counters_lock:
            self._frames_total += extra_frames
            self._ffmpeg_fallbacks += 1

    def run(self) -> None:
        def on_progress(done: int, total: int, result: ThumbResult) -> None:
            self.progress.emit(done, total)

        results = thumbs.generate(
            self._videos,
            self._output_dir,
            self._opts,
            progress=on_progress,
            should_cancel=lambda: self._cancelled,
            on_step=self._count_frame,
            on_ffmpeg_fallback=self._note_ffmpeg_fallback,
        )
        self.finished_with_results.emit(results)
