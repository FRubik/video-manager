"""Ponta a ponta: vídeos sintéticos → folhas → revisão na janela → arquivos movidos.

Roda a `MainWindow` de verdade (sem tela) e confere o que o usuário veria no
disco: a folha gerada, o vídeo descartado na quarentena, o "talvez" na pasta
dele e o histórico gravado. Os diálogos de confirmação são respondidos com
"Sim"; o resto do fluxo é o do programa.
"""

from __future__ import annotations

from PIL import Image
from PySide6.QtWidgets import QMessageBox

from video_manager import library, thumbs
from video_manager.app import MainWindow
from video_manager.config import Config
from video_manager.library import DELETE, KEEP, MAYBE, ReviewState

from .conftest import make_video


def _pastas(tmp_path):
    videos = tmp_path / "videos"
    for nome in ("praia.mp4", "festa.mp4", "viagem.mp4"):
        make_video(videos / nome)
    return videos, tmp_path / "thumbs"


def test_gera_folha_com_a_grade_pedida(tmp_path):
    videos, thumbs_dir = _pastas(tmp_path)
    opts = thumbs.ThumbOptions(n_rows=2, n_cols=3, cell_height=60, workers=2, header=False)
    progresso = []
    resultados = thumbs.generate(
        library.list_videos(videos), thumbs_dir, opts, progress=lambda d, t, r: progresso.append(d)
    )
    assert all(r.ok for r in resultados), [r.error for r in resultados]
    assert sorted(progresso) == [1, 2, 3]

    folha = Image.open(thumbs_dir / "praia.mp4.jpg")
    # 3 colunas de 160x120 reduzidas a 60 px de altura = 80 px, mais os espaços
    largura_celula = 80
    assert folha.width >= 3 * largura_celula and folha.height >= 2 * 60
    assert folha.width < 4 * largura_celula and folha.height < 3 * 60


def test_video_ilegivel_vira_falha_e_nao_folha(tmp_path):
    ruim = tmp_path / "videos" / "corrompido.mp4"
    ruim.parent.mkdir(parents=True)
    ruim.write_bytes(b"isto nao e um video")
    resultado = thumbs.extract_sheet(ruim, tmp_path / "thumbs", thumbs.ThumbOptions())
    assert not resultado.ok and resultado.error
    assert not (tmp_path / "thumbs" / "corrompido.mp4.jpg").exists()


def test_revisao_completa_move_os_arquivos(tmp_path, qapp, monkeypatch):
    videos, thumbs_dir = _pastas(tmp_path)
    opts = thumbs.ThumbOptions(n_rows=2, n_cols=2, cell_height=50, workers=2)
    assert all(r.ok for r in thumbs.generate(library.list_videos(videos), thumbs_dir, opts))

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    avisos = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[1]))
    )
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[1])))

    janela = MainWindow()
    cfg = Config(videos_dir=str(videos), thumbs_dir=str(thumbs_dir), generate_thumbs=False)
    janela.on_start(cfg)
    revisao = janela.review_view
    assert janela.stack.currentWidget() is revisao
    # ordem alfabética: festa, praia, viagem
    assert [e.name for e in revisao.entries] == ["festa.mp4", "praia.mp4", "viagem.mp4"]

    revisao.decide(DELETE)
    revisao.decide(MAYBE)
    # no meio da sessão o autosave já guardou as decisões
    salva = library.load_session(thumbs_dir)
    assert salva is not None and salva.decided == 2
    revisao.decide(KEEP)  # último: oferece aplicar, e o "Sim" aplica

    lixo = library.default_trash_dir(videos)
    talvez = library.default_maybe_dir(videos)
    assert (lixo / "festa.mp4").exists()
    assert (talvez / "praia.mp4").exists()
    assert (videos / "viagem.mp4").exists()
    assert not (videos / "festa.mp4").exists()

    state = ReviewState(thumbs_dir)
    assert state.decision_of("festa.mp4") == DELETE
    assert state.decision_of("praia.mp4") == MAYBE
    assert state.decision_of("viagem.mp4") == KEEP
    assert library.load_session(thumbs_dir) is None
    assert janela.stack.currentWidget() is janela.setup_view
    assert avisos  # o resumo final apareceu

    # a sessão seguinte só tem o que ficou no "talvez"
    janela.on_start(Config(videos_dir=str(videos), thumbs_dir=str(thumbs_dir), only_maybe=True))
    assert [e.name for e in revisao.entries] == ["praia.mp4"]
    janela.close()
