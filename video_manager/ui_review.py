"""Tela de revisão: uma thumbnail por vez, decisão por teclado."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import library
from .library import DELETE, KEEP, ReviewState, VideoEntry

COLOR_KEEP = "#2e7d32"
COLOR_DELETE = "#c62828"
COLOR_PENDING = "#757575"


class ImageViewer(QScrollArea):
    """Mostra a thumbnail ajustada à janela, com zoom 1:1 sob demanda."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel(alignment=Qt.AlignCenter)
        self._label.setStyleSheet("background: #111;")
        self.setWidget(self._label)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: #111; border: none;")
        self._pixmap: QPixmap | None = None
        self._fit = True

    def set_image(self, path: Path | None) -> None:
        if path is None or not path.exists():
            self._pixmap = None
            self._label.setText("Sem thumbnail para este vídeo")
            self._label.setStyleSheet("background: #111; color: #bbb;")
        else:
            pixmap = QPixmap(str(path))
            self._pixmap = None if pixmap.isNull() else pixmap
            if self._pixmap is None:
                self._label.setText("Não foi possível carregar a imagem")
        self._fit = True
        self._render()

    def toggle_zoom(self) -> None:
        if self._pixmap is None:
            return
        self._fit = not self._fit
        self._render()

    @property
    def zoomed(self) -> bool:
        return not self._fit

    def _render(self) -> None:
        if self._pixmap is None:
            self.setWidgetResizable(True)
            return
        if self._fit:
            self.setWidgetResizable(True)
            area: QSize = self.viewport().size()
            self._label.setPixmap(
                self._pixmap.scaled(area, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.setWidgetResizable(False)
            self._label.setPixmap(self._pixmap)
            self._label.adjustSize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self._render()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_zoom()
        super().mousePressEvent(event)


class ReviewView(QWidget):
    session_finished = Signal(dict)
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[VideoEntry] = []
        self.trash_dir: Path = Path()
        self.state: ReviewState | None = None
        self.index = 0
        # a view precisa poder receber foco para que os atalhos (contexto
        # WidgetWithChildren) cheguem até ela
        self.setFocusPolicy(Qt.StrongFocus)
        self._build_ui()
        self._install_shortcuts()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: 600;")
        self.counter_label = QLabel()
        header.addWidget(self.name_label, stretch=1)
        header.addWidget(self.status_label)
        header.addSpacing(16)
        header.addWidget(self.counter_label)
        root.addLayout(header)

        self.viewer = ImageViewer()
        self.list = QListWidget()
        self.list.setMaximumWidth(320)
        self.list.setMinimumWidth(180)
        self.list.currentRowChanged.connect(self._on_list_selection)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.viewer)
        splitter.addWidget(self.list)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([1000, 260])
        root.addWidget(splitter, stretch=1)

        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #888;")
        root.addWidget(self.info_label)

        buttons = QHBoxLayout()
        self.prev_button = QPushButton("← Anterior")
        self.next_button = QPushButton("Próximo →")
        self.keep_button = QPushButton("Manter (K)")
        self.delete_button = QPushButton("Apagar (D)")
        self.open_button = QPushButton("Abrir vídeo (O)")
        self.finish_button = QPushButton("Aplicar e finalizar")

        self.keep_button.setStyleSheet(f"font-weight: 600; color: {COLOR_KEEP};")
        self.delete_button.setStyleSheet(f"font-weight: 600; color: {COLOR_DELETE};")

        self.prev_button.clicked.connect(self.go_previous)
        self.next_button.clicked.connect(self.go_next)
        self.keep_button.clicked.connect(lambda: self.decide(KEEP))
        self.delete_button.clicked.connect(lambda: self.decide(DELETE))
        self.open_button.clicked.connect(self.open_current_video)
        self.finish_button.clicked.connect(self.finish)

        buttons.addWidget(self.prev_button)
        buttons.addWidget(self.next_button)
        buttons.addSpacing(20)
        buttons.addWidget(self.keep_button)
        buttons.addWidget(self.delete_button)
        buttons.addSpacing(20)
        buttons.addWidget(self.open_button)
        buttons.addStretch()
        buttons.addWidget(self.finish_button)
        root.addLayout(buttons)

        hint = QLabel(
            "K/→ manter · D apagar · ←/→ navegar · O abrir no player · "
            "Z ou clique = zoom 1:1 · Enter aplica"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(hint)

    def _install_shortcuts(self) -> None:
        def add(seq: str, slot):
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        add("K", lambda: self.decide(KEEP))
        add("D", lambda: self.decide(DELETE))
        add("Del", lambda: self.decide(DELETE))
        add("Right", self.go_next)
        add("Left", self.go_previous)
        add("Space", self.go_next)
        add("O", self.open_current_video)
        add("Z", self.viewer.toggle_zoom)
        add("Return", self.finish)
        add("Enter", self.finish)

    # -------------------------------------------------------------- sessão
    def load_session(self, entries: list[VideoEntry], trash_dir: Path, state: ReviewState) -> None:
        self.entries = entries
        self.trash_dir = trash_dir
        self.state = state
        self.index = 0
        for entry in self.entries:
            entry.decision = None

        self.list.blockSignals(True)
        self.list.clear()
        for entry in self.entries:
            self.list.addItem(QListWidgetItem(entry.name))
        self.list.blockSignals(False)
        for position in range(len(self.entries)):
            self._update_list_item(position)

        self.show_current()
        self.grab_keyboard_focus()

    def showEvent(self, event):
        super().showEvent(event)
        self.grab_keyboard_focus()

    def grab_keyboard_focus(self) -> None:
        """Garante que os atalhos funcionem sem exigir um clique na janela.

        O adiamento é necessário porque o diálogo de progresso (ou qualquer
        modal) só devolve o foco depois que o event loop processa o fechamento.
        """
        def take():
            if self.isVisible():
                self.window().activateWindow()
                self.setFocus(Qt.OtherFocusReason)

        take()
        QTimer.singleShot(0, take)

    @property
    def current(self) -> VideoEntry | None:
        if 0 <= self.index < len(self.entries):
            return self.entries[self.index]
        return None

    def show_current(self) -> None:
        entry = self.current
        if entry is None:
            self.name_label.setText("Nenhum vídeo nesta sessão")
            self.viewer.set_image(None)
            self.counter_label.clear()
            self.status_label.clear()
            self.info_label.clear()
            return

        self.name_label.setText(entry.name)
        self.counter_label.setText(f"{self.index + 1} / {len(self.entries)}")
        self.viewer.set_image(entry.thumb)
        self._update_status_label(entry)

        pending = sum(1 for e in self.entries if e.decision is None)
        to_delete = sum(1 for e in self.entries if e.decision == DELETE)
        to_keep = sum(1 for e in self.entries if e.decision == KEEP)
        self.info_label.setText(
            f"{entry.size_mb:,.1f} MB   ·   manter: {to_keep}   apagar: {to_delete}   "
            f"pendentes: {pending}".replace(",", ".")
        )

        self.list.blockSignals(True)
        self.list.setCurrentRow(self.index)
        self.list.blockSignals(False)

    def _update_status_label(self, entry: VideoEntry) -> None:
        if entry.decision == DELETE:
            self.status_label.setText("● APAGAR")
            self.status_label.setStyleSheet(f"font-weight: 600; color: {COLOR_DELETE};")
        elif entry.decision == KEEP:
            self.status_label.setText("● MANTER")
            self.status_label.setStyleSheet(f"font-weight: 600; color: {COLOR_KEEP};")
        else:
            self.status_label.setText("○ pendente")
            self.status_label.setStyleSheet(f"font-weight: 600; color: {COLOR_PENDING};")

    def _update_list_item(self, position: int) -> None:
        item = self.list.item(position)
        if item is None:
            return
        entry = self.entries[position]
        prefix = {DELETE: "✖ ", KEEP: "✔ "}.get(entry.decision, "  ")
        item.setText(prefix + entry.name)
        color = {DELETE: COLOR_DELETE, KEEP: COLOR_KEEP}.get(entry.decision, COLOR_PENDING)
        item.setForeground(QBrush(QColor(color)))

    # ------------------------------------------------------------- decisões
    def decide(self, decision: str) -> None:
        entry = self.current
        if entry is None:
            return
        entry.decision = decision
        self._update_status_label(entry)
        self._update_list_item(self.index)
        self.go_next(auto=True)

    def go_next(self, auto: bool = False) -> None:
        if self.index + 1 < len(self.entries):
            self.index += 1
            self.show_current()
        elif auto:
            self.show_current()
            self._offer_finish()
        else:
            self.show_current()

    def go_previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self.show_current()

    def _on_list_selection(self, row: int) -> None:
        if row >= 0 and row != self.index:
            self.index = row
            self.show_current()

    def open_current_video(self) -> None:
        entry = self.current
        if entry is None:
            return
        ok, reason = library.open_in_player(entry.video)
        if not ok:
            QMessageBox.warning(
                self,
                "Não foi possível abrir o vídeo",
                f"{entry.name}\n\n{reason}\n\nCaminho:\n{entry.video}",
            )

    def _offer_finish(self) -> None:
        to_delete = sum(1 for e in self.entries if e.decision == DELETE)
        answer = QMessageBox.question(
            self,
            "Fim da sessão",
            f"Você revisou todos os {len(self.entries)} vídeos desta sessão.\n"
            f"{to_delete} marcado(s) para apagar.\n\nAplicar agora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self.finish()

    # -------------------------------------------------------------- aplicar
    def has_pending_changes(self) -> bool:
        return any(e.decision is not None for e in self.entries)

    def finish(self) -> None:
        to_delete = [e for e in self.entries if e.decision == DELETE]
        to_keep = [e for e in self.entries if e.decision == KEEP]

        if to_delete:
            answer = QMessageBox.question(
                self,
                "Confirmar descarte",
                f"Mover {len(to_delete)} vídeo(s) para:\n{self.trash_dir}\n\n"
                "As thumbnails permanecem onde estão.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return

        moved, errors = 0, []
        for entry in to_delete:
            try:
                library.move_to_trash(entry.video, self.trash_dir)
                moved += 1
                if self.state is not None:
                    self.state.record(entry.name, DELETE)
            except OSError as exc:
                errors.append(f"{entry.name}: {exc}")

        if self.state is not None:
            for entry in to_keep:
                self.state.record(entry.name, KEEP)
            self.state.save()

        summary = {
            "movidos": moved,
            "mantidos": len(to_keep),
            "erros": errors,
            "quarentena": str(self.trash_dir),
        }

        message = (
            f"<b>{moved}</b> vídeo(s) movido(s) para a quarentena<br>"
            f"<b>{len(to_keep)}</b> mantido(s) e registrado(s) como revisados"
        )
        if errors:
            message += "<br><br><b>Falhas:</b><br>" + "<br>".join(errors[:10])
        QMessageBox.information(self, "Sessão concluída", message)

        self.session_finished.emit(summary)
