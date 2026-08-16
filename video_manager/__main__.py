"""Ponto de entrada: `uv run video-manager` ou `python -m video_manager`."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .app import MainWindow
from .icons import DESKTOP_FILE_NAME, app_icon


def main() -> int:
    # antes do QApplication: no Wayland é o app_id que o compositor usa para
    # casar a janela com o .desktop, e ele é lido na criação da aplicação
    QApplication.setDesktopFileName(DESKTOP_FILE_NAME)

    app = QApplication(sys.argv)
    # nome do processo/janela no sistema: fica igual em qualquer idioma
    app.setApplicationName("Video Manager")
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
