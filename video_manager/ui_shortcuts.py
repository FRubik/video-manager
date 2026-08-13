"""Diálogo de personalização das teclas da tela de revisão."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from . import shortcuts
from .shortcuts import ACTIONS


class ShortcutsDialog(QDialog):
    def __init__(self, key_bindings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atalhos da revisão")
        self._edits: dict[str, QKeySequenceEdit] = {}

        current = shortcuts.normalize(key_bindings)

        root = QVBoxLayout(self)
        intro = QLabel("Clique num campo e pressione a tecla que quer usar.")
        intro.setStyleSheet("color: #888;")
        root.addWidget(intro)

        form = QFormLayout()
        for action in ACTIONS:
            edit = QKeySequenceEdit(QKeySequence(current[action.key]))
            edit.setMaximumSequenceLength(1)
            self._edits[action.key] = edit
            label = action.label
            if action.extra:
                alternatives = ", ".join(shortcuts.canonical(e) for e in action.extra)
                label += f"  ({alternatives})"
            form.addRow(label + ":", edit)
        root.addLayout(form)

        note = QLabel(
            "As teclas entre parênteses continuam valendo como alternativa. "
            "Enter aplica a sessão e não pode ser remapeado."
        )
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
        for key, edit in self._edits.items():
            edit.setKeySequence(QKeySequence(shortcuts.DEFAULTS[key]))

    def key_bindings(self) -> dict[str, str]:
        return {key: edit.keySequence().toString() for key, edit in self._edits.items()}

    def accept(self) -> None:
        chosen = self.key_bindings()

        vazias = [a.label for a in ACTIONS if not chosen.get(a.key)]
        if vazias:
            QMessageBox.warning(
                self,
                "Atalho em branco",
                "Defina uma tecla para: " + ", ".join(vazias),
            )
            return

        repetidas = shortcuts.conflicts(chosen)
        if repetidas:
            detalhe = "\n".join(f"• {seq}: {' e '.join(labels)}" for seq, labels in repetidas)
            QMessageBox.warning(
                self,
                "Tecla repetida",
                f"A mesma tecla está em duas ações:\n\n{detalhe}",
            )
            return

        super().accept()
