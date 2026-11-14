"""Janela principal: alterna entre a tela de configuração e a de revisão."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
)

from . import i18n, library
from .config import Config
from .i18n import tr
from .library import ReviewState, VideoEntry
from .thumbs import ThumbOptions
from .ui_review import ReviewView
from .ui_setup import SetupView
from .worker import ThumbWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1280, 820)

        self.config = Config.load()
        # antes de construir qualquer tela: elas leem os textos na criação
        i18n.set_language(self.config.language)
        self.setWindowTitle(tr("app.title"))
        self.setup_view = SetupView(self.config)
        self.review_view = ReviewView()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.setup_view)
        self.stack.addWidget(self.review_view)
        self.setCentralWidget(self.stack)

        self.review_view.apply_key_bindings(self.config.key_bindings)

        self.setup_view.start_requested.connect(self.on_start)
        self.setup_view.generate_requested.connect(self.on_generate_only)
        self.setup_view.resume_requested.connect(self.on_resume)
        self.setup_view.key_bindings_changed.connect(self.review_view.apply_key_bindings)
        self.setup_view.language_changed.connect(self.on_language_changed)
        self.review_view.session_finished.connect(self.on_session_finished)
        self.review_view.back_requested.connect(self.on_back_requested)

        self._worker: ThumbWorker | None = None
        self._progress: QProgressDialog | None = None
        self._pending_config: Config | None = None
        #: a geração corrente abre a revisão no fim, ou volta para a tela inicial
        self._review_after_generation = True
        #: pastas da última geração, citadas nos avisos de conclusão e de falha
        self._last_thumbs_dir = ""
        self._last_videos_dir = ""
        #: vídeos já concluídos no lote corrente, para o texto do progresso
        self._generated = (0, 0)
        # a barra anda por frame, e não por vídeo: num 4K de vários GB um único
        # vídeo leva minutos, e a barra parada passava a impressão de travamento
        self._gen_timer = QTimer(self)
        self._gen_timer.setInterval(250)
        self._gen_timer.timeout.connect(self._tick_generation)

    # --------------------------------------------------------------- idioma
    def on_language_changed(self, code: str) -> None:
        """Reescreve a interface inteira no idioma escolhido, sem reiniciar."""
        i18n.set_language(code)
        self.setWindowTitle(tr("app.title"))
        self.setup_view.retranslate()
        self.review_view.retranslate()

    # --------------------------------------------------------------- início
    def _prepare_folders(self, config: Config, *, needs_existing_thumbs: bool) -> bool:
        """Valida as pastas e preenche as que ficaram em branco. False aborta.

        `needs_existing_thumbs` só é verdadeiro quando nada será gerado agora:
        aí a pasta de thumbnails precisa já existir para haver o que revisar.
        """
        videos_dir = Path(config.videos_dir).expanduser()
        thumbs_dir = Path(config.thumbs_dir).expanduser() if config.thumbs_dir else Path()

        if not videos_dir.is_dir():
            QMessageBox.warning(self, tr("app.invalid_folder.title"), tr("app.invalid_folder.body"))
            return False
        if not config.thumbs_dir:
            QMessageBox.warning(self, tr("app.thumbs_folder.title"), tr("app.thumbs_folder.empty"))
            return False
        if needs_existing_thumbs and not thumbs_dir.is_dir():
            QMessageBox.warning(
                self, tr("app.thumbs_folder.title"), tr("app.thumbs_folder.missing")
            )
            return False
        if not config.trash_dir:
            config.trash_dir = str(library.default_trash_dir(videos_dir))
            self.setup_view.trash_picker.setText(config.trash_dir)
        if not config.maybe_dir:
            config.maybe_dir = str(library.default_maybe_dir(videos_dir))
            self.setup_view.maybe_picker.setText(config.maybe_dir)
        if Path(config.maybe_dir).expanduser() == Path(config.trash_dir).expanduser():
            QMessageBox.warning(self, tr("app.same_folders.title"), tr("app.same_folders.body"))
            return False
        return True

    def on_start(self, config: Config) -> None:
        if not self._prepare_folders(config, needs_existing_thumbs=not config.generate_thumbs):
            return

        videos_dir = Path(config.videos_dir).expanduser()
        thumbs_dir = Path(config.thumbs_dir).expanduser()

        # antes de gerar qualquer coisa: uma sessão nova apaga a que está guardada
        if not self._confirm_overwrite(thumbs_dir):
            return

        config.save()
        self._pending_config = config

        if config.generate_thumbs:
            self._start_generation(config, videos_dir, thumbs_dir)
        else:
            self._start_review(config)

    def on_generate_only(self, config: Config) -> None:
        """Gera as thumbnails e para por aí: nenhuma sessão de revisão é aberta.

        Como nada é movido nem decidido, a sessão guardada em disco continua
        intacta — por isso não há a pergunta de sobrescrita do “Iniciar”.
        """
        if not self._prepare_folders(config, needs_existing_thumbs=False):
            return

        config.save()
        self._pending_config = None
        self._start_generation(
            config,
            Path(config.videos_dir).expanduser(),
            Path(config.thumbs_dir).expanduser(),
            review_after=False,
        )

    # ----------------------------------------------------------- thumbnails
    def _start_generation(
        self,
        config: Config,
        videos_dir: Path,
        thumbs_dir: Path,
        review_after: bool = True,
    ) -> None:
        # o "talvez" entra aqui também: sem thumbnail ele não apareceria na revisão
        maybe_dir = Path(config.maybe_dir).expanduser() if config.scans_maybe else None
        entries = library.scan(videos_dir, thumbs_dir, maybe_dir)
        # com "somente faltantes" marcado, uma geração interrompida é retomada
        # de onde parou: só os vídeos sem thumbnail voltam para a fila
        pending = [e.video for e in entries if not (config.only_missing and e.thumb is not None)]
        self._review_after_generation = review_after

        if not pending:
            QMessageBox.information(
                self,
                tr("app.gen.nothing.title"),
                tr("app.gen.nothing.body" if review_after else "app.gen.nothing.body.only"),
            )
            if review_after:
                self._start_review(config)
            else:
                self.setup_view.refresh_summary()
            return

        opts = ThumbOptions(
            n_rows=config.n_rows,
            n_cols=config.n_cols,
            cell_height=config.cell_height,
            margin=config.margin,
            spacing=config.spacing,
            add_timestamp=config.add_timestamp,
            workers=config.workers,
            header=config.header,
            header_fields=list(config.header_fields),
        )

        self._generated = (0, len(pending))
        self._worker = ThumbWorker(pending, thumbs_dir, opts, parent=self)

        self._progress = QProgressDialog(
            tr("app.gen.progress.label"), tr("common.cancel"), 0, self._worker.frames_total, self
        )
        self._progress.setWindowTitle(tr("app.gen.progress.title"))
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.canceled.connect(self._cancel_generation)

        self._last_thumbs_dir = str(thumbs_dir)
        self._last_videos_dir = str(videos_dir)
        self._worker.progress.connect(self._on_generation_progress)
        self._worker.finished_with_results.connect(self._on_generation_finished)
        self._worker.start()
        self._gen_timer.start()

    def _cancel_generation(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        # o diálogo se esconde sozinho ao cancelar; ele volta dizendo o que
        # está acontecendo, porque o vídeo em curso ainda leva um frame para
        # perceber o pedido
        if self._progress is not None:
            self._progress.setLabelText(tr("app.gen.cancelling"))
            self._progress.show()

    def _on_generation_progress(self, done: int, total: int) -> None:
        self._generated = (done, total)
        self._tick_generation()

    def _tick_generation(self) -> None:
        """Repinta o diálogo com o andamento em frames do lote inteiro."""
        # `setValue` roda o event loop do diálogo modal, o que pode fechar e
        # zerar `self._progress` no meio deste método — por isso a cópia local.
        dialog = self._progress
        worker = self._worker
        if dialog is None or worker is None:
            return
        done, total = self._generated
        # o total cresce quando um vídeo cai no ffmpeg (AV1): a segunda passada
        # traz mais frames a fazer, e a barra precisa acompanhar
        dialog.setMaximum(worker.frames_total)
        if not worker.cancelled:
            texto = tr(
                "app.gen.progress.detail",
                done=done,
                total=total,
                frames=worker.frames_done,
                frames_total=worker.frames_total,
            )
            if worker.ffmpeg_fallbacks:
                texto += "\n" + tr("app.gen.progress.ffmpeg", n=worker.ffmpeg_fallbacks)
            dialog.setLabelText(texto)
        dialog.setValue(min(worker.frames_done, worker.frames_total))

    def _on_generation_finished(self, results: list) -> None:
        self._gen_timer.stop()
        # ler o estado do worker ANTES de mexer no diálogo: fechar um
        # QProgressDialog emite `canceled`, e deixar isso chegar ao
        # `_cancel_generation` marcaria como cancelada uma geração que terminou
        # sozinha — era o que fazia a mensagem final falar em cancelamento.
        cancelled = self._worker is not None and self._worker.cancelled
        self._worker = None
        if self._progress is not None:
            self._progress.canceled.disconnect(self._cancel_generation)
            self._progress.close()
            self._progress = None

        # o que foi abortado a pedido do usuário não é falha do vídeo
        failures = [r for r in results if not r.ok and not r.cancelled]
        generated = sum(1 for r in results if r.ok)
        if failures:
            detail = "\n".join(f"• {r.video.name}: {r.error}" for r in failures[:15])
            if len(failures) > 15:
                detail += tr("app.gen.failed.more", n=len(failures) - 15)
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(tr("app.gen.failed.title"))
            box.setText(
                tr(
                    "app.gen.failed.body",
                    ok=len(results) - len(failures),
                    failed=len(failures),
                    detail=detail,
                )
            )
            move_button = box.addButton(tr("app.gen.failed.move"), QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok)
            box.exec()
            if box.clickedButton() is move_button:
                self._move_failed([r.video for r in failures])

        if cancelled:
            # quem cancelou a geração não quer cair na revisão logo em seguida
            QMessageBox.information(
                self,
                tr("app.gen.cancelled.title"),
                tr("app.gen.cancelled.body", ok=generated),
            )
            self.setup_view.refresh_summary()
            return

        if not self._review_after_generation:
            if not failures:
                QMessageBox.information(
                    self,
                    tr("app.gen.done.title"),
                    tr("app.gen.done.body", ok=generated, folder=self._last_thumbs_dir),
                )
            self.setup_view.refresh_summary()
            return

        if self._pending_config is not None:
            self._start_review(self._pending_config)

    def _move_failed(self, videos: list[Path]) -> None:
        """Junta numa subpasta os vídeos cuja thumbnail falhou, para conferir à mão.

        A pasta é uma padrão dentro da pasta de vídeos (`_thumb_falhou`), não uma
        das pastas gerenciadas pelo app: é só um canto para abrir os arquivos e
        ver o que houve.
        """
        base = Path(self._last_videos_dir).expanduser() if self._last_videos_dir else None
        if base is None or not base.is_dir():
            base = videos[0].parent if videos else Path.home()
        dest_dir = library.default_failed_dir(base)

        answer = QMessageBox.question(
            self,
            tr("app.gen.failed.move.title"),
            tr("app.gen.failed.move.body", count=len(videos), folder=str(dest_dir)),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        moved = 0
        errors: list[str] = []
        for video in videos:
            try:
                library.move_video(video, dest_dir, "thumb_failed")
                moved += 1
            except OSError as exc:
                errors.append(f"• {video.name}: {exc}")

        body = tr("app.gen.failed.moved.body", moved=moved, folder=str(dest_dir))
        if errors:
            body += tr("app.gen.failed.moved.errors", detail="\n".join(errors[:15]))
        QMessageBox.information(self, tr("app.gen.failed.moved.title"), body)
        self.setup_view.refresh_summary()

    # ------------------------------------------------------------- revisão
    def _start_review(self, config: Config) -> None:
        videos_dir = Path(config.videos_dir).expanduser()
        thumbs_dir = Path(config.thumbs_dir).expanduser()
        trash_dir = Path(config.trash_dir).expanduser()
        maybe_dir = Path(config.maybe_dir).expanduser()

        entries: list[VideoEntry] = library.scan(
            videos_dir, thumbs_dir, maybe_dir if config.scans_maybe else None
        )
        state = ReviewState(thumbs_dir)
        session = library.build_session(
            entries,
            state,
            random_session=config.random_session,
            session_size=config.session_size,
            skip_reviewed=config.skip_reviewed,
            only_maybe=config.only_maybe,
            shuffle=config.shuffle_order,
        )

        if not session:
            motivo = tr(
                "app.nothing.only_maybe" if config.only_maybe else "app.nothing.all_reviewed"
            )
            QMessageBox.information(self, tr("app.nothing.title"), motivo)
            return

        self.review_view.load_session(
            session,
            state,
            videos_dir=videos_dir,
            thumbs_dir=thumbs_dir,
            trash_dir=trash_dir,
            maybe_dir=maybe_dir,
            all_entries=entries,
        )
        self.stack.setCurrentWidget(self.review_view)
        self.review_view.grab_keyboard_focus()

    def _confirm_overwrite(self, thumbs_dir: Path) -> bool:
        """Pergunta antes de deixar uma sessão nova apagar a que está guardada.

        True quando não há sessão salva ou o usuário aceitou perdê-la — e nesse
        caso o arquivo já vai embora, para a tela inicial não continuar
        oferecendo uma retomada que a sessão nova sobrescreveria.
        """
        salva = library.load_session(thumbs_dir)
        if salva is None:
            return True
        answer = QMessageBox.question(
            self,
            tr("app.overwrite.title"),
            tr(
                "app.overwrite.body",
                when=salva.saved_at_label,
                total=salva.total,
                decided=salva.decided,
            ),
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Discard:
            return False
        library.clear_session(thumbs_dir)
        return True

    # ------------------------------------------------------------- retomada
    def on_resume(self, config: Config) -> None:
        """Recarrega a sessão guardada em disco, casando-a com a pasta atual."""
        thumbs_dir = Path(config.thumbs_dir).expanduser()
        salva = library.load_session(thumbs_dir)
        if salva is None:
            QMessageBox.information(self, tr("app.resume.none.title"), tr("app.resume.none.body"))
            self.setup_view.refresh_summary()
            return

        videos_dir = Path(salva.videos_dir or config.videos_dir).expanduser()
        trash_dir = Path(salva.trash_dir or config.trash_dir).expanduser()
        maybe_dir = Path(salva.maybe_dir or config.maybe_dir).expanduser()

        # a varredura inclui o "talvez" independente da opção atual: a sessão
        # salva pode conter vídeos de lá, e eles precisam ser reencontrados
        entries = library.scan(videos_dir, thumbs_dir, maybe_dir)
        session, index, missing = library.restore_session(salva, entries)

        if not session:
            QMessageBox.warning(self, tr("app.resume.empty.title"), tr("app.resume.empty.body"))
            library.clear_session(thumbs_dir)
            self.setup_view.refresh_summary()
            return

        if missing:
            QMessageBox.information(
                self,
                tr("app.resume.partial.title"),
                tr("app.resume.partial.body", missing=missing, remaining=len(session)),
            )

        self.review_view.load_session(
            session,
            ReviewState(thumbs_dir),
            videos_dir=videos_dir,
            thumbs_dir=thumbs_dir,
            trash_dir=trash_dir,
            maybe_dir=maybe_dir,
            all_entries=entries,
            start_index=index,
            resumed=True,
        )
        self.stack.setCurrentWidget(self.review_view)
        self.review_view.grab_keyboard_focus()

    def on_session_finished(self, summary: dict) -> None:
        self.stack.setCurrentWidget(self.setup_view)
        self.setup_view.refresh_summary()

    def on_back_requested(self) -> None:
        self.stack.setCurrentWidget(self.setup_view)
        self.setup_view.refresh_summary()

    # --------------------------------------------------------------- saída
    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._gen_timer.stop()
            self._worker.cancel()
            self._worker.wait(30000)
        if (
            self.stack.currentWidget() is self.review_view
            and self.review_view.has_pending_changes()
            and not self._resolve_pending_on_exit()
        ):
            event.ignore()
            return
        self.setup_view.current_config().save()
        event.accept()

    def _resolve_pending_on_exit(self) -> bool:
        """Decisões não aplicadas na hora de fechar. True se pode sair."""
        box = QMessageBox(self)
        box.setWindowTitle(tr("app.exit.title"))
        box.setIcon(QMessageBox.Question)
        box.setText(tr("app.exit.text"))
        box.setInformativeText(tr("app.exit.detail"))
        salvar = box.addButton(tr("app.exit.save"), QMessageBox.AcceptRole)
        aplicar = box.addButton(tr("app.exit.apply"), QMessageBox.ApplyRole)
        box.addButton(tr("common.discard"), QMessageBox.DestructiveRole)
        box.addButton(tr("common.cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(salvar)
        box.exec()

        clicado = box.clickedButton()
        if clicado is salvar:
            self.review_view.autosave()
            return True
        if clicado is aplicar:
            self.review_view.finish()
            # a confirmação das movimentações pode ter sido cancelada lá dentro
            return self.review_view.applied
        if clicado is not None and box.buttonRole(clicado) == QMessageBox.DestructiveRole:
            # descartar é descartar: o autosave desta sessão também vai embora
            self.review_view.discard_saved_session()
            return True
        return False
