"""Ícone da aplicação, lido dos arquivos instalados junto do pacote."""

from __future__ import annotations

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
