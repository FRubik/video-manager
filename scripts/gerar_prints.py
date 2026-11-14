"""Gera os prints do README a partir do próprio programa.

    uv run python scripts/gerar_prints.py                      # vídeos sintéticos
    uv run python scripts/gerar_prints.py --videos ~/filmes    # vídeos de verdade

Abre a janela de verdade, sem tela (`QT_QPA_PLATFORM=offscreen`), e salva a
tela inicial, a de revisão e uma folha gerada, em inglês e em português, em
`assets/prints/`. Rode de novo quando a interface mudar, e confira as imagens
antes de commitar.

Os prints do README usam os filmes abertos da Blender Foundation (Big Buck
Bunny, Sintel, Tears of Steel, CC BY 3.0), que não vão para o repositório:
baixe-os e passe a pasta em `--videos`. Sem ela, saem vídeos sintéticos.

Nada é escrito na pasta passada em `--videos`: os vídeos entram por link
simbólico, com o nome limpo, numa pasta temporária, e as folhas, o histórico e
a config ficam lá. Os nomes aparecem no print, por isso a limpeza.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# o pacote antes do cv2: ele guarda o ambiente antes de o cv2 reescrevê-lo
from video_manager import config, i18n, library, thumbs  # noqa: E402, I001

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SAIDA = RAIZ / "assets" / "prints"
#: caminho curto e legível, porque aparece nos campos de pasta do print
DEMO = Path(tempfile.gettempdir()) / "video-manager-demo"

#: nome -> (cor base BGR, quantos círculos)
VIDEOS = {
    "beach_trip_2023.mp4": ((200, 150, 40), 3),
    "birthday_party.mp4": ((60, 80, 200), 5),
    "concert_front_row.mkv": ((140, 40, 120), 4),
    "drone_mountains.mp4": ((90, 140, 60), 2),
    "family_dinner.mov": ((40, 120, 190), 3),
    "screen_recording_old.mp4": ((110, 110, 110), 1),
}


def _video(path: Path, cor: tuple[int, int, int], bolas: int) -> None:
    """Uns segundos de cena em movimento, para a grade ter o que mostrar."""
    w, h, fps, n = 640, 360, 24, 24 * 8
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    y = np.linspace(0, 1, h)[:, None, None]
    base = np.array(cor, dtype=np.float32)
    for i in range(n):
        fase = i / n
        frame = (base * (0.45 + 0.55 * y) * (0.7 + 0.3 * np.cos(fase * 6.28))).astype(np.uint8)
        frame = np.repeat(frame, w, axis=1).copy()
        for b in range(bolas):
            cx = int((0.15 + 0.7 * ((fase + b / bolas) % 1)) * w)
            cy = int(h * (0.35 + 0.3 * np.sin(fase * 6.28 + b)))
            cv2.circle(frame, (cx, cy), 28 + 8 * b, (235, 235, 235), -1, cv2.LINE_AA)
        cv2.rectangle(frame, (0, int(h * 0.8)), (w, h), tuple(int(c * 0.4) for c in cor), -1)
        writer.write(frame)
    writer.release()


#: pedaços de nome de arquivo que não dizem nada no print
_RUIDO = re.compile(r"^(\d{3,4}p|4k|hd|stereo)$", re.IGNORECASE)


def nome_limpo(arquivo: Path) -> str:
    """`Sintel - Open Movie by … [eRsGyueVLvQ].webm` -> `Sintel.webm`."""
    stem = re.sub(r"\[[^\]]*\]", "", arquivo.stem).split(" - ")[0]
    palavras = [p for p in stem.replace("_", " ").split() if not _RUIDO.match(p)]
    stem = " ".join(palavras) or arquivo.stem
    if stem.islower():
        stem = stem.title()
    return stem + arquivo.suffix.lower()


def _preparar(origem: Path | None) -> tuple[Path, Path]:
    shutil.rmtree(DEMO, ignore_errors=True)
    videos = DEMO / "videos"
    videos.mkdir(parents=True)
    if origem is None:
        for nome, (cor, bolas) in VIDEOS.items():
            _video(videos / nome, cor, bolas)
    else:
        for arquivo in library.list_videos(origem):
            (videos / nome_limpo(arquivo)).symlink_to(arquivo.resolve())
        if not library.list_videos(videos):
            raise SystemExit(f"nenhum vídeo em {origem}")
    thumbs_dir = videos / "thumbs"
    # a grade padrão do programa, para o print mostrar o que o usuário verá
    opts = thumbs.ThumbOptions(workers=4)
    falhas = [r for r in thumbs.generate(library.list_videos(videos), thumbs_dir, opts) if not r.ok]
    if falhas:
        raise SystemExit(f"folhas falharam: {[(r.video.name, r.error) for r in falhas]}")
    return videos, thumbs_dir


def _salvar(widget, nome: str) -> None:
    QApplication.processEvents()
    caminho = SAIDA / nome
    if not widget.grab().save(str(caminho)):
        raise SystemExit(f"não consegui salvar {caminho}")
    print(caminho.relative_to(RAIZ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--videos", type=Path, help="pasta com os vídeos dos prints")
    parser.add_argument(
        "--folha", help="vídeo cuja folha vira print (nome já limpo; padrão: o primeiro)"
    )
    args = parser.parse_args()
    origem = args.videos.expanduser() if args.videos else None
    if origem is not None and not origem.is_dir():
        raise SystemExit(f"pasta não encontrada: {origem}")

    app = QApplication.instance() or QApplication([])
    config.CONFIG_PATH = DEMO / "config" / "config.json"
    from video_manager.app import MainWindow

    SAIDA.mkdir(parents=True, exist_ok=True)
    for idioma in ("en", "pt"):
        # a faixa da folha sai no idioma corrente
        i18n.set_language(idioma)
        videos, thumbs_dir = _preparar(origem)
        config.Config(language=idioma, videos_dir=str(videos), thumbs_dir=str(thumbs_dir)).save()
        folha = args.folha or library.list_videos(videos)[0].name
        shutil.copyfile(
            thumbs_dir / library.thumb_output_name(Path(folha)), SAIDA / f"sheet-{idioma}.jpg"
        )
        print(f"assets/prints/sheet-{idioma}.jpg")
        janela = MainWindow()
        janela.resize(1280, 820)
        janela.show()
        _salvar(janela, f"setup-{idioma}.png")

        janela.on_start(janela.setup_view.current_config())
        revisao = janela.review_view
        # umas decisões já tomadas, para a lista mostrar os estados
        revisao.decide(library.KEEP)
        revisao.decide(library.DELETE)
        _salvar(janela, f"review-{idioma}.png")

        revisao.discard_saved_session()
        janela.hide()
        janela.deleteLater()
        QApplication.processEvents()
    shutil.rmtree(DEMO, ignore_errors=True)
    del app


if __name__ == "__main__":
    main()
