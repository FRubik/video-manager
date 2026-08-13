"""Gerenciador de vídeos: geração de contact sheets e triagem visual."""

import os

__version__ = "0.1.0"

# Cópia do ambiente antes de qualquer import pesado. O `import cv2` sobrescreve
# QT_QPA_PLATFORM_PLUGIN_PATH, QT_QPA_FONTDIR e LD_LIBRARY_PATH apontando para
# dentro do site-packages do OpenCV, que traz um único libqxcb.so ligado às
# libs Qt dele. Qualquer aplicativo Qt lançado como processo filho (o VLC, por
# exemplo) herdaria isso, tentaria carregar aquele plugin e abortaria com
# "Could not load the Qt platform plugin xcb".
#
# Este módulo é executado antes de qualquer submódulo do pacote, então a cópia
# aqui é feita necessariamente antes do cv2 entrar em cena.
PRISTINE_ENV: dict[str, str] = dict(os.environ)
