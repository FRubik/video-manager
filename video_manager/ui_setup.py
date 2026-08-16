"""Tela inicial: pastas, opções de geração e formato da sessão de revisão."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
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

from . import i18n, library
from .config import Config
from .i18n import tr
from .ui_shortcuts import ShortcutsDialog


class FolderPicker(QWidget):
    """Campo de texto com botão de procurar pasta."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.edit = QLineEdit()
        self.edit.editingFinished.connect(self.changed.emit)

        self._browse_button = QToolButton()
        self._browse_button.setText("…")
        self._browse_button.clicked.connect(self._browse)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.edit)
        self._layout.addWidget(self._browse_button)

    def add_button(self, callback) -> QToolButton:
        """Acrescenta um botão extra à direita do campo (texto vem no retranslate)."""
        button = QToolButton()
        button.clicked.connect(callback)
        self._layout.addWidget(button)
        return button

    def set_placeholder(self, text: str) -> None:
        self.edit.setPlaceholderText(text)

    def retranslate(self) -> None:
        self._browse_button.setToolTip(tr("setup.folders.browse"))

    def _browse(self) -> None:
        start = self.edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, tr("setup.folders.browse"), start)
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
    language_changed = Signal(str)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        #: pasta de vídeos anterior, para saber se a quarentena ainda é a padrão dela
        self._previous_videos_dir = ""
        self._build_ui()
        self._load_config()
        self.retranslate()  # termina em `refresh_summary`, já com os campos carregados

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # --- título + idioma ---
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.language_label = QLabel()
        self.language_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.currentIndexChanged.connect(self._on_language_selected)
        top.addWidget(self.title, stretch=1)
        top.addWidget(self.language_label)
        top.addWidget(self.language_combo)
        root.addLayout(top)

        # --- pastas ---
        self.folders_group = QGroupBox()
        folders_form = QFormLayout(self.folders_group)
        self.videos_picker = FolderPicker()
        self.thumbs_picker = FolderPicker()
        self.trash_picker = FolderPicker()
        self.maybe_picker = FolderPicker()
        # os rótulos são guardados um a um: `labelForField` não devolve nada
        # para linhas criadas sem texto, e o texto só chega no `retranslate`
        self.videos_label = QLabel()
        self.thumbs_label = QLabel()
        self.trash_label = QLabel()
        self.maybe_folder_label = QLabel()
        folders_form.addRow(self.videos_label, self.videos_picker)
        folders_form.addRow(self.thumbs_label, self.thumbs_picker)
        self.trash_default_button = self.trash_picker.add_button(
            lambda: self._use_default(self.trash_picker, library.default_trash_dir),
        )
        folders_form.addRow(self.trash_label, self.trash_picker)
        self.maybe_default_button = self.maybe_picker.add_button(
            lambda: self._use_default(self.maybe_picker, library.default_maybe_dir),
        )
        folders_form.addRow(self.maybe_folder_label, self.maybe_picker)
        root.addWidget(self.folders_group)

        self.videos_picker.changed.connect(self._on_videos_changed)
        self.thumbs_picker.changed.connect(self.refresh_summary)

        # --- geração ---
        self.gen_group = QGroupBox()
        self.gen_group.setCheckable(True)
        gen_form = QFormLayout(self.gen_group)

        self.only_missing = QCheckBox()
        gen_form.addRow(self.only_missing)

        grid_row = QHBoxLayout()
        self.n_rows = QSpinBox()
        self.n_rows.setRange(1, 12)
        self.n_cols = QSpinBox()
        self.n_cols.setRange(1, 12)
        self.rows_label = QLabel()
        self.cols_label = QLabel()
        grid_row.addWidget(self.rows_label)
        grid_row.addWidget(self.n_rows)
        grid_row.addSpacing(12)
        grid_row.addWidget(self.cols_label)
        grid_row.addWidget(self.n_cols)
        grid_row.addStretch()
        self.grid_label = QLabel()
        gen_form.addRow(self.grid_label, self._wrap(grid_row))

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
        self.cell_height_label = QLabel()
        self.margin_label = QLabel()
        self.workers_label = QLabel()
        detail_row.addWidget(self.cell_height_label)
        detail_row.addWidget(self.cell_height)
        detail_row.addSpacing(12)
        detail_row.addWidget(self.margin_label)
        detail_row.addWidget(self.margin)
        detail_row.addSpacing(12)
        detail_row.addWidget(self.workers_label)
        detail_row.addWidget(self.workers)
        detail_row.addStretch()
        self.details_label = QLabel()
        gen_form.addRow(self.details_label, self._wrap(detail_row))

        self.add_timestamp = QCheckBox()
        gen_form.addRow(self.add_timestamp)
        root.addWidget(self.gen_group)

        self.gen_group.toggled.connect(self.refresh_summary)

        # --- sessão ---
        self.session_group = QGroupBox()
        session_layout = QVBoxLayout(self.session_group)

        self.mode_all = QRadioButton()
        self.mode_random = QRadioButton()
        random_row = QHBoxLayout()
        random_row.addWidget(self.mode_random)
        self.session_size = QSpinBox()
        self.session_size.setRange(1, 10000)
        random_row.addWidget(self.session_size)
        random_row.addStretch()

        self.skip_reviewed = QCheckBox()
        self.shuffle_order = QCheckBox()

        # o “talvez” é escopo, não quantidade: por isso um grupo próprio, e não
        # mais um modo ao lado de “revisar todos” e “verificação randômica”
        maybe_row = QHBoxLayout()
        self.maybe_label = QLabel()
        maybe_row.addWidget(self.maybe_label)
        self.maybe_ignore = QRadioButton()
        self.maybe_include = QRadioButton()
        self.maybe_only = QRadioButton()
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
        root.addWidget(self.session_group)

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
        self.resume_button = QPushButton()
        self.resume_button.clicked.connect(self._emit_resume)
        self.resume_discard_button = QPushButton()
        self.resume_discard_button.clicked.connect(self._discard_saved_session)
        resume_layout.addWidget(self.resume_label, stretch=1)
        resume_layout.addWidget(self.resume_button)
        resume_layout.addWidget(self.resume_discard_button)
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
        root.addWidget(self.volume)

        root.addStretch()

        actions = QHBoxLayout()
        self.rescan_button = QPushButton()
        self.rescan_button.clicked.connect(self.refresh_summary)
        self.shortcuts_button = QPushButton()
        self.shortcuts_button.clicked.connect(self._edit_shortcuts)
        self.start_button = QPushButton()
        self.start_button.setDefault(True)
        self.start_button.setMinimumWidth(140)
        self.start_button.clicked.connect(self._emit_start)
        actions.addWidget(self.rescan_button)
        actions.addWidget(self.shortcuts_button)
        actions.addStretch()
        actions.addWidget(self.start_button)
        root.addLayout(actions)

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    # --------------------------------------------------------------- idioma
    def retranslate(self) -> None:
        """Reescreve todo o texto fixo da tela no idioma corrente."""
        self.title.setText(tr("app.title"))
        self.language_label.setText(tr("setup.language"))
        self.language_combo.setToolTip(tr("setup.language.tip"))
        self._select_current_language()

        # --- pastas ---
        self.folders_group.setTitle(tr("setup.folders"))
        trash_name = library.default_trash_dir_name()
        maybe_name = library.default_maybe_dir_name()
        for picker, label, label_key, hint_key, hint_name in (
            (self.videos_picker, self.videos_label,
             "setup.folders.videos", "setup.folders.videos.hint", None),
            (self.thumbs_picker, self.thumbs_label,
             "setup.folders.thumbs", "setup.folders.thumbs.hint", None),
            (self.trash_picker, self.trash_label,
             "setup.folders.trash", "setup.folders.trash.hint", trash_name),
            (self.maybe_picker, self.maybe_folder_label,
             "setup.folders.maybe", "setup.folders.maybe.hint", maybe_name),
        ):
            label.setText(tr(label_key))
            picker.set_placeholder(
                tr(hint_key) if hint_name is None else tr(hint_key, name=hint_name)
            )
            picker.retranslate()
        self.trash_default_button.setText(tr("common.default"))
        self.trash_default_button.setToolTip(
            tr("setup.folders.trash.default.tip", name=trash_name)
        )
        self.maybe_default_button.setText(tr("common.default"))
        self.maybe_default_button.setToolTip(
            tr("setup.folders.maybe.default.tip", name=maybe_name)
        )

        # --- geração ---
        self.gen_group.setTitle(tr("setup.gen"))
        self.gen_group.setToolTip(tr("setup.gen.tip"))
        self.only_missing.setText(tr("setup.gen.only_missing"))
        self.grid_label.setText(tr("setup.gen.grid"))
        self.rows_label.setText(tr("setup.gen.rows"))
        self.cols_label.setText(tr("setup.gen.cols"))
        self.details_label.setText(tr("setup.gen.details"))
        self.cell_height_label.setText(tr("setup.gen.cell_height"))
        self.margin_label.setText(tr("setup.gen.margin"))
        self.workers_label.setText(tr("setup.gen.workers"))
        self.add_timestamp.setText(tr("setup.gen.timestamp"))

        # --- sessão ---
        self.session_group.setTitle(tr("setup.session"))
        self.mode_all.setText(tr("setup.session.all"))
        self.mode_random.setText(tr("setup.session.random"))
        self.session_size.setSuffix(tr("setup.session.size_suffix"))
        self.skip_reviewed.setText(tr("setup.session.skip_reviewed"))
        self.shuffle_order.setText(tr("setup.session.shuffle"))
        self.shuffle_order.setToolTip(tr("setup.session.shuffle.tip"))
        self.maybe_label.setText(tr("setup.session.maybe_label"))
        for button, key in (
            (self.maybe_ignore, "ignore"),
            (self.maybe_include, "include"),
            (self.maybe_only, "only"),
        ):
            button.setText(tr(f"setup.session.maybe.{key}"))
            button.setToolTip(tr(f"setup.session.maybe.{key}.tip"))

        # --- retomada e ações ---
        self.resume_button.setText(tr("setup.resume.button"))
        self.resume_button.setToolTip(tr("setup.resume.button.tip"))
        self.resume_discard_button.setText(tr("common.discard"))
        self.resume_discard_button.setToolTip(tr("setup.resume.discard.tip"))
        self.volume.setToolTip(tr("setup.volume.tip"))
        self.rescan_button.setText(tr("setup.rescan"))
        self.shortcuts_button.setText(tr("setup.shortcuts"))
        self.shortcuts_button.setToolTip(tr("setup.shortcuts.tip"))
        self.start_button.setText(tr("setup.start"))

        # os textos dinâmicos (resumo, volume, sessão salva) vêm daqui
        self.refresh_summary()

    def _select_current_language(self) -> None:
        """Deixa o combo no idioma corrente sem disparar uma nova troca."""
        index = self.language_combo.findData(i18n.current_language())
        if index < 0:
            return
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(index)
        self.language_combo.blockSignals(False)

    def _on_language_selected(self) -> None:
        code = self.language_combo.currentData()
        if not code or code == i18n.current_language():
            return
        # o resto da tela vai junto: a escolha de idioma não é motivo para
        # perder o que já está preenchido aqui
        self.current_config().save()
        self.language_changed.emit(code)

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
        c.language = self.language_combo.currentData() or c.language
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

    def _follows_videos(self, picker: FolderPicker, candidates_for) -> bool:
        """A pasta está vazia ou ainda é a padrão da pasta de vídeos anterior?

        Vale qualquer um dos nomes padrão, não só o do idioma corrente: trocar
        de idioma não pode fazer a pasta parar de acompanhar a de vídeos.
        """
        current = picker.text()
        if not current:
            return True
        if not self._previous_videos_dir:
            return False
        previous = Path(self._previous_videos_dir).expanduser()
        return Path(current).expanduser() in candidates_for(previous)

    def _on_videos_changed(self) -> None:
        if self.videos_picker.text():
            for picker, default_for, candidates_for in (
                (self.trash_picker, library.default_trash_dir, library.trash_dir_candidates),
                (self.maybe_picker, library.default_maybe_dir, library.maybe_dir_candidates),
            ):
                if self._follows_videos(picker, candidates_for):
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
            self.summary.setText(tr("setup.summary.no_folder"))
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

        escopo = tr("setup.summary.scope_maybe") if only_maybe else ""
        ordem = tr("setup.summary.order_random") if self.shuffle_order.isChecked() else ""
        lines = [
            tr("setup.summary.counts", total=total, with_thumb=with_thumb, missing=missing),
            tr("setup.summary.reviewed", n=reviewed)
            + (tr("setup.summary.from_maybe", n=from_maybe) if from_maybe else ""),
            tr("setup.summary.session", n=session_count, scope=escopo, order=ordem),
        ]
        if only_maybe and not session_count:
            lines.append(tr("setup.summary.maybe_empty"))
        elif missing and not will_generate:
            lines.append(tr("setup.summary.missing_thumbs"))
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

        primeira = tr(
            "setup.volume.total", size=size(stats.total_bytes), count=stats.total_count
        )
        if stats.maybe_count:
            primeira += tr("setup.volume.maybe", size=size(stats.maybe_bytes))
        if stats.trash_count:
            primeira += tr(
                "setup.volume.trash", size=size(stats.trash_bytes), count=stats.trash_count
            )
        lines = [primeira]

        rate = stats.discard_rate
        if rate is None:
            lines.append(tr("setup.volume.no_rate", n=library.MIN_DECIDED_FOR_RATE))
        else:
            lines.append(
                tr(
                    "setup.volume.rate",
                    rate=library.format_rate(rate),
                    count=stats.decided_count,
                    size=size(stats.decided_bytes),
                )
            )
            lines.append(
                tr(
                    "setup.volume.projection",
                    pending=size(stats.pending_bytes),
                    remaining=size(stats.estimated_remaining),
                )
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
            tr(
                "setup.resume.label",
                when=salva.saved_at_label,
                total=salva.total,
                decided=salva.decided,
                position=posicao,
            )
        )
        self.resume_box.show()

    def _emit_resume(self) -> None:
        self.resume_requested.emit(self.current_config())

    def _discard_saved_session(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("setup.resume.discard.title"),
            tr("setup.resume.discard.body"),
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer == QMessageBox.Discard:
            library.clear_session(self.thumbs_picker.path())
            self.refresh_summary()

    def _emit_start(self) -> None:
        self.start_requested.emit(self.current_config())
