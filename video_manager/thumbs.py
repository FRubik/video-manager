"""Geração dos contact sheets (grade de frames) — motor herdado do Thumbnail Maker."""

from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .i18n import tr
from .library import launch_env, thumb_output_name


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


def _time_window(duration: float, margin: float) -> tuple[float, float]:
    start = duration * margin
    end = duration * (1.0 - margin)
    if end <= start:  # vídeo muito curto para a margem pedida
        return 0.0, duration
    return start, end


def _grab_opencv(
    cap: cv2.VideoCapture,
    times: np.ndarray,
    total_frames: int,
    fps: float,
    should_cancel: Callable[[], bool] | None,
    on_step: Callable[[], None] | None,
) -> tuple[list[np.ndarray | None], bool]:
    """Um frame (BGR) por instante de `times`, ou None onde o decoder falhou.

    Devolve `(frames, cancelado)`. `should_cancel` é consultado a cada frame —
    num 4K de vários GB uma única extração leva minutos. `on_step` avisa a cada
    instante processado, dê certo ou não: a barra de progresso conta células,
    não sucessos.
    """
    frames: list[np.ndarray | None] = []
    for t in times:
        if should_cancel is not None and should_cancel():
            return frames, True
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ret, frame_bgr = cap.read()
        if not ret:  # fallback por índice de frame
            frame_idx = min(total_frames - 1, max(0, int(t * fps)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame_bgr = cap.read()
        frames.append(frame_bgr if ret else None)
        if on_step is not None:
            on_step()
    return frames, False


def _grab_ffmpeg(
    video_path: Path,
    times: np.ndarray,
    should_cancel: Callable[[], bool] | None,
    on_step: Callable[[], None] | None,
) -> tuple[list[np.ndarray | None], bool]:
    """Segundo caminho, quando o OpenCV não decodificou um único frame.

    É o caso do AV1: os wheels do `opencv-python` trazem um ffmpeg sem `dav1d`,
    só com o decoder de AV1 por hardware, e `cap.read()` falha em todos os
    instantes. O `ffmpeg` do sistema (dependência **opcional**) decodifica.

    Um processo por frame, com seek preciso — foi o único desenho comportado em
    memória na medição de 01/09 (os de processo único chegaram a 7 GB de pico),
    e a precisão do seek mantém o timestamp desenhado honesto. `on_step` conta
    outra rodada de frames: quem chama já esticou o total para acomodá-la.
    """
    frames: list[np.ndarray | None] = []
    for t in times:
        if should_cancel is not None and should_cancel():
            return frames, True
        frames.append(_ffmpeg_one_frame(video_path, float(t)))
        if on_step is not None:
            on_step()
    return frames, False


def _ffmpeg_one_frame(video_path: Path, t: float) -> np.ndarray | None:
    """Extrai um único frame com o ffmpeg do sistema, devolvido como BGR.

    `-ss` antes de `-i` é seek preciso e rápido (decodifica só do keyframe
    anterior até `t`). `launch_env()` evita que o subprocesso herde o
    `LD_LIBRARY_PATH` que o `import cv2` deixa envenenado — o mesmo que
    derrubava o VLC.
    """
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-ss", f"{t:.3f}", "-i", str(video_path),
        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, env=launch_env(), timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return cv2.imdecode(np.frombuffer(proc.stdout, dtype=np.uint8), cv2.IMREAD_COLOR)


def _compose(
    frames: list[np.ndarray | None], times: np.ndarray, opts: ThumbOptions
) -> Image.Image:
    """Monta a grade a partir dos frames; posições sem frame ficam pretas."""
    reference = next(f for f in frames if f is not None)
    fh, fw = reference.shape[:2]
    aspect_ratio = fw / fh if fh > 0 else 16 / 9
    cell_h = int(opts.cell_height)
    cell_w = max(1, int(cell_h * aspect_ratio))
    font = ImageFont.load_default()

    cells: list[Image.Image] = []
    for t, frame_bgr in zip(times, frames):
        if frame_bgr is None:
            cells.append(Image.new("RGB", (cell_w, cell_h), (0, 0, 0)))
            continue
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(cv2.resize(frame_rgb, (cell_w, cell_h)))
        if opts.add_timestamp:
            _draw_timestamp(img, format_seconds(t), font)
        cells.append(img)

    while len(cells) < opts.n_rows * opts.n_cols:
        cells.append(Image.new("RGB", (cell_w, cell_h), (0, 0, 0)))

    grid = Image.new("RGB", (cell_w * opts.n_cols, cell_h * opts.n_rows), (0, 0, 0))
    for idx, cell in enumerate(cells):
        grid.paste(cell, ((idx % opts.n_cols) * cell_w, (idx // opts.n_cols) * cell_h))
    return grid


def extract_sheet(
    video_path: Path,
    output_dir: Path,
    opts: ThumbOptions,
    should_cancel: Callable[[], bool] | None = None,
    on_step: Callable[[], None] | None = None,
    on_ffmpeg_fallback: Callable[[int], None] | None = None,
) -> ThumbResult:
    """Extrai n_rows*n_cols frames equidistantes e monta a grade em um JPEG.

    O OpenCV é o motor; quando ele não decodifica nada (AV1, tipicamente) e o
    `ffmpeg` está no PATH, um segundo caminho tenta com ele antes de desistir.
    Um vídeo que não rendeu **nenhum** frame vira erro — uma folha preta salva
    é pior que uma falha visível.
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
        start_time, end_time = _time_window(duration, opts.margin)
        n_thumbs = opts.n_rows * opts.n_cols
        times = np.linspace(start_time, end_time, n_thumbs + 2)[1:-1]

        frames, cancelled = _grab_opencv(
            cap, times, total_frames, fps, should_cancel, on_step
        )
        cap.release()
        if cancelled:
            return cancelado

        if not any(f is not None for f in frames) and shutil.which("ffmpeg"):
            if on_ffmpeg_fallback is not None:
                on_ffmpeg_fallback(len(times))
            frames, cancelled = _grab_ffmpeg(video_path, times, should_cancel, on_step)
            if cancelled:
                return cancelado

        if not any(f is not None for f in frames):
            return ThumbResult(video_path, False, tr("error.thumb.frames"))

        sheet = _compose(frames, times, opts)
        sheet.save(output_dir / thumb_output_name(video_path), "JPEG", quality=90)
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
    on_ffmpeg_fallback: Callable[[int], None] | None = None,
) -> list[ThumbResult]:
    """Processa a lista em paralelo, reportando progresso a cada vídeo concluído.

    `on_step` é chamado de dentro das threads do pool, a cada frame extraído, e
    `on_ffmpeg_fallback(n)` quando um vídeo cai no ffmpeg (com o número de frames
    da segunda passada): quem passa os callbacks precisa que sejam seguros para
    chamadas simultâneas e fora da thread principal.
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
                extract_sheet, v, output_dir, opts, should_cancel, on_step,
                on_ffmpeg_fallback,
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
