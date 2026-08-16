"""Textos da interface em português e inglês.

Um dicionário simples em vez de `.ts`/`.qm` do Qt: são dois idiomas e o
projeto roda direto do código-fonte, sem passo de build. `tr` aceita
argumentos nomeados, que são aplicados com `str.format`.

As chaves seguem `tela.elemento`. Nenhum texto visível deve ser escrito
literalmente nos módulos de UI.
"""

from __future__ import annotations

import locale

#: código -> nome do idioma no próprio idioma, para o seletor da tela inicial
LANGUAGES: dict[str, str] = {
    "pt": "Português (Brasil)",
    "en": "English",
}

#: usado quando o locale do sistema não é reconhecido
FALLBACK = "en"

_current = FALLBACK


def detect_language() -> str:
    """Idioma do sistema, se for um dos suportados.

    O `QLocale` vem primeiro porque normaliza os três sistemas: o `locale` da
    biblioteca padrão devolve `Portuguese_Brazil` no Windows, e nada de útil
    quando o processo está no locale "C".
    """
    for code in (_qt_locale(), _stdlib_locale()):
        prefix = code.replace("-", "_").split("_")[0].lower()
        if prefix in LANGUAGES:
            return prefix
    return FALLBACK


def _qt_locale() -> str:
    # importado aqui dentro: `i18n` é carregado antes da interface existir
    from PySide6.QtCore import QLocale

    return QLocale.system().name()


def _stdlib_locale() -> str:
    try:
        return locale.getlocale()[0] or ""
    except ValueError:
        return ""


def set_language(code: str | None) -> str:
    """Define o idioma corrente. Vazio ou desconhecido cai na detecção."""
    global _current
    _current = code if code in LANGUAGES else detect_language()
    return _current


def current_language() -> str:
    return _current


def tr(key: str, /, **kwargs) -> str:
    """Texto da chave no idioma corrente, formatado com os argumentos dados.

    A chave é posicional para não colidir com um placeholder chamado `key`,
    que os rótulos com tecla de atalho usam.
    """
    entry = STRINGS.get(key)
    if entry is None:
        return key  # chave sem tradução aparece crua: erro visível, não silencioso
    text = entry.get(_current) or entry.get(FALLBACK, key)
    return text.format(**kwargs) if kwargs else text


def format_number(value: float, decimals: int = 0) -> str:
    """Número com os separadores do idioma corrente (1.234,5 / 1,234.5)."""
    text = f"{value:,.{decimals}f}"
    if _current == "pt":
        # de 1,234.5 (padrão do Python) para 1.234,5
        text = text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return text


STRINGS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------- genéricos
    "app.title": {
        "pt": "Gerenciador de Vídeos",
        "en": "Video Manager",
    },
    "common.cancel": {"pt": "Cancelar", "en": "Cancel"},
    "common.discard": {"pt": "Descartar", "en": "Discard"},
    "common.default": {"pt": "Padrão", "en": "Default"},
    "common.videos_count": {"pt": "{n} vídeo(s)", "en": "{n} video(s)"},
    # só campos numéricos: `%b`/`%A` sairiam no idioma do locale do sistema,
    # que não tem relação com o idioma escolhido aqui
    "format.datetime": {"pt": "%d/%m às %H:%M", "en": "%m/%d at %H:%M"},

    # ------------------------------------------------------------- decisões
    "decision.keep": {"pt": "manter", "en": "keep"},
    "decision.maybe": {"pt": "talvez", "en": "maybe"},
    "decision.delete": {"pt": "apagar", "en": "delete"},

    # ------------------------------------------------------- tela: idioma
    "setup.language": {"pt": "Idioma:", "en": "Language:"},
    "setup.language.tip": {
        "pt": "Troca o idioma da interface na hora. A escolha fica salva.",
        "en": "Switches the interface language right away. The choice is saved.",
    },

    # ------------------------------------------------------- tela: pastas
    "setup.folders": {"pt": "Pastas", "en": "Folders"},
    "setup.folders.videos": {"pt": "Vídeos:", "en": "Videos:"},
    "setup.folders.thumbs": {"pt": "Thumbnails:", "en": "Thumbnails:"},
    "setup.folders.trash": {"pt": "Descartes:", "en": "Discards:"},
    "setup.folders.maybe": {"pt": "Talvez:", "en": "Maybe:"},
    "setup.folders.videos.hint": {
        "pt": "pasta com os vídeos",
        "en": "folder holding the videos",
    },
    "setup.folders.thumbs.hint": {
        "pt": "pasta onde ficam/serão salvas as thumbs",
        "en": "folder where the thumbnails are (or will be) saved",
    },
    "setup.folders.trash.hint": {
        "pt": "quarentena (padrão: <vídeos>/{name})",
        "en": "quarantine (default: <videos>/{name})",
    },
    "setup.folders.maybe.hint": {
        "pt": "rever depois (padrão: <vídeos>/{name})",
        "en": "review later (default: <videos>/{name})",
    },
    "setup.folders.trash.default.tip": {
        "pt": "Apontar a quarentena para <pasta de vídeos>/{name}",
        "en": "Point the quarantine at <videos folder>/{name}",
    },
    "setup.folders.maybe.default.tip": {
        "pt": "Apontar o “talvez” para <pasta de vídeos>/{name}",
        "en": "Point “maybe” at <videos folder>/{name}",
    },
    "setup.folders.browse": {"pt": "Escolher pasta", "en": "Choose folder"},

    # --------------------------------------------------- tela: thumbnails
    "setup.gen": {"pt": "Gerar thumbnails", "en": "Generate thumbnails"},
    "setup.gen.tip": {
        "pt": "Desmarcado: abre direto a interface de revisão usando as thumbs já existentes.",
        "en": "Unchecked: goes straight to the review screen using the existing thumbnails.",
    },
    "setup.gen.only_missing": {
        "pt": "Somente vídeos que ainda não têm thumbnail",
        "en": "Only videos that have no thumbnail yet",
    },
    "setup.gen.grid": {"pt": "Grade:", "en": "Grid:"},
    "setup.gen.rows": {"pt": "linhas", "en": "rows"},
    "setup.gen.cols": {"pt": "colunas", "en": "columns"},
    "setup.gen.details": {"pt": "Detalhes:", "en": "Details:"},
    "setup.gen.cell_height": {"pt": "altura da célula", "en": "cell height"},
    "setup.gen.margin": {"pt": "margem", "en": "margin"},
    "setup.gen.workers": {"pt": "threads", "en": "threads"},
    "setup.gen.timestamp": {
        "pt": "Escrever o tempo em cada frame",
        "en": "Stamp the timestamp on each frame",
    },

    # ------------------------------------------------------- tela: sessão
    "setup.session": {"pt": "Sessão de revisão", "en": "Review session"},
    "setup.session.all": {
        "pt": "Revisar todos os vídeos com thumbnail",
        "en": "Review every video that has a thumbnail",
    },
    "setup.session.random": {
        "pt": "Verificação randômica — sortear apenas",
        "en": "Random check — draw only",
    },
    "setup.session.size_suffix": {"pt": " vídeos", "en": " videos"},
    "setup.session.skip_reviewed": {
        "pt": "Pular vídeos que já revisei em sessões anteriores",
        "en": "Skip videos I already reviewed in earlier sessions",
    },
    "setup.session.shuffle": {
        "pt": "Mostrar em ordem randômica, e não alfabética",
        "en": "Show in random order instead of alphabetical",
    },
    "setup.session.shuffle.tip": {
        "pt": "Embaralha a ordem de exibição da sessão. Útil numa pasta onde os "
              "nomes agrupam o conteúdo — a ordem alfabética faz você ver tudo de "
              "um tipo de uma vez.",
        "en": "Shuffles the order the session is shown in. Useful in a folder where "
              "the names group the content — alphabetical order makes you watch "
              "everything of one kind in a row.",
    },
    "setup.session.maybe_label": {
        "pt": "Vídeos do “talvez”:",
        "en": "Videos in “maybe”:",
    },
    "setup.session.maybe.ignore": {"pt": "deixar de fora", "en": "leave out"},
    "setup.session.maybe.include": {"pt": "incluir na sessão", "en": "include in the session"},
    "setup.session.maybe.only": {"pt": "somente eles", "en": "only those"},
    "setup.session.maybe.ignore.tip": {
        "pt": "A sessão ignora a pasta “talvez”.",
        "en": "The session ignores the “maybe” folder.",
    },
    "setup.session.maybe.include.tip": {
        "pt": "Traz de volta o que ficou na pasta “talvez”, junto com os demais. "
              "Manter devolve o vídeo à pasta de vídeos; apagar manda para a quarentena.",
        "en": "Brings back whatever is sitting in the “maybe” folder, alongside the rest. "
              "Keeping returns the video to the videos folder; deleting sends it to quarantine.",
    },
    "setup.session.maybe.only.tip": {
        "pt": "A sessão inteira é feita das dúvidas anteriores — nenhum vídeo novo entra.",
        "en": "The whole session is made of earlier doubts — no new video comes in.",
    },

    # ------------------------------------------------ tela: sessão salva
    "setup.resume.button": {"pt": "Retomar", "en": "Resume"},
    "setup.resume.button.tip": {
        "pt": "Continuar a sessão salva de onde ela parou",
        "en": "Continue the saved session from where it stopped",
    },
    "setup.resume.discard.tip": {
        "pt": "Esquecer a sessão salva e liberar esses vídeos para novas sessões",
        "en": "Forget the saved session and free those videos for new ones",
    },
    "setup.resume.label": {
        "pt": "<b>Sessão interrompida</b> em {when} — {total} vídeo(s), "
              "{decided} decidido(s), parou no #{position}.<br>"
              "<i>Nada foi movido: as decisões são aplicadas quando você finalizar.</i>",
        "en": "<b>Session interrupted</b> on {when} — {total} video(s), "
              "{decided} decided, stopped at #{position}.<br>"
              "<i>Nothing was moved: decisions are applied when you finish.</i>",
    },
    "setup.resume.discard.title": {
        "pt": "Descartar sessão salva",
        "en": "Discard saved session",
    },
    "setup.resume.discard.body": {
        "pt": "As decisões guardadas nessa sessão são perdidas e os vídeos voltam "
              "a entrar em sessões novas.\n\nNenhum arquivo é movido ou apagado.",
        "en": "The decisions stored in that session are lost and the videos go back "
              "into new sessions.\n\nNo file is moved or deleted.",
    },

    # ---------------------------------------------------- tela: resumo
    "setup.summary.no_folder": {
        "pt": "Selecione uma pasta de vídeos válida para começar.",
        "en": "Select a valid videos folder to start.",
    },
    "setup.summary.counts": {
        "pt": "<b>{total}</b> vídeos · <b>{with_thumb}</b> com thumbnail · "
              "<b>{missing}</b> sem thumbnail",
        "en": "<b>{total}</b> videos · <b>{with_thumb}</b> with a thumbnail · "
              "<b>{missing}</b> without one",
    },
    "setup.summary.reviewed": {
        "pt": "<b>{n}</b> já revisados em sessões anteriores",
        "en": "<b>{n}</b> already reviewed in earlier sessions",
    },
    "setup.summary.from_maybe": {
        "pt": " · <b>{n}</b> vindos do “talvez”",
        "en": " · <b>{n}</b> coming from “maybe”",
    },
    "setup.summary.session": {
        "pt": "Esta sessão vai mostrar <b>{n}</b> vídeo(s){scope}{order}.",
        "en": "This session will show <b>{n}</b> video(s){scope}{order}.",
    },
    "setup.summary.scope_maybe": {"pt": " — só do “talvez”", "en": " — from “maybe” only"},
    "setup.summary.order_random": {"pt": " em ordem randômica", "en": " in random order"},
    "setup.summary.maybe_empty": {
        "pt": "<i>A pasta “talvez” está vazia (ou os vídeos dela não têm thumbnail) — "
              "não há dúvida anterior para rever.</i>",
        "en": "<i>The “maybe” folder is empty (or its videos have no thumbnail) — "
              "there is no earlier doubt to revisit.</i>",
    },
    "setup.summary.missing_thumbs": {
        "pt": "<i>Os vídeos sem thumbnail ficam de fora — marque “Gerar thumbnails” "
              "para incluí-los.</i>",
        "en": "<i>Videos without a thumbnail are left out — check “Generate thumbnails” "
              "to include them.</i>",
    },

    # ---------------------------------------------------- tela: volume
    "setup.volume.tip": {
        "pt": "A projeção aplica ao volume ainda não revisado a mesma proporção "
              "de descarte das decisões que você já tomou.",
        "en": "The projection applies to the not-yet-reviewed volume the same discard "
              "ratio as the decisions you have already made.",
    },
    "setup.volume.total": {
        "pt": "<b>{size}</b> em {count} vídeo(s)",
        "en": "<b>{size}</b> across {count} video(s)",
    },
    "setup.volume.maybe": {
        "pt": " · <b>{size}</b> no “talvez”",
        "en": " · <b>{size}</b> in “maybe”",
    },
    "setup.volume.trash": {
        "pt": " · <b>{size}</b> parados na quarentena ({count} vídeo(s), ainda ocupando disco)",
        "en": " · <b>{size}</b> sitting in quarantine ({count} video(s), still taking up disk)",
    },
    "setup.volume.no_rate": {
        "pt": "<i>A projeção do tamanho final aparece depois de {n} vídeos decididos "
              "nesta versão — as decisões anteriores não registraram o tamanho.</i>",
        "en": "<i>The final-size projection shows up after {n} videos decided in this "
              "version — earlier decisions did not record the size.</i>",
    },
    "setup.volume.rate": {
        "pt": "Você descarta <b>{rate}</b> do volume que decide "
              "({count} vídeos decididos, {size}).",
        "en": "You discard <b>{rate}</b> of the volume you decide on "
              "({count} videos decided, {size}).",
    },
    "setup.volume.projection": {
        "pt": "Faltam decidir {pending} — nesse ritmo, devem sobrar "
              "<b>{remaining}</b> no fim do processo.",
        "en": "{pending} still to decide — at this pace, <b>{remaining}</b> should be "
              "left when it is over.",
    },

    # ---------------------------------------------------- tela: ações
    "setup.rescan": {"pt": "Reanalisar pastas", "en": "Rescan folders"},
    "setup.shortcuts": {"pt": "Atalhos…", "en": "Shortcuts…"},
    "setup.shortcuts.tip": {
        "pt": "Escolher as teclas usadas na tela de revisão",
        "en": "Choose the keys used on the review screen",
    },
    "setup.start": {"pt": "Iniciar", "en": "Start"},

    # ------------------------------------------------------ avisos: início
    "app.invalid_folder.title": {"pt": "Pasta inválida", "en": "Invalid folder"},
    "app.invalid_folder.body": {
        "pt": "A pasta de vídeos não existe.",
        "en": "The videos folder does not exist.",
    },
    "app.thumbs_folder.title": {"pt": "Pasta de thumbnails", "en": "Thumbnails folder"},
    "app.thumbs_folder.empty": {
        "pt": "Informe a pasta onde ficam (ou serão salvas) as thumbnails.",
        "en": "Tell me the folder where the thumbnails are (or will be) saved.",
    },
    "app.thumbs_folder.missing": {
        "pt": "A pasta de thumbnails não existe. Marque “Gerar thumbnails” ou "
              "corrija o caminho.",
        "en": "The thumbnails folder does not exist. Check “Generate thumbnails” or "
              "fix the path.",
    },
    "app.same_folders.title": {"pt": "Pastas iguais", "en": "Same folder twice"},
    "app.same_folders.body": {
        "pt": "As pastas de descartes e de “talvez” precisam ser diferentes.",
        "en": "The discards and “maybe” folders have to be different.",
    },

    # -------------------------------------------------- avisos: thumbnails
    "app.gen.nothing.title": {"pt": "Nada a gerar", "en": "Nothing to generate"},
    "app.gen.nothing.body": {
        "pt": "Todos os vídeos já possuem thumbnail. Indo para a revisão.",
        "en": "Every video already has a thumbnail. Going to the review screen.",
    },
    "app.gen.progress.title": {"pt": "Processando", "en": "Working"},
    "app.gen.progress.label": {"pt": "Gerando thumbnails…", "en": "Generating thumbnails…"},
    "app.gen.progress.detail": {
        "pt": "Gerando thumbnails… {done}/{total}\n{name}",
        "en": "Generating thumbnails… {done}/{total}\n{name}",
    },
    "app.gen.failed.title": {"pt": "Alguns vídeos falharam", "en": "Some videos failed"},
    "app.gen.failed.body": {
        "pt": "{ok} thumbnail(s) gerada(s), {failed} com erro:\n\n{detail}",
        "en": "{ok} thumbnail(s) generated, {failed} with errors:\n\n{detail}",
    },
    "app.gen.failed.more": {"pt": "\n… e mais {n}", "en": "\n… and {n} more"},

    # ----------------------------------------------------- avisos: revisão
    "app.nothing.title": {"pt": "Nada para revisar", "en": "Nothing to review"},
    "app.nothing.only_maybe": {
        "pt": "Nenhum vídeo com thumbnail na pasta “talvez”.\n"
              "Escolha “incluir na sessão” ou “deixar de fora” para rever o resto.",
        "en": "No video with a thumbnail in the “maybe” folder.\n"
              "Pick “include in the session” or “leave out” to review the rest.",
    },
    "app.nothing.all_reviewed": {
        "pt": "Nenhum vídeo com thumbnail pendente de revisão.\n"
              "Desmarque “Pular vídeos já revisados” para rever tudo de novo.",
        "en": "No video with a thumbnail is pending review.\n"
              "Uncheck “Skip videos I already reviewed” to go through everything again.",
    },
    "app.overwrite.title": {"pt": "Há uma sessão salva", "en": "There is a saved session"},
    "app.overwrite.body": {
        "pt": "Existe uma sessão de {when} com {total} vídeo(s) e {decided} decisão(ões) "
              "ainda não aplicada(s).\n\n"
              "Começar uma sessão nova descarta essas marcações. "
              "Para continuar de onde parou, volte e use “Retomar”.",
        "en": "There is a session from {when} with {total} video(s) and {decided} decision(s) "
              "not applied yet.\n\n"
              "Starting a new session throws those marks away. "
              "To continue where you stopped, go back and use “Resume”.",
    },
    "app.resume.none.title": {"pt": "Sem sessão salva", "en": "No saved session"},
    "app.resume.none.body": {
        "pt": "Não há sessão guardada para esta pasta de thumbnails.",
        "en": "There is no session stored for this thumbnails folder.",
    },
    "app.resume.empty.title": {"pt": "Sessão vazia", "en": "Empty session"},
    "app.resume.empty.body": {
        "pt": "Nenhum vídeo da sessão salva ainda está nas pastas. A sessão foi descartada.",
        "en": "None of the saved session's videos are in the folders anymore. "
              "The session was discarded.",
    },
    "app.resume.partial.title": {
        "pt": "Sessão retomada parcialmente",
        "en": "Session partially resumed",
    },
    "app.resume.partial.body": {
        "pt": "{missing} vídeo(s) da sessão não estão mais nas pastas e ficaram de fora.\n"
              "Retomando com os {remaining} restantes.",
        "en": "{missing} video(s) from the session are no longer in the folders and were "
              "left out.\nResuming with the remaining {remaining}.",
    },

    # -------------------------------------------------------- avisos: saída
    "app.exit.title": {"pt": "Sair da revisão", "en": "Leave the review"},
    "app.exit.text": {
        "pt": "Há decisões desta sessão que ainda não foram aplicadas.",
        "en": "This session has decisions that have not been applied yet.",
    },
    "app.exit.detail": {
        "pt": "<b>Salvar</b> guarda a sessão como está — dá para retomar na tela inicial.<br>"
              "<b>Aplicar</b> move os vídeos agora e encerra a sessão.<br>"
              "<b>Descartar</b> perde as marcações.",
        "en": "<b>Save</b> stores the session as it is — you can resume it from the "
              "start screen.<br>"
              "<b>Apply</b> moves the videos now and ends the session.<br>"
              "<b>Discard</b> loses the marks.",
    },
    "app.exit.save": {"pt": "Salvar sessão e sair", "en": "Save session and leave"},
    "app.exit.apply": {"pt": "Aplicar e sair", "en": "Apply and leave"},

    # ----------------------------------------------------- tela de revisão
    "review.no_thumb": {
        "pt": "Sem thumbnail para este vídeo",
        "en": "No thumbnail for this video",
    },
    "review.bad_image": {
        "pt": "Não foi possível carregar a imagem",
        "en": "The image could not be loaded",
    },
    "review.empty": {"pt": "Nenhum vídeo nesta sessão", "en": "No video in this session"},
    "review.prev": {"pt": "← Anterior ({key})", "en": "← Previous ({key})"},
    "review.next": {"pt": "Próximo ({key}) →", "en": "Next ({key}) →"},
    "review.keep": {"pt": "Manter ({key})", "en": "Keep ({key})"},
    "review.maybe": {"pt": "Talvez ({key})", "en": "Maybe ({key})"},
    "review.delete": {"pt": "Apagar ({key})", "en": "Delete ({key})"},
    "review.open": {"pt": "Abrir vídeo ({key})", "en": "Open video ({key})"},
    "review.save": {"pt": "Salvar e sair", "en": "Save and leave"},
    "review.save.tip": {
        "pt": "Guarda esta sessão como está — decisões e posição — para retomar depois.\n"
              "Nada é movido agora.",
        "en": "Stores this session as it is — decisions and position — to resume later.\n"
              "Nothing is moved now.",
    },
    "review.finish": {"pt": "Aplicar e finalizar", "en": "Apply and finish"},
    "review.hint.zoom": {"pt": " · clique na imagem = zoom", "en": " · click the image = zoom"},
    "review.counts": {
        "pt": "{size}   ·   manter: {keep}   talvez: {maybe}   apagar: {delete}   "
              "pendentes: {pending}{origin}",
        "en": "{size}   ·   keep: {keep}   maybe: {maybe}   delete: {delete}   "
              "pending: {pending}{origin}",
    },
    "review.from_maybe": {"pt": "  ·   veio do “talvez”", "en": "  ·   came from “maybe”"},
    "review.status.keep": {"pt": "● MANTER", "en": "● KEEP"},
    "review.status.maybe": {"pt": "● TALVEZ", "en": "● MAYBE"},
    "review.status.delete": {"pt": "● APAGAR", "en": "● DELETE"},
    "review.status.pending": {"pt": "○ pendente", "en": "○ pending"},

    # ------------------------------------------------- revisão: rodapé
    "review.volume.folder": {"pt": "Pasta: {size}", "en": "Folder: {size}"},
    "review.volume.marked": {"pt": "marcado — {parts}", "en": "marked — {parts}"},
    "review.volume.projection": {
        "pt": "projeção: ~{size} no fim ({rate} do volume decidido vai para a quarentena)",
        "en": "projection: ~{size} at the end ({rate} of the decided volume goes to quarantine)",
    },

    # ------------------------------------------------- revisão: diálogos
    "review.open.failed.title": {
        "pt": "Não foi possível abrir o vídeo",
        "en": "The video could not be opened",
    },
    "review.open.failed.body": {
        "pt": "{name}\n\n{reason}\n\nCaminho:\n{path}",
        "en": "{name}\n\n{reason}\n\nPath:\n{path}",
    },
    "review.end.title": {"pt": "Fim da sessão", "en": "End of the session"},
    "review.end.body": {
        "pt": "Você revisou todos os {total} vídeos desta sessão.\n"
              "{delete} para apagar ({delete_size}) · "
              "{maybe} para rever depois ({maybe_size}).\n\nAplicar agora?",
        "en": "You reviewed all {total} videos in this session.\n"
              "{delete} to delete ({delete_size}) · "
              "{maybe} to review later ({maybe_size}).\n\nApply now?",
    },
    "review.saved.title": {"pt": "Sessão salva", "en": "Session saved"},
    "review.saved.body": {
        "pt": "{total} vídeo(s) guardados, {decided} já decidido(s).<br><br>"
              "Nada foi movido. A tela inicial oferece <b>Retomar</b> enquanto esta "
              "sessão existir.",
        "en": "{total} video(s) stored, {decided} already decided.<br><br>"
              "Nothing was moved. The start screen offers <b>Resume</b> for as long as "
              "this session exists.",
    },
    "review.confirm.title": {"pt": "Confirmar movimentações", "en": "Confirm the moves"},
    "review.confirm.line": {
        "pt": "• {count} vídeo(s) — {size} — {reason}:\n    {dest}",
        "en": "• {count} video(s) — {size} — {reason}:\n    {dest}",
    },
    "review.confirm.footer": {
        "pt": "\n\nAs thumbnails permanecem onde estão.",
        "en": "\n\nThe thumbnails stay where they are.",
    },
    "review.confirm.to_delete": {"pt": "apagar", "en": "delete"},
    "review.confirm.to_maybe": {"pt": "rever depois", "en": "review later"},
    "review.confirm.to_videos": {
        "pt": "voltar para a pasta de vídeos",
        "en": "back to the videos folder",
    },
    "review.done.title": {"pt": "Sessão concluída", "en": "Session finished"},
    "review.done.line": {
        "pt": "<b>{count}</b> vídeo(s) — {size} — {text}",
        "en": "<b>{count}</b> video(s) — {size} — {text}",
    },
    "review.done.deleted": {
        "pt": "movido(s) para a quarentena",
        "en": "moved to quarantine",
    },
    "review.done.maybe": {
        "pt": "guardado(s) para rever depois",
        "en": "kept aside to review later",
    },
    "review.done.kept": {
        "pt": "mantido(s) e registrado(s) como revisados",
        "en": "kept and recorded as reviewed",
    },
    "review.done.projection": {
        "pt": "<br><br>No ritmo atual de descarte, a pasta deve estabilizar em <b>{size}</b>.",
        "en": "<br><br>At the current discard pace, the folder should settle at <b>{size}</b>.",
    },
    "review.done.errors": {"pt": "<br><br><b>Falhas:</b><br>", "en": "<br><br><b>Failures:</b><br>"},

    # ---------------------------------------------------------- atalhos
    "shortcuts.title": {"pt": "Atalhos da revisão", "en": "Review shortcuts"},
    "shortcuts.intro": {
        "pt": "Clique num campo e pressione a tecla que quer usar.",
        "en": "Click a field and press the key you want to use.",
    },
    "shortcuts.note": {
        "pt": "As teclas entre parênteses continuam valendo como alternativa. "
              "Enter aplica a sessão e não pode ser remapeado.",
        "en": "The keys in parentheses keep working as alternatives. "
              "Enter applies the session and cannot be remapped.",
    },
    "shortcuts.empty.title": {"pt": "Atalho em branco", "en": "Empty shortcut"},
    "shortcuts.empty.body": {
        "pt": "Defina uma tecla para: {actions}",
        "en": "Set a key for: {actions}",
    },
    "shortcuts.clash.title": {"pt": "Tecla repetida", "en": "Duplicate key"},
    "shortcuts.clash.body": {
        "pt": "A mesma tecla está em duas ações:\n\n{detail}",
        "en": "The same key is bound to two actions:\n\n{detail}",
    },
    "shortcuts.apply_hint": {"pt": "Enter aplica", "en": "Enter applies"},
    "action.prev": {"pt": "Vídeo anterior", "en": "Previous video"},
    "action.next": {"pt": "Próximo vídeo", "en": "Next video"},
    "action.keep": {"pt": "Manter", "en": "Keep"},
    "action.maybe": {"pt": "Talvez", "en": "Maybe"},
    "action.delete": {"pt": "Excluir", "en": "Delete"},
    "action.open": {"pt": "Abrir no player", "en": "Open in the player"},
    "action.zoom": {"pt": "Zoom 1:1", "en": "1:1 zoom"},

    # ------------------------------------------------------------- erros
    "error.file_gone": {
        "pt": "o arquivo não está mais nesse caminho",
        "en": "the file is no longer at that path",
    },
    "error.launcher_missing": {
        "pt": "`{launcher}` não foi encontrado no sistema",
        "en": "`{launcher}` was not found on the system",
    },
    "error.thumb.open": {
        "pt": "não foi possível abrir o vídeo",
        "en": "the video could not be opened",
    },
    "error.thumb.metadata": {
        "pt": "metadados inválidos (frames/fps)",
        "en": "invalid metadata (frames/fps)",
    },
    "error.thumb.frames": {
        "pt": "não foi possível ler frames",
        "en": "no frames could be read",
    },
}
