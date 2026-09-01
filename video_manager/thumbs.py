"""Geração dos contact sheets (grade de frames) — motor herdado do Thumbnail Maker."""

from __future__ import annotations

import functools
import shutil
import subprocess
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import metadata
from .i18n import tr
from .library import launch_env, thumb_output_name
from .metadata import VideoInfo


@dataclass
class ThumbOptions:
    n_rows: int = 5
    n_cols: int = 5
    cell_height: int = 200
    margin: float = 0.05  # ignora os primeiros/últimos X% do vídeo
    add_timestamp: bool = True
    workers: int = 6
    #: faixa superior com os dados do arquivo
    header: bool = True
    #: quais informações entram nela (chaves de `metadata.FIELDS`)
    header_fields: list[str] = field(default_factory=lambda: list(metadata.DEFAULTS))


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


# ------------------------------------------------------------------ cabeçalho

HEADER_BG = (46, 46, 46)
HEADER_FG = (255, 255, 255)
HEADER_DIM = (170, 170, 170)
WATERMARK_FG = (124, 124, 124)

#: marca do programa, à direita da faixa — fixa, não traduzida
WATERMARK_TITLE = "VIDEO MANAGER"
WATERMARK_SUB = "github.com/FRubik/video-manager"

#: mesmo ícone de `icons.py`, lido daqui pelo caminho para não arrastar o Qt
#: para dentro do motor de geração
LOGO_PATH = Path(__file__).parent / "icons" / "hicolor" / "256x256" / "apps" / "video-manager.png"

#: cinza do ponto mais claro do logo depois de recolorido, contra os 46 do
#: fundo — o ícone colorido, com o fundo escuro dele, virava um bloco no meio
#: da faixa em vez de fazer par com o texto da marca
LOGO_PEAK = 168

#: primeira que existir no sistema; a ordem cobre Linux, Windows e macOS
_FONT_FILES: dict[bool, tuple[str, ...]] = {
    False: (
        "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf",
        "arial.ttf", "Arial.ttf", "Helvetica.ttc",
    ),
    True: (
        "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf",
        "arialbd.ttf", "Arial Bold.ttf", "Helvetica.ttc",
    ),
}


@functools.lru_cache(maxsize=None)
def _font(size: int, bold: bool = False):
    """Uma TrueType do sistema no tamanho pedido.

    A `load_default()` do Pillow é bitmap de 11px e, mesmo na variante
    escalável (a embutida Aileron), **não tem os acentos** — nome de arquivo em
    português sairia com caixinhas. Por isso ela é o último recurso, não a
    primeira escolha; qualquer sistema com fontes instaladas cai antes.
    """
    for name in _FONT_FILES[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:  # pragma: no cover — Pillow antigo
        return ImageFont.load_default()


@functools.lru_cache(maxsize=None)
def _logo(height: int):
    """O ícone do programa na altura pedida, em cinza, ou None se não houver.

    O ícone é recolorido em vez de colado como está: `autocontrast` estica a
    luminância, e a rampa leva o fundo escuro dele para o cinza da faixa e os
    cartões claros para o tom do texto da marca. O resultado é um desenho no
    mesmo peso do "VIDEO MANAGER" ao lado, não um adesivo.
    """
    try:
        with Image.open(LOGO_PATH) as arquivo:
            logo = arquivo.convert("RGBA")
    except (OSError, ValueError):
        return None
    width = max(1, round(height * logo.width / logo.height))
    logo = logo.resize((width, height), Image.LANCZOS)

    base, peak = HEADER_BG[0], LOGO_PEAK
    # o expoente afunda as sombras: o fundo do ícone encosta no da faixa e só
    # os cartões ficam de pé
    rampa = [round(base + (peak - base) * (v / 255) ** 1.7) for v in range(256)]
    cinza = ImageOps.autocontrast(logo.convert("L")).point(rampa)
    return Image.merge("RGB", (cinza, cinza, cinza)), logo.getchannel("A")


def _ellipsize(text: str, font, max_width: float) -> str:
    """Corta no meio, não no fim: é o fim do nome que costuma identificar o vídeo."""
    if font.getlength(text) <= max_width:
        return text
    head, tail = len(text) // 2, len(text) - len(text) // 2
    while head + tail > 4:
        if head > tail:
            head -= 1
        else:
            tail -= 1
        candidate = f"{text[:head]}…{text[len(text) - tail:]}"
        if font.getlength(candidate) <= max_width:
            return candidate
    return "…"


def _header_image(width: int, lines: list[tuple[str, str]]):
    """Faixa superior com os dados do arquivo, na largura da grade.

    O corpo da fonte acompanha a largura da folha: uma grade de 1 coluna tem
    ~355px e a mesma fonte de uma de 5 colunas ficaria ilegível de tão grande.
    O teto e o entrelinha são apertados de propósito — numa grade 5x5 a faixa
    chegava a ficar mais alta que uma linha inteira de frames.
    """
    if not lines:
        return None

    size = max(9, min(17, round(width / 92)))
    font = _font(size, True)  # negrito, como na folha do Video Thumbnails Maker
    pad_x = max(8, round(width * 0.01))
    line_h = round(size * 1.4)
    pad_y = max(4, round(size * 0.4))

    mark_font = _font(max(size, round(size * 2.1)), True)
    sub_font = _font(max(8, round(size * 0.85)))
    block_h = mark_font.size + sub_font.size + 4
    # a faixa nunca é mais baixa que a marca: com poucas informações escolhidas
    # ela vazaria pelo corte da folha
    height = max(pad_y * 2 + line_h * len(lines), pad_y * 2 + block_h)

    image = Image.new("RGB", (width, height), HEADER_BG)
    draw = ImageDraw.Draw(image)

    label_w = max((font.getlength(label) for label, _ in lines), default=0.0)
    colon_x = pad_x + label_w + size * 0.6
    value_x = colon_x + size * 0.8

    # a marca do programa: logo + nome + endereço, encostados na direita. Numa
    # grade estreita ela não cabe sem comer a linha do nome do arquivo, que é a
    # que interessa — aí simplesmente não é desenhada.
    text_w = max(mark_font.getlength(WATERMARK_TITLE), sub_font.getlength(WATERMARK_SUB))
    logo = _logo(block_h)
    mark_w = text_w + (logo[0].width + round(size * 0.7) if logo else 0)
    if width < 640 or mark_w > width * 0.4 or value_x + mark_w + size * 8 > width:
        mark_w = 0.0
    else:
        top = max(pad_y, (height - block_h) // 2)
        right = width - pad_x
        draw.text((right, top), WATERMARK_TITLE, font=mark_font,
                  fill=WATERMARK_FG, anchor="ra")
        draw.text((right, top + mark_font.size + 4), WATERMARK_SUB, font=sub_font,
                  fill=WATERMARK_FG, anchor="ra")
        if logo is not None:
            desenho, mascara = logo
            image.paste(desenho, (round(right - text_w - size * 0.7) - desenho.width, top),
                        mascara)

    available = width - value_x - pad_x - (mark_w + size * 1.5 if mark_w else 0)
    for row, (label, value) in enumerate(lines):
        y = pad_y + row * line_h
        draw.text((pad_x, y), label, font=font, fill=HEADER_FG)
        draw.text((colon_x, y), ":", font=font, fill=HEADER_DIM)
        draw.text((value_x, y), _ellipsize(value, font, available),
                  font=font, fill=HEADER_FG)
    return image


def _compose(
    frames: list[np.ndarray | None],
    times: np.ndarray,
    opts: ThumbOptions,
    info: VideoInfo | None = None,
) -> Image.Image:
    """Monta a grade a partir dos frames; posições sem frame ficam pretas.

    Com `opts.header` e um `info`, a folha ganha a faixa de dados no topo.
    """
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

    if not opts.header or info is None:
        return grid
    header = _header_image(grid.width, metadata.header_lines(info, opts.header_fields))
    if header is None:
        return grid
    sheet = Image.new("RGB", (grid.width, header.height + grid.height), HEADER_BG)
    sheet.paste(header, (0, 0))
    sheet.paste(grid, (0, header.height))
    return sheet


def _collect_info(
    video_path: Path,
    cap: cv2.VideoCapture,
    fps: float,
    duration: float,
    opts: ThumbOptions,
) -> VideoInfo | None:
    """Dados do arquivo para o cabeçalho, ou None quando ele está desligado.

    O `ffprobe` só é chamado se alguma informação escolhida depender dele — é
    um subprocesso por vídeo, e quem quer só nome, tamanho e duração não paga
    por ele. Sem `ffprobe` no PATH, `probe` devolve o que já havia.
    """
    if not opts.header:
        return None
    info = metadata.from_capture(
        video_path,
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        fps,
        duration,
    )
    if metadata.needs_ffprobe(opts.header_fields):
        info = metadata.probe(info)
    return info


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
        info = _collect_info(video_path, cap, fps, duration, opts)
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

        if info is not None and not (info.width and info.height):
            # AV1 e afins: o OpenCV abre o arquivo mas não devolve a resolução;
            # o frame que sobreviveu à extração sabe dizer qual é
            reference = next(f for f in frames if f is not None)
            info.height, info.width = reference.shape[:2]

        sheet = _compose(frames, times, opts, info)
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
