"""Ponto de entrada: `uv run video-manager` ou `python -m video_manager`."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .app import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    # nome do processo/janela no sistema: fica igual em qualquer idioma
    app.setApplicationName("Video Manager")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
