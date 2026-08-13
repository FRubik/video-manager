#!/usr/bin/env python
"""Atalho para abrir o programa: `uv run videos.py` dentro desta pasta.

Equivale a `uv run video-manager` — existe só para o caso de você preferir
rodar um arquivo, como no comic-translate.
"""

from video_manager.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
