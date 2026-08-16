"""Ícone da aplicação, lido dos arquivos instalados junto do pacote."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon

#: nome do ícone no tema do sistema e no `Icon=` do arquivo .desktop
ICON_NAME = "video-manager"

#: precisa bater com o nome do .desktop instalado: é por ele que o compositor
#: Wayland liga a janela ao ícone do menu (o `setWindowIcon` sozinho não basta)
DESKTOP_FILE_NAME = "video-manager"

ICON_DIR = Path(__file__).parent / "icons"


def app_icon() -> QIcon:
    """O ícone em todas as resoluções que existirem na pasta.

    Entregar cada PNG separado, em vez de um só grande, deixa o Qt escolher o
    tamanho mais próximo do que cada contexto pede — o 16px desenhado à mão não
    vira um borrão quando a barra de tarefas pede um ícone pequeno.

    O tema do sistema tem precedência: se o ícone já estiver instalado em
    `~/.local/share/icons`, é a versão de lá que aparece.
    """
    icon = QIcon.fromTheme(ICON_NAME)
    if not icon.isNull():
        return icon

    icon = QIcon()
    for png in sorted(ICON_DIR.glob(f"hicolor/*/apps/{ICON_NAME}.png")):
        icon.addFile(str(png))
    return icon


def desktop_entry_installed() -> bool:
    """Existe um `<DESKTOP_FILE_NAME>.desktop` nos diretórios XDG?

    Serve para só declarar o nome do .desktop quando ele de fato existe. O Qt
    usa esse nome para se registrar no portal do freedesktop, e o portal
    responde com um erro barulhento no stderr quando não encontra o arquivo
    correspondente — o que é o caso normal de quem roda o projeto sem instalar
    a entrada de menu.
    """
    if not sys.platform.startswith(("linux", "freebsd")):
        return False

    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for data_dir in [home, *system.split(":")]:
        if data_dir and (Path(data_dir) / "applications" / f"{DESKTOP_FILE_NAME}.desktop").is_file():
            return True
    return False
