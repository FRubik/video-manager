"""Metadados do vídeo para o cabeçalho do contact sheet.

O que o OpenCV e o `os.stat` já dão (nome, tamanho, resolução, fps, duração)
sai sempre; codec, bitrate e a faixa de áudio dependem do `ffprobe`, que é
dependência **opcional** — sem ele o cabeçalho encolhe em vez de falhar.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import i18n
from .i18n import tr
from .library import format_size, launch_env


@dataclass(frozen=True)
class HeaderField:
    """Uma informação que o usuário pode ligar ou desligar no cabeçalho."""

    key: str
    #: linha própria; um campo com `parent` só acrescenta algo à linha do pai
    parent: str | None = None
    #: marcado quando não há preferência salva
    default: bool = False
    #: sem `ffprobe` o campo simplesmente não aparece
    needs_ffprobe: bool = False


#: ordem em que as linhas são desenhadas; os filhos vêm logo depois do pai
FIELDS: tuple[HeaderField, ...] = (
    HeaderField("name", default=True),
    HeaderField("size", default=True),
    HeaderField("bitrate", parent="size", needs_ffprobe=True),
    HeaderField("modified", parent="size"),
    HeaderField("resolution", default=True),
    HeaderField("duration", default=True),
    HeaderField("video", default=True, needs_ffprobe=True),
    HeaderField("pixel_format", parent="video", needs_ffprobe=True),
    HeaderField("audio", default=True, needs_ffprobe=True),
    HeaderField("audio_streams", parent="audio", needs_ffprobe=True),
)

BY_KEY: dict[str, HeaderField] = {f.key: f for f in FIELDS}

DEFAULTS: list[str] = [f.key for f in FIELDS if f.default]


def normalize(selection) -> list[str]:
    """Seleção válida, na ordem de `FIELDS`; entrada inutilizável vira o padrão.

    Um filho só sobrevive com o pai marcado — é ele quem desenha a linha.
    """
    if not isinstance(selection, (list, tuple, set)):
        return list(DEFAULTS)
    chosen = {k for k in selection if k in BY_KEY}
    return [f.key for f in FIELDS if f.key in chosen and (f.parent is None or f.parent in chosen)]


def needs_ffprobe(selection) -> bool:
    return any(BY_KEY[k].needs_ffprobe for k in normalize(selection))


def has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


@dataclass
class VideoInfo:
    """O que se sabe de um vídeo. Campos que ninguém soube responder ficam None."""

    path: Path
    size_bytes: int = 0
    modified: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0

    container_bitrate: int | None = None
    video_codec: str | None = None
    video_profile: str | None = None
    video_bitrate: int | None = None
    pixel_format: str | None = None
    bit_depth: int | None = None
    audio_codec: str | None = None
    audio_profile: str | None = None
    audio_bitrate: int | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    audio_streams: int = 0
    #: o ffprobe respondeu (mesmo que sem alguns campos)
    probed: bool = False


def from_capture(path: Path, width: int, height: int, fps: float, duration: float) -> VideoInfo:
    """Base montada com o que `extract_sheet` já leu do OpenCV e do disco."""
    info = VideoInfo(path, width=width, height=height, fps=fps, duration=duration)
    try:
        stat = path.stat()
        info.size_bytes = stat.st_size
        info.modified = stat.st_mtime
    except OSError:
        pass
    return info


def probe(info: VideoInfo, timeout: float = 30.0) -> VideoInfo:
    """Completa `info` com o `ffprobe` do sistema; sem ele, devolve como está.

    `launch_env()` pelo mesmo motivo do ffmpeg em `thumbs`: o `import cv2`
    envenena o `LD_LIBRARY_PATH` do processo e o filho não deve herdar isso.
    """
    if not has_ffprobe():
        return info
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "--",
        str(info.path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, env=launch_env(), timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return info
    if proc.returncode != 0 or not proc.stdout:
        return info
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return info

    _apply_format(info, data.get("format") or {})
    streams = data.get("streams") or []
    _apply_video(info, next((s for s in streams if s.get("codec_type") == "video"), {}))
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    info.audio_streams = len(audios)
    _apply_audio(info, audios[0] if audios else {})
    info.probed = True
    return info


def _apply_format(info: VideoInfo, fmt: dict) -> None:
    info.container_bitrate = _as_int(fmt.get("bit_rate"))
    duration = _as_float(fmt.get("duration"))
    if duration:  # mais confiável que total_frames/fps em arquivo com VFR
        info.duration = duration


def _apply_video(info: VideoInfo, stream: dict) -> None:
    if not stream:
        return
    info.video_codec = stream.get("codec_name")
    info.video_profile = _profile(stream)
    info.video_bitrate = _as_int(stream.get("bit_rate"))
    info.pixel_format = stream.get("pix_fmt")
    info.bit_depth = _as_int(stream.get("bits_per_raw_sample"))
    info.width = _as_int(stream.get("width")) or info.width
    info.height = _as_int(stream.get("height")) or info.height
    fps = _as_fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    if fps:
        info.fps = fps


def _apply_audio(info: VideoInfo, stream: dict) -> None:
    if not stream:
        return
    info.audio_codec = stream.get("codec_name")
    info.audio_profile = stream.get("profile")
    info.audio_bitrate = _as_int(stream.get("bit_rate"))
    info.audio_sample_rate = _as_int(stream.get("sample_rate"))
    info.audio_channels = _as_int(stream.get("channels"))


def _profile(stream: dict) -> str | None:
    """Perfil com o nível quando faz sentido: `High@L4.0`."""
    profile = stream.get("profile")
    if not profile:
        return None
    level = _as_int(stream.get("level"))
    if level and level > 0 and stream.get("codec_name") in ("h264", "hevc"):
        return f"{profile}@L{level / 10:.1f}" if level >= 10 else f"{profile}@L{level}"
    return str(profile)


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_fraction(value) -> float | None:
    """`30000/1001` do ffprobe vira 29.97."""
    if not value or "/" not in str(value):
        return _as_float(value)
    num, _, den = str(value).partition("/")
    top, bottom = _as_float(num), _as_float(den)
    if not top or not bottom:
        return None
    return top / bottom


# ------------------------------------------------------------------ formatação

#: nome bonito do codec; o que não estiver aqui sai em maiúsculas
CODEC_NAMES: dict[str, str] = {
    "h264": "AVC",
    "hevc": "HEVC",
    "av1": "AV1",
    "vp9": "VP9",
    "vp8": "VP8",
    "mpeg4": "MPEG-4",
    "mpeg2video": "MPEG-2",
    "wmv3": "WMV",
    "vc1": "VC-1",
    "theora": "Theora",
    "prores": "ProRes",
    "aac": "AAC",
    "ac3": "AC-3",
    "eac3": "E-AC-3",
    "mp3": "MP3",
    "opus": "Opus",
    "flac": "FLAC",
    "vorbis": "Vorbis",
    "dts": "DTS",
    "truehd": "TrueHD",
    "pcm_s16le": "PCM",
    "wmav2": "WMA",
}


def codec_name(codec: str | None) -> str:
    if not codec:
        return "—"
    return CODEC_NAMES.get(codec.lower(), codec.upper())


def format_duration(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def format_bitrate(bits_per_second: int | None) -> str | None:
    if not bits_per_second or bits_per_second <= 0:
        return None
    if bits_per_second >= 10_000_000:
        return f"{i18n.format_number(bits_per_second / 1_000_000, 1)} Mbps"
    return f"{i18n.format_number(bits_per_second / 1000, 0)} Kbps"


def format_fps(fps: float) -> str:
    return f"{i18n.format_number(fps, 3 if fps % 1 else 0)} fps"


def format_sample_rate(hertz: int | None) -> str | None:
    if not hertz or hertz <= 0:
        return None
    khz = hertz / 1000
    return f"{i18n.format_number(khz, 0 if khz % 1 == 0 else 1)} KHz"


def format_modified(timestamp: float) -> str | None:
    if not timestamp:
        return None
    return time.strftime(tr("format.file_datetime"), time.localtime(timestamp))


def _join(parts: list[str | None]) -> str:
    return ", ".join(p for p in parts if p)


def header_lines(info: VideoInfo, selection) -> list[tuple[str, str]]:
    """Pares (rótulo, valor) do cabeçalho, na ordem, já traduzidos.

    Linha sem nada para dizer (codec que o ffprobe não achou, vídeo sem áudio)
    é omitida em vez de sair vazia.
    """
    chosen = set(normalize(selection))
    lines: list[tuple[str, str]] = []

    def add(key: str, value: str | None) -> None:
        if key in chosen and value:
            lines.append((tr(f"sheet.header.{key}"), value))

    add("name", info.path.name)

    size_parts: list[str | None] = [format_size(info.size_bytes) if info.size_bytes else None]
    if "bitrate" in chosen:
        size_parts.append(format_bitrate(info.container_bitrate))
    if "modified" in chosen:
        size_parts.append(format_modified(info.modified))
    add("size", " · ".join(p for p in size_parts if p))

    if info.width and info.height:
        resolution = f"{info.width}x{info.height}"
        if info.fps > 0:
            resolution += f" / {format_fps(info.fps)}"
        add("resolution", resolution)
    add("duration", format_duration(info.duration) if info.duration > 0 else None)

    if "video" in chosen and info.video_codec:
        codec = codec_name(info.video_codec)
        if info.video_profile:
            codec += f" ({info.video_profile})"
        parts: list[str | None] = [
            codec,
            format_bitrate(info.video_bitrate),
            format_fps(info.fps) if info.fps > 0 else None,
        ]
        if "pixel_format" in chosen:
            parts.append(_pixel_format(info))
        add("video", _join(parts))

    if "audio" in chosen and info.audio_codec:
        codec = codec_name(info.audio_codec)
        if info.audio_profile and info.audio_profile.lower() not in codec.lower():
            codec += f" ({info.audio_profile})"
        parts = [
            codec,
            format_bitrate(info.audio_bitrate),
            format_sample_rate(info.audio_sample_rate),
            _channels(info.audio_channels),
        ]
        if "audio_streams" in chosen and info.audio_streams > 1:
            parts.append(tr("sheet.value.streams", n=info.audio_streams))
        add("audio", _join(parts))

    return lines


def _pixel_format(info: VideoInfo) -> str | None:
    """`8 bit, yuv420p` — a profundidade sai do nome do formato quando falta."""
    if not info.pixel_format:
        return None
    depth = info.bit_depth
    if not depth:
        for suffix, bits in (("12", 12), ("10", 10)):
            if suffix in info.pixel_format:
                depth = bits
                break
        else:
            depth = 8
    return f"{tr('sheet.value.bit_depth', n=depth)} {info.pixel_format}"


def _channels(channels: int | None) -> str | None:
    if not channels or channels <= 0:
        return None
    key = "sheet.value.channel" if channels == 1 else "sheet.value.channels"
    return tr(key, n=channels)
