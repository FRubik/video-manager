"""Geração dos contact sheets (grade de frames) — motor herdado do Thumbnail Maker."""

from __future__ import annotations

from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .i18n import tr
from .library import thumb_output_name


@dataclass
class ThumbOptions:
    n_rows: int = 5
    n_cols: int = 5
    cell_height: int = 200
    margin: float = 0.05  # ignora os primeiros/últimos X% do vídeo
    add_timestamp: bool = True
    workers: int = 6


@dataclass
class ThumbResult:
    video: Path
    ok: bool
    error: str | None = None
    #: abortado a pedido do usuário — não conta como falha do vídeo
    cancelled: bool = False


def format_seconds(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def _draw_timestamp(img: Image.Image, text: str, font) -> None:
    draw = ImageDraw.Draw(img)
    padding = 4
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:  # Pillow < 8
        text_w, text_h = draw.textsize(text, font=font)

    w, h = img.size
    x, y = 10, h - 10 - text_h
    draw.rectangle(
        [max(0, x - padding), max(0, y - padding),
         min(w, x + text_w + padding), min(h, y + text_h + padding)],
        fill=(0, 0, 0),
    )
    draw.text((x, y), text, font=font, fill=(255, 255, 255))


def extract_sheet(
    video_path: Path,
    output_dir: Path,
    opts: ThumbOptions,
    should_cancel: Callable[[], bool] | None = None,
    on_step: Callable[[], None] | None = None,
) -> ThumbResult:
    """Extrai n_rows*n_cols frames equidistantes e monta a grade em um JPEG.

    `should_cancel` é consultado a cada frame: num vídeo 4K de vários GB uma
    única extração leva minutos, e esperar por ela era o que fazia o cancelar
    parecer que não funcionava. `on_step` avisa a cada frame pronto, para a
    barra de progresso andar dentro do vídeo e não só entre um e outro.
    """
    cancelado = ThumbResult(video_path, False, None, cancelled=True)
    try:
        if should_cancel is not None and should_cancel():
            return cancelado

        output_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return ThumbResult(video_path, False, tr("error.thumb.open"))

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        if total_frames <= 0 or fps <= 0:
            cap.release()
            return ThumbResult(video_path, False, tr("error.thumb.metadata"))

        duration = total_frames / fps
        start_time = duration * opts.margin
        end_time = duration * (1.0 - opts.margin)
        if end_time <= start_time:  # vídeo muito curto para a margem pedida
            start_time, end_time = 0.0, duration

        n_thumbs = opts.n_rows * opts.n_cols

        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start_time * 1000.0))
        ret, first_frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, first_frame = cap.read()
            if not ret:
                cap.release()
                return ThumbResult(video_path, False, tr("error.thumb.frames"))

        fh, fw = first_frame.shape[:2]
        aspect_ratio = fw / fh if fh > 0 else 16 / 9
        cell_h = int(opts.cell_height)
        cell_w = max(1, int(cell_h * aspect_ratio))

        times = np.linspace(start_time, end_time, n_thumbs + 2)[1:-1]
        font = ImageFont.load_default()
        thumbs: list[Image.Image] = []

        for t in times:
            if should_cancel is not None and should_cancel():
                cap.release()
                return cancelado
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ret, frame_bgr = cap.read()
            if not ret:  # fallback por índice de frame
                frame_idx = min(total_frames - 1, max(0, int(t * fps)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame_bgr = cap.read()

            if not ret:
                thumbs.append(Image.new("RGB", (cell_w, cell_h), (0, 0, 0)))
                if on_step is not None:
                    on_step()
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(cv2.resize(frame_rgb, (cell_w, cell_h)))
            if opts.add_timestamp:
                _draw_timestamp(img, format_seconds(t), font)
            thumbs.append(img)
            if on_step is not None:
                on_step()

        cap.release()

        while len(thumbs) < n_thumbs:
            thumbs.append(Image.new("RGB", (cell_w, cell_h), (0, 0, 0)))

        grid = Image.new("RGB", (cell_w * opts.n_cols, cell_h * opts.n_rows), (0, 0, 0))
        for idx, thumb in enumerate(thumbs):
            grid.paste(thumb, ((idx % opts.n_cols) * cell_w, (idx // opts.n_cols) * cell_h))

        grid.save(output_dir / thumb_output_name(video_path), "JPEG", quality=90)
        return ThumbResult(video_path, True)

    except Exception as exc:  # nunca deixa um vídeo problemático derrubar o lote
        return ThumbResult(video_path, False, str(exc))


def generate(
    videos: Iterable[Path],
    output_dir: Path,
    opts: ThumbOptions,
    progress: Callable[[int, int, ThumbResult], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_step: Callable[[], None] | None = None,
) -> list[ThumbResult]:
    """Processa a lista em paralelo, reportando progresso a cada vídeo concluído.

    `on_step` é chamado de dentro das threads do pool, a cada frame extraído:
    quem passa o callback precisa que ele seja seguro para chamadas simultâneas
    e fora da thread principal.
    """
    videos = list(videos)
    results: list[ThumbResult] = []
    if not videos:
        return results

    output_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, opts.workers)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                extract_sheet, v, output_dir, opts, should_cancel, on_step
            ): v
            for v in videos
        }
        done = 0
        for future in as_completed(futures):
            # sem `break`: a fila é percorrida até o fim mesmo cancelada, para
            # que todo vídeo submetido tenha um resultado. O que ainda não
            # começou sai na hora; o que está em curso para no próximo frame.
            if should_cancel is not None and should_cancel():
                for pending in futures:
                    pending.cancel()
            try:
                result = future.result()
            except CancelledError:
                result = ThumbResult(futures[future], False, None, cancelled=True)
            except Exception as exc:
                result = ThumbResult(futures[future], False, str(exc))
            results.append(result)
            if result.cancelled:
                continue
            done += 1
            if progress is not None:
                progress(done, len(videos), result)

    return results
