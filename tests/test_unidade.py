"""Testes de unidade: funções puras de varredura, histórico, nomes e formatação."""

from __future__ import annotations

import json

import numpy as np
import pytest

from video_manager import config, i18n, library, metadata, shortcuts, thumbs
from video_manager.library import DELETE, KEEP, MAYBE, ReviewState, VideoEntry


def _touch(path, size=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


# ------------------------------------------------------------- varredura
def test_list_videos_so_primeiro_nivel_e_ordem_alfabetica(tmp_path):
    _touch(tmp_path / "b.MP4")
    _touch(tmp_path / "A.mkv")
    _touch(tmp_path / "notas.txt")
    _touch(tmp_path / "sub" / "c.mp4")
    assert [p.name for p in library.list_videos(tmp_path)] == ["A.mkv", "b.MP4"]


def test_list_videos_pasta_inexistente(tmp_path):
    assert library.list_videos(tmp_path / "nao-existe") == []


def test_find_thumb_aceita_as_duas_convencoes(tmp_path):
    thumbs_dir = tmp_path / "thumbs"
    _touch(thumbs_dir / "um.mp4.jpg")
    _touch(thumbs_dir / "dois.png")
    index = library.index_thumbs(thumbs_dir)
    assert library.find_thumb(tmp_path / "um.mp4", index).name == "um.mp4.jpg"
    assert library.find_thumb(tmp_path / "dois.mkv", index).name == "dois.png"
    assert library.find_thumb(tmp_path / "tres.mp4", index) is None


def test_scan_inclui_talvez_marcado(tmp_path):
    videos, thumbs_dir, maybe = tmp_path / "v", tmp_path / "t", tmp_path / "v" / "_talvez"
    _touch(videos / "a.mp4")
    _touch(maybe / "b.mp4")
    _touch(thumbs_dir / "a.mp4.jpg")
    entries = library.scan(videos, thumbs_dir, maybe)
    assert [(e.name, e.from_maybe, e.thumb is not None) for e in entries] == [
        ("a.mp4", False, True),
        ("b.mp4", True, False),
    ]
    assert len(library.scan(videos, thumbs_dir)) == 1


# ------------------------------------------------------------- histórico
def test_review_state_persiste_e_so_decisao_final_conta(tmp_path):
    state = ReviewState(tmp_path)
    state.record("a.mp4", KEEP, 100)
    state.record("b.mp4", MAYBE, 50)
    state.save()
    relido = ReviewState(tmp_path)
    assert relido.was_reviewed("a.mp4")
    assert not relido.was_reviewed("b.mp4")
    assert relido.decision_of("b.mp4") == MAYBE


def test_review_state_rename_leva_o_registro(tmp_path):
    state = ReviewState(tmp_path)
    state.record("velho.mp4", DELETE, 10)
    state.rename("velho.mp4", "novo.mp4")
    assert state.was_reviewed("novo.mp4") and not state.was_reviewed("velho.mp4")


def test_review_state_arquivo_corrompido_vira_vazio(tmp_path):
    (tmp_path / library.STATE_FILE).write_text("{ não é json", encoding="utf-8")
    assert ReviewState(tmp_path).reviewed == {}


def test_build_session_filtra_e_sorteia_em_ordem(tmp_path):
    state = ReviewState(tmp_path)
    state.record("c.mp4", KEEP)
    entries = [VideoEntry(tmp_path / f"{n}.mp4", thumb=tmp_path / f"{n}.jpg") for n in "abcdef"] + [
        VideoEntry(tmp_path / "sem.mp4")
    ]
    todos = library.build_session(
        entries, state, random_session=False, session_size=0, skip_reviewed=True
    )
    assert [e.name for e in todos] == ["a.mp4", "b.mp4", "d.mp4", "e.mp4", "f.mp4"]

    sorteio = library.build_session(
        entries, state, random_session=True, session_size=3, skip_reviewed=True
    )
    nomes = [e.name for e in sorteio]
    assert len(nomes) == 3 and nomes == sorted(nomes)


def test_sessao_salva_e_retomada(tmp_path):
    entries = [VideoEntry(tmp_path / f"{n}.mp4") for n in "abc"]
    entries[0].decision = DELETE
    library.save_session(
        tmp_path,
        entries,
        1,
        videos_dir=tmp_path,
        trash_dir=tmp_path / "t",
        maybe_dir=tmp_path / "m",
    )
    salva = library.load_session(tmp_path)
    assert salva.total == 3 and salva.decided == 1 and salva.index == 1

    # "a" sumiu da pasta: a sessão encurta e o índice acompanha
    atuais = [VideoEntry(tmp_path / f"{n}.mp4") for n in "bc"]
    sessao, indice, sumidos = library.restore_session(salva, atuais)
    assert [e.name for e in sessao] == ["b.mp4", "c.mp4"]
    assert (indice, sumidos) == (0, 1)

    library.clear_session(tmp_path)
    assert library.load_session(tmp_path) is None


def test_load_session_descarta_decisao_invalida(tmp_path):
    (tmp_path / library.SESSION_FILE).write_text(
        json.dumps({"items": [{"name": "a.mp4", "decision": "explodir"}], "index": 9}),
        encoding="utf-8",
    )
    salva = library.load_session(tmp_path)
    assert salva.items[0]["decision"] is None and salva.index == 0


def test_collect_stats_taxa_e_projecao(tmp_path):
    state = ReviewState(tmp_path)
    for i in range(4):
        state.record(f"apagado{i}.mp4", DELETE, 300)
    state.record("mantido.mp4", KEEP, 100)
    pendente = VideoEntry(_touch(tmp_path / "pendente.mp4", 1000))
    stats = library.collect_stats([pendente], state)
    assert stats.decided_count == 5
    assert stats.discard_rate == pytest.approx(1200 / 1300)
    assert stats.pending_bytes == 1000
    assert stats.estimated_remaining is not None


# ------------------------------------------------------- nomes e arquivos
def test_unique_destination_numera(tmp_path):
    _touch(tmp_path / "a.mp4")
    _touch(tmp_path / "a (2).mp4")
    assert library.unique_destination(tmp_path / "a.mp4").name == "a (3).mp4"
    assert library.unique_destination(tmp_path / "b.mp4").name == "b.mp4"


@pytest.mark.parametrize(
    ("bruto", "limpo"),
    [("  nome/ruim:*? ", "nomeruim"), ("...", ""), ("ok.final.", "ok.final"), ("a\tb", "ab")],
)
def test_clean_stem(bruto, limpo):
    assert library.clean_stem(bruto) == limpo


def test_free_pair_e_rename_pair_mantem_a_convencao(tmp_path):
    video = _touch(tmp_path / "v" / "velho.mp4")
    thumb = _touch(tmp_path / "t" / "velho.mp4.jpg")
    _touch(tmp_path / "v" / "novo.mp4")  # ocupado: numera
    index = library.index_thumbs(tmp_path / "t")
    novo_video, nova_thumb = library.free_pair(video, thumb, "novo", index)
    assert (novo_video.name, nova_thumb.name) == ("novo (2).mp4", "novo (2).mp4.jpg")
    library.rename_pair(video, thumb, novo_video, nova_thumb)
    assert novo_video.exists() and nova_thumb.exists()
    assert not video.exists() and not thumb.exists()


def test_free_pair_nao_adota_thumb_orfa(tmp_path):
    video = _touch(tmp_path / "v" / "a.mp4")
    _touch(tmp_path / "t" / "b.mp4.jpg")  # folha de um vídeo que já foi apagado
    index = library.index_thumbs(tmp_path / "t")
    novo_video, _ = library.free_pair(video, None, "b", index)
    assert novo_video.name == "b (2).mp4"


def test_move_video_registra_no_log(tmp_path):
    video = _touch(tmp_path / "a.mp4")
    destino = library.move_video(video, tmp_path / "lixo", DELETE)
    assert destino.exists() and not video.exists()
    linha = json.loads((tmp_path / "lixo" / library.TRASH_LOG).read_text(encoding="utf-8"))
    assert linha["motivo"] == DELETE and linha["destino"] == str(destino)


def test_empty_trash_leva_so_as_thumbs_dos_apagados(tmp_path):
    _touch(tmp_path / "lixo" / "a.mp4", 100)
    _touch(tmp_path / "t" / "a.mp4.jpg", 5)
    _touch(tmp_path / "t" / "pendente.mp4.jpg", 5)
    assert library.empty_trash(tmp_path / "lixo", tmp_path / "t") == (1, 105)
    assert (tmp_path / "t" / "pendente.mp4.jpg").exists()


def test_launch_env_tira_caminhos_do_qt_do_opencv(monkeypatch):
    import video_manager

    monkeypatch.setitem(video_manager.PRISTINE_ENV, "QT_PLUGIN_PATH", "/x/site-packages/cv2/qt")
    monkeypatch.setitem(video_manager.PRISTINE_ENV, "QT_QPA_FONTDIR", "/usr/share/fonts")
    env = library.launch_env()
    assert "QT_PLUGIN_PATH" not in env and env["QT_QPA_FONTDIR"] == "/usr/share/fonts"


# ------------------------------------------------------------ formatação
def test_format_size_nos_dois_idiomas():
    assert library.format_size(512) == "512 B"
    assert library.format_size(1536) == "1.5 KB"
    i18n.set_language("pt")
    assert library.format_size(1536) == "1,5 KB"
    assert i18n.format_number(1234.5, 1) == "1.234,5"


def test_traducoes_completas():
    faltando = [k for k, v in i18n.STRINGS.items() if set(v) != set(i18n.LANGUAGES)]
    assert faltando == []


def test_tr_chave_desconhecida_aparece_crua():
    assert i18n.tr("nao.existe") == "nao.existe"


def test_formatos_de_metadados():
    assert metadata.format_duration(3725.9) == "01:02:05"
    assert metadata.format_bitrate(12_500_000) == "12.5 Mbps"
    assert metadata.format_bitrate(800_000) == "800 Kbps"
    assert metadata.format_bitrate(None) is None
    assert metadata.format_fps(29.97) == "29.970 fps"
    assert metadata.format_sample_rate(44100) == "44.1 KHz"
    assert thumbs.format_seconds(61) == "00:01:01"


def test_metadata_normalize_exige_o_pai():
    assert metadata.normalize(["bitrate", "name"]) == ["name"]
    assert metadata.normalize("lixo") == metadata.DEFAULTS


def test_header_lines_omite_o_que_nao_tem(tmp_path):
    info = metadata.VideoInfo(tmp_path / "x.mp4", width=640, height=360, fps=25.0, duration=90)
    linhas = dict(metadata.header_lines(info, metadata.DEFAULTS))
    assert "640x360 / 25 fps" in linhas.values()
    assert "00:01:30" in linhas.values()
    assert len(linhas) == 3  # nome, resolução, duração; sem tamanho nem codecs


# --------------------------------------------------------------- atalhos
def test_shortcuts_normalize_completa_e_canoniza():
    mapa = shortcuts.normalize({"keep": "k", "inexistente": "X"})
    assert mapa["keep"] == "K" and mapa["delete"] == shortcuts.DEFAULTS["delete"]
    assert "inexistente" not in mapa


def test_shortcuts_conflitos():
    mapa = dict(shortcuts.DEFAULTS, keep="Q")
    assert [tecla for tecla, _ in shortcuts.conflicts(mapa)] == ["Q"]
    assert shortcuts.conflicts(shortcuts.DEFAULTS) == []


# ---------------------------------------------------------------- config
def test_config_ida_e_volta_ignora_chave_desconhecida():
    cfg = config.Config(videos_dir="/videos", n_rows=3)
    cfg.save()
    raw = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
    raw["chave_antiga"] = 1
    config.CONFIG_PATH.write_text(json.dumps(raw), encoding="utf-8")
    relida = config.Config.load()
    assert relida.videos_dir == "/videos" and relida.n_rows == 3


# --------------------------------------------------------------- folhas
def test_header_height_acha_a_faixa():
    folha = np.zeros((100, 300, 3), dtype=np.uint8)
    folha[:20] = thumbs.HEADER_BG
    assert thumbs.header_height(folha) == 20
    assert thumbs.header_height(np.zeros((50, 300, 3), dtype=np.uint8)) == 0
