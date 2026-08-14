"""Tela inicial: pastas, opções de geração e formato da sessão de revisão."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import library
from .config import Config
from .ui_shortcuts import ShortcutsDialog


class FolderPicker(QWidget):
    """Campo de texto com botão de procurar pasta."""

    changed = Signal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.editingFinished.connect(self.changed.emit)

        button = QToolButton()
        button.setText("…")
        button.setToolTip("Escolher pasta")
        button.clicked.connect(self._browse)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.edit)
        self._layout.addWidget(button)

    def add_button(self, text: str, tooltip: str, callback) -> QToolButton:
        """Acrescenta um botão extra à direita do campo."""
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        self._layout.addWidget(button)
        return button

    def _browse(self) -> None:
        start = self.edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Escolher pasta", start)
        if chosen:
            self.edit.setText(chosen)
            self.changed.emit()

    def path(self) -> Path:
        return Path(self.edit.text().strip()).expanduser()

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value)


class SetupView(QWidget):
    start_requested = Signal(Config)
    resume_requested = Signal(Config)
    key_bindings_changed = Signal(dict)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        #: pasta de vídeos anterior, para saber se a quarentena ainda é a padrão dela
        self._previous_videos_dir = ""
        self._build_ui()
        self._load_config()
        self.refresh_summary()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("Gerenciador de Vídeos")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        root.addWidget(title)

        # --- pastas ---
        folders = QGroupBox("Pastas")
        form = QFormLayout(folders)
        self.videos_picker = FolderPicker("pasta com os vídeos")
        self.thumbs_picker = FolderPicker("pasta onde ficam/serão salvas as thumbs")
        self.trash_picker = FolderPicker("quarentena (padrão: <vídeos>/_para_apagar)")
        self.maybe_picker = FolderPicker("rever depois (padrão: <vídeos>/_talvez)")
        form.addRow("Vídeos:", self.videos_picker)
        form.addRow("Thumbnails:", self.thumbs_picker)
        self.trash_default_button = self.trash_picker.add_button(
            "Padrão",
            "Apontar a quarentena para <pasta de vídeos>/_para_apagar",
            lambda: self._use_default(self.trash_picker, library.default_trash_dir),
        )
        form.addRow("Descartes:", self.trash_picker)
        self.maybe_default_button = self.maybe_picker.add_button(
            "Padrão",
            "Apontar o “talvez” para <pasta de vídeos>/_talvez",
            lambda: self._use_default(self.maybe_picker, library.default_maybe_dir),
        )
        form.addRow("Talvez:", self.maybe_picker)
        root.addWidget(folders)

        self.videos_picker.changed.connect(self._on_videos_changed)
        self.thumbs_picker.changed.connect(self.refresh_summary)

        # --- geração ---
        self.gen_group = QGroupBox("Gerar thumbnails")
        self.gen_group.setCheckable(True)
        self.gen_group.setToolTip(
            "Desmarcado: abre direto a interface de revisão usando as thumbs já existentes."
        )
        gen_form = QFormLayout(self.gen_group)

        self.only_missing = QCheckBox("Somente vídeos que ainda não têm thumbnail")
        gen_form.addRow(self.only_missing)

        grid_row = QHBoxLayout()
        self.n_rows = QSpinBox()
        self.n_rows.setRange(1, 12)
        self.n_cols = QSpinBox()
        self.n_cols.setRange(1, 12)
        grid_row.addWidget(QLabel("linhas"))
        grid_row.addWidget(self.n_rows)
        grid_row.addSpacing(12)
        grid_row.addWidget(QLabel("colunas"))
        grid_row.addWidget(self.n_cols)
        grid_row.addStretch()
        gen_form.addRow("Grade:", self._wrap(grid_row))

        detail_row = QHBoxLayout()
        self.cell_height = QSpinBox()
        self.cell_height.setRange(60, 800)
        self.cell_height.setSingleStep(20)
        self.cell_height.setSuffix(" px")
        self.margin = QDoubleSpinBox()
        self.margin.setRange(0.0, 0.45)
        self.margin.setSingleStep(0.01)
        self.margin.setDecimals(2)
        self.workers = QSpinBox()
        self.workers.setRange(1, 32)
        detail_row.addWidget(QLabel("altura da célula"))
        detail_row.addWidget(self.cell_height)
        detail_row.addSpacing(12)
        detail_row.addWidget(QLabel("margem"))
        detail_row.addWidget(self.margin)
        detail_row.addSpacing(12)
        detail_row.addWidget(QLabel("threads"))
        detail_row.addWidget(self.workers)
        detail_row.addStretch()
        gen_form.addRow("Detalhes:", self._wrap(detail_row))

        self.add_timestamp = QCheckBox("Escrever o tempo em cada frame")
        gen_form.addRow(self.add_timestamp)
        root.addWidget(self.gen_group)

        self.gen_group.toggled.connect(self.refresh_summary)

        # --- sessão ---
        session = QGroupBox("Sessão de revisão")
        session_layout = QVBoxLayout(session)

        self.mode_all = QRadioButton("Revisar todos os vídeos com thumbnail")
        self.mode_random = QRadioButton("Verificação randômica — sortear apenas")
        random_row = QHBoxLayout()
        random_row.addWidget(self.mode_random)
        self.session_size = QSpinBox()
        self.session_size.setRange(1, 10000)
        self.session_size.setSuffix(" vídeos")
        random_row.addWidget(self.session_size)
        random_row.addStretch()

        self.skip_reviewed = QCheckBox("Pular vídeos que já revisei em sessões anteriores")
        self.shuffle_order = QCheckBox("Mostrar em ordem randômica, e não alfabética")
        self.shuffle_order.setToolTip(
            "Embaralha a ordem de exibição da sessão. Útil numa pasta onde os "
            "nomes agrupam o conteúdo — a ordem alfabética faz você ver tudo de "
            "um tipo de uma vez."
        )

        # o “talvez” é escopo, não quantidade: por isso um grupo próprio, e não
        # mais um modo ao lado de “revisar todos” e “verificação randômica”
        maybe_row = QHBoxLayout()
        maybe_row.addWidget(QLabel("Vídeos do “talvez”:"))
        self.maybe_ignore = QRadioButton("deixar de fora")
        self.maybe_include = QRadioButton("incluir na sessão")
        self.maybe_only = QRadioButton("somente eles")
        self.maybe_ignore.setToolTip("A sessão ignora a pasta “talvez”.")
        self.maybe_include.setToolTip(
            "Traz de volta o que ficou na pasta “talvez”, junto com os demais. "
            "Manter devolve o vídeo à pasta de vídeos; apagar manda para a quarentena."
        )
        self.maybe_only.setToolTip(
            "A sessão inteira é feita das dúvidas anteriores — nenhum vídeo novo entra."
        )
        self.maybe_group = QButtonGroup(self)
        for button in (self.maybe_ignore, self.maybe_include, self.maybe_only):
            self.maybe_group.addButton(button)
            maybe_row.addWidget(button)
        maybe_row.addStretch()

        session_layout.addWidget(self.mode_all)
        session_layout.addLayout(random_row)
        session_layout.addWidget(self.skip_reviewed)
        session_layout.addWidget(self.shuffle_order)
        session_layout.addLayout(maybe_row)
        root.addWidget(session)

        self.mode_random.toggled.connect(self.session_size.setEnabled)
        self.mode_random.toggled.connect(self.refresh_summary)
        self.skip_reviewed.toggled.connect(self.refresh_summary)
        self.shuffle_order.toggled.connect(self.refresh_summary)
        self.maybe_group.buttonToggled.connect(self.refresh_summary)
        self.maybe_picker.changed.connect(self.refresh_summary)

        # --- sessão interrompida ---
        self.resume_box = QFrame()
        self.resume_box.setFrameShape(QFrame.StyledPanel)
        self.resume_box.setStyleSheet(
            "QFrame { border: 1px solid #ef6c00; border-radius: 4px; padding: 8px; }"
        )
        resume_layout = QHBoxLayout(self.resume_box)
        self.resume_label = QLabel()
        self.resume_label.setWordWrap(True)
        self.resume_label.setStyleSheet("border: none;")
        resume_button = QPushButton("Retomar")
        resume_button.setToolTip("Continuar a sessão salva de onde ela parou")
        resume_button.clicked.connect(self._emit_resume)
        discard_button = QPushButton("Descartar")
        discard_button.setToolTip("Esquecer a sessão salva e liberar esses vídeos para novas sessões")
        discard_button.clicked.connect(self._discard_saved_session)
        resume_layout.addWidget(self.resume_label, stretch=1)
        resume_layout.addWidget(resume_button)
        resume_layout.addWidget(discard_button)
        self.resume_box.hide()
        root.addWidget(self.resume_box)

        # --- resumo + ação ---
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setFrameShape(QFrame.StyledPanel)
        self.summary.setStyleSheet("padding: 8px;")
        root.addWidget(self.summary)

        self.volume = QLabel()
        self.volume.setWordWrap(True)
        self.volume.setFrameShape(QFrame.StyledPanel)
        self.volume.setStyleSheet("padding: 8px;")
        self.volume.setToolTip(
            "A projeção aplica ao volume ainda não revisado a mesma proporção "
            "de descarte das decisões que você já tomou."
        )
        root.addWidget(self.volume)

        root.addStretch()

        actions = QHBoxLayout()
        rescan = QPushButton("Reanalisar pastas")
        rescan.clicked.connect(self.refresh_summary)
        shortcuts_button = QPushButton("Atalhos…")
        shortcuts_button.setToolTip("Escolher as teclas usadas na tela de revisão")
        shortcuts_button.clicked.connect(self._edit_shortcuts)
        self.start_button = QPushButton("Iniciar")
        self.start_button.setDefault(True)
        self.start_button.setMinimumWidth(140)
        self.start_button.clicked.connect(self._emit_start)
        actions.addWidget(rescan)
        actions.addWidget(shortcuts_button)
        actions.addStretch()
        actions.addWidget(self.start_button)
        root.addLayout(actions)

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    # --------------------------------------------------------------- estado
    def _load_config(self) -> None:
        c = self.config
        self.videos_picker.setText(c.videos_dir)
        self.thumbs_picker.setText(c.thumbs_dir)
        self.trash_picker.setText(c.trash_dir)
        self.maybe_picker.setText(c.maybe_dir)
        self.gen_group.setChecked(c.generate_thumbs)
        self.only_missing.setChecked(c.only_missing)
        self.n_rows.setValue(c.n_rows)
        self.n_cols.setValue(c.n_cols)
        self.cell_height.setValue(c.cell_height)
        self.margin.setValue(c.margin)
        self.workers.setValue(c.workers)
        self.add_timestamp.setChecked(c.add_timestamp)
        self.mode_random.setChecked(c.random_session)
        self.mode_all.setChecked(not c.random_session)
        self.session_size.setValue(c.session_size)
        self.session_size.setEnabled(c.random_session)
        self.skip_reviewed.setChecked(c.skip_reviewed)
        self.shuffle_order.setChecked(c.shuffle_order)
        if c.only_maybe:
            self.maybe_only.setChecked(True)
        elif c.include_maybe:
            self.maybe_include.setChecked(True)
        else:
            self.maybe_ignore.setChecked(True)
        self._previous_videos_dir = c.videos_dir
        # config de uma versão anterior não traz as pastas novas
        if c.videos_dir:
            for picker, default_for in (
                (self.trash_picker, library.default_trash_dir),
                (self.maybe_picker, library.default_maybe_dir),
            ):
                if not picker.text():
                    picker.setText(str(default_for(self.videos_picker.path())))

    def current_config(self) -> Config:
        c = self.config
        c.videos_dir = self.videos_picker.text()
        c.thumbs_dir = self.thumbs_picker.text()
        c.trash_dir = self.trash_picker.text()
        c.maybe_dir = self.maybe_picker.text()
        c.generate_thumbs = self.gen_group.isChecked()
        c.only_missing = self.only_missing.isChecked()
        c.n_rows = self.n_rows.value()
        c.n_cols = self.n_cols.value()
        c.cell_height = self.cell_height.value()
        c.margin = self.margin.value()
        c.workers = self.workers.value()
        c.add_timestamp = self.add_timestamp.isChecked()
        c.random_session = self.mode_random.isChecked()
        c.session_size = self.session_size.value()
        c.skip_reviewed = self.skip_reviewed.isChecked()
        c.shuffle_order = self.shuffle_order.isChecked()
        c.only_maybe = self.maybe_only.isChecked()
        c.include_maybe = self.maybe_include.isChecked()
        return c

    def _edit_shortcuts(self) -> None:
        dialog = ShortcutsDialog(self.config.key_bindings, self)
        if dialog.exec() != ShortcutsDialog.Accepted:
            return
        self.config.key_bindings = dialog.key_bindings()
        self.config.save()
        self.key_bindings_changed.emit(self.config.key_bindings)

    def maybe_scan_dir(self) -> Path | None:
        """Pasta “talvez” a incluir na varredura, ou None se ela fica de fora."""
        varre = self.maybe_include.isChecked() or self.maybe_only.isChecked()
        if not varre or not self.maybe_picker.text():
            return None
        return self.maybe_picker.path()

    def _use_default(self, picker: FolderPicker, default_for) -> None:
        if not self.videos_picker.text():
            return
        picker.setText(str(default_for(self.videos_picker.path())))
        self.refresh_summary()

    def _follows_videos(self, picker: FolderPicker, default_for) -> bool:
        """A pasta está vazia ou ainda é a padrão da pasta de vídeos anterior?"""
        current = picker.text()
        if not current:
            return True
        if not self._previous_videos_dir:
            return False
        previous = Path(self._previous_videos_dir).expanduser()
        return Path(current).expanduser() == default_for(previous)

    def _on_videos_changed(self) -> None:
        if self.videos_picker.text():
            for picker, default_for in (
                (self.trash_picker, library.default_trash_dir),
                (self.maybe_picker, library.default_maybe_dir),
            ):
                if self._follows_videos(picker, default_for):
                    picker.setText(str(default_for(self.videos_picker.path())))
        self._previous_videos_dir = self.videos_picker.text()
        self.refresh_summary()

    def refresh_summary(self) -> None:
        videos_dir = self.videos_picker.path()
        thumbs_dir = self.thumbs_picker.path()
        has_videos_dir = bool(self.videos_picker.text())
        self.trash_default_button.setEnabled(has_videos_dir)
        self.maybe_default_button.setEnabled(has_videos_dir)
        self._refresh_saved_session()

        if not has_videos_dir or not videos_dir.is_dir():
            self.summary.setText("Selecione uma pasta de vídeos válida para começar.")
            self.volume.clear()
            self.start_button.setEnabled(False)
            return

        entries = library.scan(videos_dir, thumbs_dir, self.maybe_scan_dir())
        total = len(entries)
        from_maybe = sum(1 for e in entries if e.from_maybe)
        with_thumb = sum(1 for e in entries if e.thumb is not None)
        missing = total - with_thumb

        state = library.ReviewState(thumbs_dir)
        reviewed = sum(1 for e in entries if state.was_reviewed(e.name))
        will_generate = self.gen_group.isChecked()
        only_maybe = self.maybe_only.isChecked()
        pending = library.build_session(
            entries,
            state,
            random_session=False,
            session_size=0,
            skip_reviewed=self.skip_reviewed.isChecked(),
            # se as thumbs vão ser geradas agora, os vídeos sem thumb também entram
            require_thumb=not will_generate,
            only_maybe=only_maybe,
        )

        session_count = len(pending)
        if self.mode_random.isChecked():
            session_count = min(session_count, self.session_size.value())

        escopo = " — só do “talvez”" if only_maybe else ""
        ordem = " em ordem randômica" if self.shuffle_order.isChecked() else ""
        lines = [
            f"<b>{total}</b> vídeos · <b>{with_thumb}</b> com thumbnail · <b>{missing}</b> sem thumbnail",
            f"<b>{reviewed}</b> já revisados em sessões anteriores"
            + (f" · <b>{from_maybe}</b> vindos do “talvez”" if from_maybe else ""),
            f"Esta sessão vai mostrar <b>{session_count}</b> vídeo(s){escopo}{ordem}.",
        ]
        if only_maybe and not session_count:
            lines.append(
                "<i>A pasta “talvez” está vazia (ou os vídeos dela não têm thumbnail) — "
                "não há dúvida anterior para rever.</i>"
            )
        elif missing and not will_generate:
            lines.append(
                "<i>Os vídeos sem thumbnail ficam de fora — marque “Gerar thumbnails” para incluí-los.</i>"
            )
        self.summary.setText("<br>".join(lines))
        self._refresh_volume(entries, state)
        self.start_button.setEnabled(total > 0)

    def _refresh_volume(
        self, entries: list[library.VideoEntry], state: library.ReviewState
    ) -> None:
        """Painel de espaço: o que a pasta ocupa hoje e onde isso deve parar."""
        trash_dir = self.trash_picker.path() if self.trash_picker.text() else None
        stats = library.collect_stats(entries, state, trash_dir=trash_dir)
        size = library.format_size

        primeira = f"<b>{size(stats.total_bytes)}</b> em {stats.total_count} vídeo(s)"
        if stats.maybe_count:
            primeira += f" · <b>{size(stats.maybe_bytes)}</b> no “talvez”"
        if stats.trash_count:
            primeira += (
                f" · <b>{size(stats.trash_bytes)}</b> parados na quarentena "
                f"({stats.trash_count} vídeo(s), ainda ocupando disco)"
            )
        lines = [primeira]

        rate = stats.discard_rate
        if rate is None:
            lines.append(
                f"<i>A projeção do tamanho final aparece depois de "
                f"{library.MIN_DECIDED_FOR_RATE} vídeos decididos nesta versão — "
                "as decisões anteriores não registraram o tamanho.</i>"
            )
        else:
            lines.append(
                f"Você descarta <b>{rate:.0%}</b> do volume que decide "
                f"({stats.decided_count} vídeos decididos, {size(stats.decided_bytes)})."
            )
            lines.append(
                f"Faltam decidir {size(stats.pending_bytes)} — nesse ritmo, devem sobrar "
                f"<b>{size(stats.estimated_remaining)}</b> no fim do processo."
            )
        self.volume.setText("<br>".join(lines))

    # ------------------------------------------------------- sessão salva
    def _refresh_saved_session(self) -> None:
        """Mostra o convite a retomar quando há sessão guardada para estas pastas."""
        thumbs_dir = self.thumbs_picker.path()
        salva = library.load_session(thumbs_dir) if self.thumbs_picker.text() else None
        # uma sessão de outra pasta de vídeos não faz sentido aqui, mesmo
        # compartilhando as thumbnails
        if salva is not None and salva.videos_dir:
            atual = self.videos_picker.path()
            if Path(salva.videos_dir).expanduser() != atual:
                salva = None

        if salva is None:
            self.resume_box.hide()
            return

        posicao = min(salva.index + 1, salva.total)
        self.resume_label.setText(
            f"<b>Sessão interrompida</b> em {salva.saved_at_label} — {salva.total} vídeo(s), "
            f"{salva.decided} decidido(s), parou no #{posicao}.<br>"
            "<i>Nada foi movido: as decisões são aplicadas quando você finalizar.</i>"
        )
        self.resume_box.show()

    def _emit_resume(self) -> None:
        self.resume_requested.emit(self.current_config())

    def _discard_saved_session(self) -> None:
        answer = QMessageBox.question(
            self,
            "Descartar sessão salva",
            "As decisões guardadas nessa sessão são perdidas e os vídeos voltam "
            "a entrar em sessões novas.\n\nNenhum arquivo é movido ou apagado.",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer == QMessageBox.Discard:
            library.clear_session(self.thumbs_picker.path())
            self.refresh_summary()

    def _emit_start(self) -> None:
        self.start_requested.emit(self.current_config())
