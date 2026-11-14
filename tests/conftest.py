"""Ambiente comum da suíte: Qt sem janela e um HOME descartável.

O HOME é trocado **antes** de importar o `video_manager`: o `CONFIG_PATH` é
calculado na importação a partir dele, e a `MainWindow` grava a config sozinha
ao iniciar uma sessão. Sem isto, rodar os testes sobrescreveria a config real
de quem roda (já aconteceu num teste manual, em 16/08/2026).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_HOME = Path(tempfile.mkdtemp(prefix="video-manager-testes-"))
os.environ["HOME"] = str(_HOME)

# o pacote primeiro: ele guarda o ambiente antes de o cv2 reescrevê-lo
from video_manager import config, i18n  # noqa: E402, I001

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

assert str(config.CONFIG_PATH).startswith(str(_HOME)), "config fora do HOME de teste"

#: referência de módulo: se o QApplication for coletado, o processo aborta
#: na criação do primeiro widget
_APP = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _idioma_e_config(tmp_path, monkeypatch):
    """Cada teste começa em inglês e com uma config própria."""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config" / "config.json")
    i18n.set_language("en")
    yield
    i18n.set_language("en")


@pytest.fixture
def qapp():
    return _APP


def make_video(path: Path, *, frames: int = 48, fps: float = 24.0, size=(160, 120)) -> Path:
    """Vídeo sintético: cada frame tem uma cor diferente, para a grade não sair uniforme."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not writer.isOpened():
        pytest.skip("o OpenCV desta máquina não grava mp4v")
    w, h = size
    for i in range(frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = ((i * 5) % 256, (i * 11) % 256, 255 - (i * 5) % 256)
        cv2.putText(frame, str(i), (10, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    return path
