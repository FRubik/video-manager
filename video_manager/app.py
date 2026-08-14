"""Janela principal: alterna entre a tela de configuração e a de revisão."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
)

from . import library
from .config import Config
from .library import ReviewState, VideoEntry
from .thumbs import ThumbOptions
from .ui_review import ReviewView
from .ui_setup import SetupView
from .worker import ThumbWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerenciador de Vídeos")
        self.resize(1280, 820)

        self.config = Config.load()
        self.setup_view = SetupView(self.config)
        self.review_view = ReviewView()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.setup_view)
        self.stack.addWidget(self.review_view)
        self.setCentralWidget(self.stack)

        self.review_view.apply_key_bindings(self.config.key_bindings)

        self.setup_view.start_requested.connect(self.on_start)
        self.setup_view.key_bindings_changed.connect(self.review_view.apply_key_bindings)
        self.review_view.session_finished.connect(self.on_session_finished)

        self._worker: ThumbWorker | None = None
        self._progress: QProgressDialog | None = None
        self._pending_config: Config | None = None

    # --------------------------------------------------------------- início
    def on_start(self, config: Config) -> None:
        videos_dir = Path(config.videos_dir).expanduser()
        thumbs_dir = Path(config.thumbs_dir).expanduser() if config.thumbs_dir else Path()

        if not videos_dir.is_dir():
            QMessageBox.warning(self, "Pasta inválida", "A pasta de vídeos não existe.")
            return
        if not config.thumbs_dir:
            QMessageBox.warning(
                self, "Pasta de thumbnails", "Informe a pasta onde ficam (ou serão salvas) as thumbnails."
            )
            return
        if not config.generate_thumbs and not thumbs_dir.is_dir():
            QMessageBox.warning(
                self,
                "Pasta de thumbnails",
                "A pasta de thumbnails não existe. Marque “Gerar thumbnails” ou corrija o caminho.",
            )
            return
        if not config.trash_dir:
            config.trash_dir = str(library.default_trash_dir(videos_dir))
            self.setup_view.trash_picker.setText(config.trash_dir)
        if not config.maybe_dir:
            config.maybe_dir = str(library.default_maybe_dir(videos_dir))
            self.setup_view.maybe_picker.setText(config.maybe_dir)
        if Path(config.maybe_dir).expanduser() == Path(config.trash_dir).expanduser():
            QMessageBox.warning(
                self,
                "Pastas iguais",
                "As pastas de descartes e de “talvez” precisam ser diferentes.",
            )
            return

        config.save()
        self._pending_config = config

        if config.generate_thumbs:
            self._start_generation(config, videos_dir, thumbs_dir)
        else:
            self._start_review(config)

    # ----------------------------------------------------------- thumbnails
    def _start_generation(self, config: Config, videos_dir: Path, thumbs_dir: Path) -> None:
        # o "talvez" entra aqui também: sem thumbnail ele não apareceria na revisão
        maybe_dir = Path(config.maybe_dir).expanduser() if config.include_maybe else None
        entries = library.scan(videos_dir, thumbs_dir, maybe_dir)
        pending = [e.video for e in entries if not (config.only_missing and e.thumb is not None)]

        if not pending:
            QMessageBox.information(
                self, "Nada a gerar", "Todos os vídeos já possuem thumbnail. Indo para a revisão."
            )
            self._start_review(config)
            return

        opts = ThumbOptions(
            n_rows=config.n_rows,
            n_cols=config.n_cols,
            cell_height=config.cell_height,
            margin=config.margin,
            add_timestamp=config.add_timestamp,
            workers=config.workers,
        )

        self._progress = QProgressDialog(
            "Gerando thumbnails…", "Cancelar", 0, len(pending), self
        )
        self._progress.setWindowTitle("Processando")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.canceled.connect(self._cancel_generation)

        self._worker = ThumbWorker(pending, thumbs_dir, opts, parent=self)
        self._worker.progress.connect(self._on_generation_progress)
        self._worker.finished_with_results.connect(self._on_generation_finished)
        self._worker.start()

    def _cancel_generation(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _on_generation_progress(self, done: int, total: int, name: str) -> None:
        # `setValue` roda o event loop do diálogo modal, o que pode fechar e
        # zerar `self._progress` no meio deste método — por isso a cópia local.
        dialog = self._progress
        if dialog is None:
            return
        dialog.setLabelText(f"Gerando thumbnails… {done}/{total}\n{name}")
        dialog.setValue(done)

    def _on_generation_finished(self, results: list) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        self._worker = None

        failures = [r for r in results if not r.ok]
        if failures:
            detail = "\n".join(f"• {r.video.name}: {r.error}" for r in failures[:15])
            if len(failures) > 15:
                detail += f"\n… e mais {len(failures) - 15}"
            QMessageBox.warning(
                self,
                "Alguns vídeos falharam",
                f"{len(results) - len(failures)} thumbnail(s) gerada(s), "
                f"{len(failures)} com erro:\n\n{detail}",
            )

        if self._pending_config is not None:
            self._start_review(self._pending_config)

    # ------------------------------------------------------------- revisão
    def _start_review(self, config: Config) -> None:
        videos_dir = Path(config.videos_dir).expanduser()
        thumbs_dir = Path(config.thumbs_dir).expanduser()
        trash_dir = Path(config.trash_dir).expanduser()
        maybe_dir = Path(config.maybe_dir).expanduser()

        entries: list[VideoEntry] = library.scan(
            videos_dir, thumbs_dir, maybe_dir if config.include_maybe else None
        )
        state = ReviewState(thumbs_dir)
        session = library.build_session(
            entries,
            state,
            random_session=config.random_session,
            session_size=config.session_size,
            skip_reviewed=config.skip_reviewed,
        )

        if not session:
            QMessageBox.information(
                self,
                "Nada para revisar",
                "Nenhum vídeo com thumbnail pendente de revisão.\n"
                "Desmarque “Pular vídeos já revisados” para rever tudo de novo.",
            )
            return

        self.review_view.load_session(
            session,
            state,
            videos_dir=videos_dir,
            trash_dir=trash_dir,
            maybe_dir=maybe_dir,
            all_entries=entries,
        )
        self.stack.setCurrentWidget(self.review_view)
        self.review_view.grab_keyboard_focus()

    def on_session_finished(self, summary: dict) -> None:
        self.stack.setCurrentWidget(self.setup_view)
        self.setup_view.refresh_summary()

    # --------------------------------------------------------------- saída
    def closeEvent(self, event):
        if self.stack.currentWidget() is self.review_view and self.review_view.has_pending_changes():
            answer = QMessageBox.question(
                self,
                "Sair sem aplicar?",
                "Há decisões desta sessão que ainda não foram aplicadas.\n"
                "Sair agora descarta essas marcações.",
                QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Discard:
                event.ignore()
                return
        self.setup_view.current_config().save()
        event.accept()
