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

from . import library, shortcuts
from .i18n import tr
from .library import DELETE, KEEP, MAYBE, ReviewState, VideoEntry

COLOR_KEEP = "#2e7d32"
COLOR_DELETE = "#c62828"
COLOR_MAYBE = "#ef6c00"
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
            self._label.setText(tr("review.no_thumb"))
            self._label.setStyleSheet("background: #111; color: #bbb;")
        else:
            pixmap = QPixmap(str(path))
            self._pixmap = None if pixmap.isNull() else pixmap
            if self._pixmap is None:
                self._label.setText(tr("review.bad_image"))
        self._fit = True
        self._render()

    def toggle_zoom(self) -> None:
        if self._pixmap is None:
            return
        self._fit = not self._fit
        self._render()

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
        #: tudo que foi varrido, não só a sessão — base das estatísticas de volume
        self.all_entries: list[VideoEntry] = []
        self.videos_dir: Path = Path()
        self.thumbs_dir: Path = Path()
        self.trash_dir: Path = Path()
        self.maybe_dir: Path = Path()
        self.state: ReviewState | None = None
        self.index = 0
        #: depois de aplicar, o autosave não pode ressuscitar o arquivo apagado
        self._applied = False
        # a view precisa poder receber foco para que os atalhos (contexto
        # WidgetWithChildren) cheguem até ela
        self.setFocusPolicy(Qt.StrongFocus)
        self._shortcuts: list[QShortcut] = []
        #: teclas em vigor, guardadas para reescrever os rótulos ao trocar de idioma
        self._key_bindings: dict[str, str] = dict(shortcuts.DEFAULTS)
        self._build_ui()
        self.apply_key_bindings(shortcuts.DEFAULTS)

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

        self.volume_label = QLabel()
        self.volume_label.setWordWrap(True)
        self.volume_label.setStyleSheet("color: #888;")
        root.addWidget(self.volume_label)

        buttons = QHBoxLayout()
        # os seis primeiros têm o texto escrito em `apply_key_bindings`, que
        # precisa carimbar a tecla atual de cada ação
        self.prev_button = QPushButton()
        self.next_button = QPushButton()
        self.keep_button = QPushButton()
        self.maybe_button = QPushButton()
        self.delete_button = QPushButton()
        self.open_button = QPushButton()
        self.back_button = QPushButton()
        self.finish_button = QPushButton()

        self.keep_button.setStyleSheet(f"font-weight: 600; color: {COLOR_KEEP};")
        self.maybe_button.setStyleSheet(f"font-weight: 600; color: {COLOR_MAYBE};")
        self.delete_button.setStyleSheet(f"font-weight: 600; color: {COLOR_DELETE};")

        self.prev_button.clicked.connect(self.go_previous)
        self.next_button.clicked.connect(self.go_next)
        self.keep_button.clicked.connect(lambda: self.decide(KEEP))
        self.maybe_button.clicked.connect(lambda: self.decide(MAYBE))
        self.delete_button.clicked.connect(lambda: self.decide(DELETE))
        self.open_button.clicked.connect(self.open_current_video)
        self.back_button.clicked.connect(self.go_back)
        self.finish_button.clicked.connect(self.finish)

        buttons.addWidget(self.prev_button)
        buttons.addWidget(self.next_button)
        buttons.addSpacing(20)
        buttons.addWidget(self.keep_button)
        buttons.addWidget(self.maybe_button)
        buttons.addWidget(self.delete_button)
        buttons.addSpacing(20)
        buttons.addWidget(self.open_button)
        buttons.addStretch()
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.finish_button)
        root.addLayout(buttons)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self.hint)

    def retranslate(self) -> None:
        """Reescreve a tela no idioma corrente, preservando a sessão em curso."""
        self.apply_key_bindings(self._key_bindings)
        if self.entries:
            self.show_current()
            self.refresh_volume()

    def apply_key_bindings(self, key_bindings: dict) -> None:
        """Reinstala os atalhos e reescreve rótulos e dica com as teclas atuais."""
        mapping = shortcuts.normalize(key_bindings)
        self._key_bindings = mapping

        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts.clear()

        slots = {
            "prev": self.go_previous,
            "next": self.go_next,
            "keep": lambda: self.decide(KEEP),
            "maybe": lambda: self.decide(MAYBE),
            "delete": lambda: self.decide(DELETE),
            "open": self.open_current_video,
            "zoom": self.viewer.toggle_zoom,
        }

        def add(sequence: str, slot) -> None:
            if not sequence:
                return
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

        escolhidas = {shortcuts.canonical(v) for v in mapping.values()}
        for action in shortcuts.ACTIONS:
            slot = slots[action.key]
            add(mapping[action.key], slot)
            for alternativa in action.extra:
                # uma alternativa fixa não pode roubar a tecla escolhida para outra ação
                if shortcuts.canonical(alternativa) not in escolhidas:
                    add(alternativa, slot)
        for sequence in shortcuts.APPLY_KEYS:
            add(sequence, self.finish)

        for button, action in (
            (self.prev_button, "prev"),
            (self.next_button, "next"),
            (self.keep_button, "keep"),
            (self.maybe_button, "maybe"),
            (self.delete_button, "delete"),
            (self.open_button, "open"),
        ):
            button.setText(tr(f"review.{action}", key=mapping[action]))
        self.back_button.setText(tr("review.back"))
        self.back_button.setToolTip(tr("review.back.tip"))
        self.finish_button.setText(tr("review.finish"))
        self.hint.setText(shortcuts.describe(mapping) + tr("review.hint.zoom"))

    # -------------------------------------------------------------- sessão
    def load_session(
        self,
        entries: list[VideoEntry],
        state: ReviewState,
        *,
        videos_dir: Path,
        thumbs_dir: Path,
        trash_dir: Path,
        maybe_dir: Path,
        all_entries: list[VideoEntry] | None = None,
        start_index: int = 0,
        resumed: bool = False,
    ) -> None:
        """Carrega a sessão. `resumed` preserva as decisões vindas do disco."""
        self.entries = entries
        self.all_entries = entries if all_entries is None else all_entries
        self.videos_dir = videos_dir
        self.thumbs_dir = thumbs_dir
        self.trash_dir = trash_dir
        self.maybe_dir = maybe_dir
        self.state = state
        self.index = start_index if 0 <= start_index < len(entries) else 0
        self._applied = False
        if not resumed:
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
        self.refresh_volume()
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
            self.name_label.setText(tr("review.empty"))
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
        to_maybe = sum(1 for e in self.entries if e.decision == MAYBE)
        origem = tr("review.from_maybe") if entry.from_maybe else ""
        self.info_label.setText(
            tr(
                "review.counts",
                size=library.format_size(entry.size_bytes),
                keep=to_keep,
                maybe=to_maybe,
                delete=to_delete,
                pending=pending,
                origin=origem,
            )
        )

        self.list.blockSignals(True)
        self.list.setCurrentRow(self.index)
        self.list.blockSignals(False)

    # ---------------------------------------------------------- estatísticas
    def _stats(self) -> library.Stats:
        if self.state is None:
            return library.Stats()
        return library.collect_stats(self.all_entries, self.state, session=self.entries)

    def refresh_volume(self) -> None:
        """Volume marcado nesta sessão e projeção do tamanho final da pasta.

        Só é recalculado quando uma decisão muda: navegar entre os vídeos não
        altera nenhum desses números.
        """
        stats = self._stats()
        partes = [tr("review.volume.folder", size=library.format_size(stats.total_bytes))]

        marcado = [
            f"{tr(chave)} {library.format_size(stats.session_bytes(decisao))}"
            for decisao, chave in (
                (DELETE, "decision.delete"),
                (MAYBE, "decision.maybe"),
                (KEEP, "decision.keep"),
            )
            if stats.session_bytes(decisao)
        ]
        if marcado:
            partes.append(tr("review.volume.marked", parts=" · ".join(marcado)))

        restante = stats.estimated_remaining
        if restante is not None:
            partes.append(
                tr(
                    "review.volume.projection",
                    size=library.format_size(restante),
                    rate=library.format_rate(stats.discard_rate),
                )
            )
        self.volume_label.setText("   ·   ".join(partes))

    def _update_status_label(self, entry: VideoEntry) -> None:
        texto = tr(
            {DELETE: "review.status.delete", KEEP: "review.status.keep",
             MAYBE: "review.status.maybe"}.get(entry.decision, "review.status.pending")
        )
        cor = {DELETE: COLOR_DELETE, KEEP: COLOR_KEEP, MAYBE: COLOR_MAYBE}.get(
            entry.decision, COLOR_PENDING
        )
        self.status_label.setText(texto)
        self.status_label.setStyleSheet(f"font-weight: 600; color: {cor};")

    def _update_list_item(self, position: int) -> None:
        item = self.list.item(position)
        if item is None:
            return
        entry = self.entries[position]
        prefix = {DELETE: "✖ ", KEEP: "✔ ", MAYBE: "? "}.get(entry.decision, "  ")
        item.setText(prefix + entry.name)
        color = {DELETE: COLOR_DELETE, KEEP: COLOR_KEEP, MAYBE: COLOR_MAYBE}.get(
            entry.decision, COLOR_PENDING
        )
        item.setForeground(QBrush(QColor(color)))

    # ------------------------------------------------------------- decisões
    def decide(self, decision: str) -> None:
        entry = self.current
        if entry is None:
            return
        entry.decision = decision
        self._update_status_label(entry)
        self._update_list_item(self.index)
        self.refresh_volume()
        # antes de avançar: no último vídeo, `go_next` abre o diálogo de fim de
        # sessão, que pode aplicar tudo e apagar o arquivo que acabamos de gravar.
        # A posição salva é a seguinte — retomar deve cair no próximo pendente.
        self.autosave(self.index + 1)
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
                tr("review.open.failed.title"),
                tr(
                    "review.open.failed.body",
                    name=entry.name,
                    reason=reason,
                    path=entry.video,
                ),
            )

    def _offer_finish(self) -> None:
        stats = self._stats()
        to_delete = stats.session_count(DELETE)
        to_maybe = stats.session_count(MAYBE)
        answer = QMessageBox.question(
            self,
            tr("review.end.title"),
            tr(
                "review.end.body",
                total=len(self.entries),
                delete=to_delete,
                delete_size=library.format_size(stats.session_bytes(DELETE)),
                maybe=to_maybe,
                maybe_size=library.format_size(stats.session_bytes(MAYBE)),
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self.finish()

    # ------------------------------------------------------- sessão salva
    @property
    def applied(self) -> bool:
        """A sessão já foi aplicada ou encerrada — não há mais o que guardar."""
        return self._applied

    def autosave(self, index: int | None = None) -> None:
        """Grava a sessão no disco depois de cada decisão.

        É o que cobre a interrupção que não avisa — incluindo o app morrer sem
        chance de perguntar nada. O arquivo é pequeno e some ao aplicar.
        """
        if self._applied or not self.entries or self.state is None:
            return
        posicao = self.index if index is None else index
        library.save_session(
            self.thumbs_dir,
            self.entries,
            max(0, min(posicao, len(self.entries) - 1)),
            videos_dir=self.videos_dir,
            trash_dir=self.trash_dir,
            maybe_dir=self.maybe_dir,
        )

    def discard_saved_session(self) -> None:
        """Apaga o arquivo e trava o autosave — a sessão acabou."""
        self._applied = True
        library.clear_session(self.thumbs_dir)

    def go_back(self) -> None:
        """Volta para a tela inicial sem mover nada.

        Não há o que confirmar: o autosave já gravou cada decisão no disco, e a
        tela inicial oferece "Retomar" enquanto a sessão existir.
        """
        self.autosave()
        self.back_requested.emit()

    # -------------------------------------------------------------- aplicar
    def has_pending_changes(self) -> bool:
        return any(e.decision is not None for e in self.entries)

    def _planned_moves(self) -> list[tuple[VideoEntry, Path | None, str]]:
        """Para cada decidido: (vídeo, destino ou None se fica onde está, motivo)."""
        plano = []
        for entry in self.entries:
            if entry.decision == DELETE:
                plano.append((entry, self.trash_dir, DELETE))
            elif entry.decision == MAYBE:
                # já está no talvez: nada a mover, só o registro muda
                plano.append((entry, None if entry.from_maybe else self.maybe_dir, MAYBE))
            elif entry.decision == KEEP:
                # manter um vídeo do talvez significa trazê-lo de volta
                plano.append((entry, self.videos_dir if entry.from_maybe else None, KEEP))
        return plano

    def finish(self) -> None:
        plano = self._planned_moves()
        if not plano:
            self.discard_saved_session()
            self.session_finished.emit({"movidos": 0, "mantidos": 0, "talvez": 0, "erros": []})
            return

        linhas = []
        for destino, chave in (
            (self.trash_dir, "review.confirm.to_delete"),
            (self.maybe_dir, "review.confirm.to_maybe"),
            (self.videos_dir, "review.confirm.to_videos"),
        ):
            movidos = [entry for entry, dest, _ in plano if dest == destino]
            if movidos:
                linhas.append(
                    tr(
                        "review.confirm.line",
                        count=len(movidos),
                        size=library.format_size(sum(e.size_bytes for e in movidos)),
                        reason=tr(chave),
                        dest=destino,
                    )
                )

        if linhas:
            answer = QMessageBox.question(
                self,
                tr("review.confirm.title"),
                "\n".join(linhas) + tr("review.confirm.footer"),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return

        contagem = {DELETE: 0, KEEP: 0, MAYBE: 0}
        volume = {DELETE: 0, KEEP: 0, MAYBE: 0}
        errors: list[str] = []
        for entry, destino, motivo in plano:
            tamanho = entry.size_bytes  # medido antes do move, que invalida o caminho
            try:
                if destino is not None:
                    # devolução: o log fica no "talvez", de onde o vídeo saiu
                    log_dir = self.maybe_dir if motivo == KEEP else None
                    library.move_video(entry.video, destino, motivo, log_dir)
                contagem[motivo] += 1
                volume[motivo] += tamanho
                if self.state is not None:
                    self.state.record(entry.name, motivo, tamanho)
            except OSError as exc:
                # sem registro: a decisão volta a aparecer na próxima sessão
                errors.append(f"{entry.name}: {exc}")

        if self.state is not None:
            self.state.save()
        # o que falhou não entrou no histórico e volta na próxima sessão; a
        # sessão salva, essa, já cumpriu o papel dela
        self.discard_saved_session()

        summary = {
            "movidos": contagem[DELETE],
            "mantidos": contagem[KEEP],
            "talvez": contagem[MAYBE],
            "bytes_movidos": volume[DELETE],
            "erros": errors,
            "quarentena": str(self.trash_dir),
        }

        def linha(quantos: int, bytes_: int, chave: str) -> str:
            return tr(
                "review.done.line",
                count=quantos,
                size=library.format_size(bytes_),
                text=tr(chave),
            )

        message = "<br>".join((
            linha(contagem[DELETE], volume[DELETE], "review.done.deleted"),
            linha(contagem[MAYBE], volume[MAYBE], "review.done.maybe"),
            linha(contagem[KEEP], volume[KEEP], "review.done.kept"),
        ))
        restante = self._stats().estimated_remaining
        if restante is not None:
            message += tr("review.done.projection", size=library.format_size(restante))
        if errors:
            message += tr("review.done.errors") + "<br>".join(errors[:10])
        QMessageBox.information(self, tr("review.done.title"), message)

        self.session_finished.emit(summary)
