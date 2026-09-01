"""Diálogo de escolha das informações do cabeçalho da folha."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from . import metadata
from .i18n import tr
from .metadata import FIELDS


class HeaderFieldsDialog(QDialog):
    """Uma linha por informação; as que só enriquecem outra ficam indentadas.

    Um filho (o bitrate na linha do tamanho, por exemplo) não tem linha própria
    na folha, então segue o pai: desmarcar o pai desabilita e desliga o filho.
    """

    def __init__(self, selection, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("header.title"))
        self._boxes: dict[str, QCheckBox] = {}

        chosen = set(metadata.normalize(selection))
        sem_ffprobe = not metadata.has_ffprobe()

        root = QVBoxLayout(self)
        intro = QLabel(tr("header.intro"))
        intro.setStyleSheet("color: #888;")
        root.addWidget(intro)

        for campo in FIELDS:
            label = tr(f"header.field.{campo.key}")
            if campo.needs_ffprobe and sem_ffprobe:
                label += " *"
            box = QCheckBox(label)
            box.setChecked(campo.key in chosen)
            if campo.parent is not None:
                box.setStyleSheet("margin-left: 18px;")  # cinza pareceria desabilitado
                pai = self._boxes[campo.parent]
                pai.toggled.connect(box.setEnabled)
                pai.toggled.connect(lambda on, b=box: None if on else b.setChecked(False))
                box.setEnabled(pai.isChecked())
            self._boxes[campo.key] = box
            root.addWidget(box)

        if sem_ffprobe:
            aviso = QLabel(tr("header.ffprobe.missing"))
            aviso.setWordWrap(True)
            aviso.setStyleSheet("color: #a80; font-size: 11px;")
            root.addWidget(aviso)

        note = QLabel(tr("header.note"))
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        root.addWidget(buttons)

    def _restore_defaults(self) -> None:
        for key, box in self._boxes.items():
            box.setChecked(key in metadata.DEFAULTS)

    def selection(self) -> list[str]:
        return metadata.normalize([k for k, box in self._boxes.items() if box.isChecked()])
