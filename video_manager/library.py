"""Varredura das pastas, pareamento vídeo↔thumbnail, histórico e quarentena."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

VIDEO_EXTS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv",
    ".flv", ".m4v", ".mpg", ".mpeg", ".ts", ".3gp",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

STATE_FILE = ".video_manager_state.json"
SESSION_FILE = ".video_manager_session.json"
TRASH_LOG = "_movimentos.jsonl"

KEEP = "keep"
DELETE = "delete"
MAYBE = "maybe"

#: decisões finais — só elas contam como "já revisado"
FINAL_DECISIONS = (KEEP, DELETE)

#: abaixo disso a taxa de descarte é ruído (com 1 decisão ela seria 0% ou 100%)
MIN_DECIDED_FOR_RATE = 5


@dataclass
class VideoEntry:
    """Um vídeo da pasta e a thumbnail correspondente (quando existe)."""

    video: Path
    thumb: Path | None = None
    decision: str | None = None  # None | KEEP | DELETE | MAYBE
    #: veio da pasta "talvez", e volta para a pasta de vídeos se for mantido
    from_maybe: bool = False
    _size: int | None = field(default=None, repr=False, compare=False)

    @property
    def name(self) -> str:
        return self.video.name

    @property
    def size_bytes(self) -> int:
        """Tamanho em bytes, lido uma vez só.

        O cache não é só desempenho: depois de aplicar a sessão o arquivo já
        saiu do caminho original, e as estatísticas ainda precisam do número.
        """
        if self._size is None:
            try:
                self._size = self.video.stat().st_size
            except OSError:
                self._size = 0
        return self._size

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


def format_size(num_bytes: float) -> str:
    """Tamanho legível no formato brasileiro (`1.234,5 GB`)."""
    valor = float(num_bytes)
    unidade = "B"
    for proxima in ("KB", "MB", "GB", "TB"):
        if abs(valor) < 1024:
            break
        valor /= 1024
        unidade = proxima
    texto = f"{valor:,.{0 if unidade == 'B' else 1}f}"
    # de 1,234.5 (padrão do Python) para 1.234,5
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".") + f" {unidade}"


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


def scan(videos_dir: Path, thumbs_dir: Path, maybe_dir: Path | None = None) -> list[VideoEntry]:
    """Vídeos da pasta principal e, opcionalmente, os que estão no "talvez".

    Como `list_videos` só olha o primeiro nível, o "talvez" padrão (uma
    subpasta dos vídeos) não é varrido duas vezes.
    """
    index = index_thumbs(thumbs_dir)
    entries = [VideoEntry(video=v, thumb=find_thumb(v, index)) for v in list_videos(videos_dir)]
    if maybe_dir is not None and maybe_dir.is_dir():
        entries += [
            VideoEntry(video=v, thumb=find_thumb(v, index), from_maybe=True)
            for v in list_videos(maybe_dir)
        ]
    return entries


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
        """Só decisão final conta: o "talvez" existe justamente para voltar."""
        return self.decision_of(name) in FINAL_DECISIONS

    def decision_of(self, name: str) -> str | None:
        entry = self.reviewed.get(name)
        return entry.get("decision") if isinstance(entry, dict) else None

    def record(self, name: str, decision: str, size_bytes: int = 0) -> None:
        self.reviewed[name] = {
            "decision": decision,
            "at": datetime.now().isoformat(timespec="seconds"),
            # guardado para as estatísticas de volume: depois de mover o vídeo
            # não há mais como medir o que saiu da pasta
            "size": size_bytes,
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


@dataclass
class SavedSession:
    """Uma sessão interrompida, guardada para ser retomada depois.

    Existe para o que o histórico não cobre: decisões que ainda não foram
    aplicadas e, sobretudo, a amostra de uma verificação randômica — aplicar
    no meio encerra aquele sorteio e devolve o resto ao bolo.
    """

    saved_at: str = ""
    videos_dir: str = ""
    trash_dir: str = ""
    maybe_dir: str = ""
    index: int = 0
    #: um por vídeo da sessão: {"name", "from_maybe", "decision"}
    items: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def decided(self) -> int:
        return sum(1 for item in self.items if item.get("decision"))

    @property
    def saved_at_label(self) -> str:
        """Data legível, ou o texto cru se não for uma data ISO."""
        try:
            return datetime.fromisoformat(self.saved_at).strftime("%d/%m às %H:%M")
        except ValueError:
            return self.saved_at


def session_path(thumbs_dir: Path) -> Path:
    return thumbs_dir / SESSION_FILE


def save_session(
    thumbs_dir: Path,
    entries: list[VideoEntry],
    index: int,
    *,
    videos_dir: Path,
    trash_dir: Path,
    maybe_dir: Path,
) -> None:
    """Grava a sessão em andamento ao lado do histórico.

    Só o nome de cada vídeo é guardado — o caminho é reencontrado na varredura
    da retomada, que é a mesma chave que o histórico já usa.
    """
    payload = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "videos_dir": str(videos_dir),
        "trash_dir": str(trash_dir),
        "maybe_dir": str(maybe_dir),
        "index": index,
        "items": [
            {"name": e.name, "from_maybe": e.from_maybe, "decision": e.decision}
            for e in entries
        ],
    }
    try:
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        session_path(thumbs_dir).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass  # não vale interromper a revisão por causa do autosave


def load_session(thumbs_dir: Path) -> SavedSession | None:
    """Sessão salva nessa pasta de thumbnails, ou None se não houver uma válida."""
    try:
        raw = json.loads(session_path(thumbs_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        return None
    decisoes = (KEEP, DELETE, MAYBE)
    items = [
        {
            "name": item["name"],
            "from_maybe": bool(item.get("from_maybe")),
            "decision": item["decision"] if item.get("decision") in decisoes else None,
        }
        for item in raw["items"]
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    if not items:
        return None
    index = raw.get("index")
    return SavedSession(
        saved_at=str(raw.get("saved_at", "")),
        videos_dir=str(raw.get("videos_dir", "")),
        trash_dir=str(raw.get("trash_dir", "")),
        maybe_dir=str(raw.get("maybe_dir", "")),
        index=index if isinstance(index, int) and 0 <= index < len(items) else 0,
        items=items,
    )


def clear_session(thumbs_dir: Path) -> None:
    try:
        session_path(thumbs_dir).unlink(missing_ok=True)
    except OSError:
        pass


def restore_session(
    saved: SavedSession, entries: list[VideoEntry]
) -> tuple[list[VideoEntry], int, int]:
    """Casa a sessão salva com a varredura atual.

    Retorna (vídeos da sessão, índice onde retomar, quantos sumiram da pasta).
    Um vídeo que mudou de pasta (do "talvez" para os vídeos, por exemplo) ainda
    é reconhecido pelo nome; um que não está mais em lugar nenhum sai da sessão,
    e o índice acompanha esse encurtamento.
    """
    por_chave = {(e.name, e.from_maybe): e for e in entries}
    por_nome: dict[str, VideoEntry] = {}
    for entry in entries:
        por_nome.setdefault(entry.name, entry)

    session: list[VideoEntry] = []
    index = 0
    missing = 0
    for position, item in enumerate(saved.items):
        entry = por_chave.get((item["name"], item["from_maybe"])) or por_nome.get(item["name"])
        if entry is None:
            missing += 1
            continue
        entry.decision = item["decision"]
        if position < saved.index:
            index += 1
        session.append(entry)
    return session, min(index, max(len(session) - 1, 0)), missing


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


@dataclass
class Stats:
    """Volume da pasta e o ritmo de descarte, para projetar o que vai sobrar."""

    total_count: int = 0
    total_bytes: int = 0
    #: ainda sem decisão final (o "talvez" conta como pendente, por definição)
    pending_count: int = 0
    pending_bytes: int = 0
    maybe_count: int = 0
    maybe_bytes: int = 0
    #: volume já decidido, somando histórico e sessão em andamento
    keep_bytes: int = 0
    delete_bytes: int = 0
    decided_count: int = 0
    #: o que está parado na quarentena, ainda ocupando disco
    trash_count: int = 0
    trash_bytes: int = 0
    #: marcado na sessão em andamento, ainda não aplicado
    session: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {d: (0, 0) for d in (KEEP, DELETE, MAYBE)}
    )

    def session_count(self, decision: str) -> int:
        return self.session[decision][0]

    def session_bytes(self, decision: str) -> int:
        return self.session[decision][1]

    @property
    def decided_bytes(self) -> int:
        return self.keep_bytes + self.delete_bytes

    @property
    def discard_rate(self) -> float | None:
        """Fração do volume decidido que foi para a quarentena.

        None enquanto a amostra for pequena demais para significar algo.
        """
        if self.decided_bytes <= 0 or self.decided_count < MIN_DECIDED_FOR_RATE:
            return None
        return self.delete_bytes / self.decided_bytes

    @property
    def estimated_remaining(self) -> int | None:
        """Quanto a pasta deve ter no fim, se o ritmo atual se mantiver.

        O que já foi descartado não está mais em `total_bytes`; encolhem
        apenas o que está marcado para sair e a parcela projetada do pendente.
        """
        rate = self.discard_rate
        if rate is None:
            return None
        sai_agora = self.session_bytes(DELETE)
        return round(self.total_bytes - sai_agora - self.pending_bytes * rate)


def folder_size(folder: Path) -> tuple[int, int]:
    """(quantidade, bytes) dos vídeos no primeiro nível da pasta."""
    total = 0
    videos = list_videos(folder)
    for video in videos:
        try:
            total += video.stat().st_size
        except OSError:
            pass
    return len(videos), total


def collect_stats(
    entries: list[VideoEntry],
    state: ReviewState,
    *,
    trash_dir: Path | None = None,
    session: list[VideoEntry] | None = None,
) -> Stats:
    """Estatísticas de volume da pasta varrida.

    `session` são as decisões ainda não aplicadas, que valem mais que o
    histórico para os mesmos vídeos — assim a projeção reage enquanto você
    revisa, e não só depois de aplicar.
    """
    pendente_na_sessao = {
        e.name: e.decision for e in (session or []) if e.decision is not None
    }

    # nome -> (decisão final, bytes); inclui vídeos que já saíram da pasta
    decididos: dict[str, tuple[str, int]] = {}
    for name, record in state.reviewed.items():
        if not isinstance(record, dict):
            continue
        decisao, tamanho = record.get("decision"), record.get("size")
        if decisao in FINAL_DECISIONS and isinstance(tamanho, int) and tamanho > 0:
            decididos[name] = (decisao, tamanho)

    stats = Stats()
    for entry in entries:
        stats.total_count += 1
        stats.total_bytes += entry.size_bytes
        if entry.from_maybe:
            stats.maybe_count += 1
            stats.maybe_bytes += entry.size_bytes

        decisao = pendente_na_sessao.get(entry.name)
        if decisao in FINAL_DECISIONS:
            decididos[entry.name] = (decisao, entry.size_bytes)
        elif decisao is None and state.was_reviewed(entry.name):
            # decidido antes e ainda na pasta: não é pendente. Se o histórico
            # não trouxe o tamanho, ele fica de fora da taxa — medir o arquivo
            # agora só puxaria a taxa para baixo, porque os descartes antigos
            # já saíram da pasta e não teriam a mesma chance de ser medidos.
            pass
        else:
            stats.pending_count += 1
            stats.pending_bytes += entry.size_bytes

    for decisao, tamanho in decididos.values():
        stats.decided_count += 1
        if decisao == KEEP:
            stats.keep_bytes += tamanho
        else:
            stats.delete_bytes += tamanho

    for entry in session or []:
        if entry.decision is None:
            continue
        quantos, bytes_ = stats.session[entry.decision]
        stats.session[entry.decision] = (quantos + 1, bytes_ + entry.size_bytes)

    if trash_dir is not None:
        stats.trash_count, stats.trash_bytes = folder_size(trash_dir)
    return stats


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


def move_video(video: Path, dest_dir: Path, motivo: str, log_dir: Path | None = None) -> Path:
    """Move o vídeo para a pasta indicada e registra o movimento em log.

    `log_dir` existe para a devolução de um vídeo do "talvez": o log pertence
    à pasta gerenciada pelo app, não à pasta de vídeos do usuário.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_destination(dest_dir / video.name)
    shutil.move(str(video), str(dest))
    _log_move(log_dir or dest_dir, video, dest, motivo)
    return dest


def _log_move(dest_dir: Path, origin: Path, dest: Path, motivo: str) -> None:
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "motivo": motivo,
        "origem": str(origin),
        "destino": str(dest),
    }
    try:
        with (dest_dir / TRASH_LOG).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def default_trash_dir(videos_dir: Path) -> Path:
    return videos_dir / "_para_apagar"


def default_maybe_dir(videos_dir: Path) -> Path:
    return videos_dir / "_talvez"


#: variáveis que o OpenCV reescreve e que envenenam qualquer app Qt filho
_QT_VARS_ENVENENADAS = (
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "QT_PLUGIN_PATH",
    "QT_QPA_FONTDIR",
    "LD_LIBRARY_PATH",
)


def launch_env() -> dict[str, str]:
    """Ambiente limpo para processos externos (ver PRISTINE_ENV em __init__)."""
    from . import PRISTINE_ENV

    env = dict(PRISTINE_ENV)
    # cinto de segurança: se o shell de origem já trazia algum desses caminhos
    # apontando para um site-packages, ele também não deve ir para o filho
    for var in _QT_VARS_ENVENENADAS:
        valor = env.get(var, "")
        if "site-packages" in valor or "/cv2/" in valor:
            env.pop(var, None)
    return env


def open_in_player(path: Path) -> tuple[bool, str]:
    """Abre o vídeo no player padrão do sistema.

    Entrega o caminho do arquivo diretamente ao abridor do sistema em vez de
    uma URL `file://`: players como o VLC recebem a URL via `%U` do .desktop e
    nomes com `#`, `%`, `&` ou espaços podem ser reinterpretados no caminho,
    resultando em "não foi possível abrir o arquivo".

    Retorna (sucesso, motivo da falha).
    """
    if not path.exists():
        return False, "o arquivo não está mais nesse caminho"

    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606 - API padrão do Windows
            return True, ""

        launcher = "open" if sys.platform == "darwin" else "xdg-open"
        executable = shutil.which(launcher)
        if executable is None:
            return False, f"`{launcher}` não foi encontrado no sistema"

        subprocess.Popen(
            [executable, str(path)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=launch_env(),
        )
        return True, ""
    except OSError as exc:
        return False, str(exc)
