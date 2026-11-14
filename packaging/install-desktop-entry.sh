#!/usr/bin/env bash
# Installs the icon and the launcher into the current user's desktop
# environment, so Video Manager shows up in the application menu with its icon.
#
# Nothing here needs root: everything goes under $XDG_DATA_HOME (~/.local/share
# by default). Run `--uninstall` to remove the same files.
#
# On Wayland the icon on the taskbar comes from this .desktop file, matched to
# the window by app id — running the app without installing it leaves the
# window with the compositor's generic icon.

set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICONS_DIR="$DATA_HOME/icons/hicolor"

# reverse-DNS id, shared by the .desktop, the icon and the Wayland app id
# (the same value as APP_ID in video_manager/icons.py)
APP_ID="io.github.frubik.VideoManager"
DESKTOP_FILE="$APP_ID.desktop"
ICON_NAME="$APP_ID"

# the id the files had before the reverse-DNS one; still cleaned up so an
# upgrade does not leave a dead launcher in the menu
OLD_ID="video-manager"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_icons="$here/../video_manager/icons"

# nomes com prefixo de propósito: uma função chamada `install` teria
# precedência sobre /usr/bin/install e chamaria a si mesma sem parar
remove_files() {
    local id="$1"
    rm -f "$APPS_DIR/$id.desktop"
    find "$ICONS_DIR" \( -name "$id.png" -o -name "$id.svg" \) -delete 2>/dev/null || true
}

refresh_caches() {
    # sem eles o menu só percebe a mudança na próxima sessão
    command -v gtk-update-icon-cache >/dev/null 2>&1 &&
        gtk-update-icon-cache -qtf "$ICONS_DIR" 2>/dev/null || true
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database -q "$APPS_DIR" 2>/dev/null || true
    command -v kbuildsycoca6 >/dev/null 2>&1 &&
        kbuildsycoca6 >/dev/null 2>&1 || true
}

do_uninstall() {
    remove_files "$APP_ID"
    remove_files "$OLD_ID"
    refresh_caches
    echo "Removed $DESKTOP_FILE and the $ICON_NAME icons from $DATA_HOME."
}

do_install() {
    # The menu does not run the command through a login shell, so it may not
    # see ~/.local/bin even when the terminal does (KDE on Arch is one such
    # case). The launcher gets the absolute path found right now instead.
    local exec_path
    if ! exec_path="$(command -v video-manager 2>/dev/null)"; then
        exec_path="video-manager"
        echo "Warning: 'video-manager' is not on the PATH — the launcher will not" >&2
        echo "work until you run 'uv tool install --editable .' in the project" >&2
        echo "and then this script again." >&2
    fi

    remove_files "$OLD_ID"

    # os PNGs por tamanho: o tema do sistema escolhe o mais próximo sozinho
    for png in "$source_icons"/hicolor/*/apps/"$ICON_NAME".png; do
        size="$(basename "$(dirname "$(dirname "$png")")")"
        install -Dm644 "$png" "$ICONS_DIR/$size/apps/$ICON_NAME.png"
    done
    install -Dm644 "$source_icons/scalable/$ICON_NAME.svg" \
        "$ICONS_DIR/scalable/apps/$ICON_NAME.svg"

    install -d -m755 "$APPS_DIR"
    # Exec= keeps the bare command in the repo and gets the real path here
    # (quoted only when needed: some launchers dislike quotes they do not need)
    case "$exec_path" in *" "*) exec_path="\"$exec_path\"" ;; esac
    sed "s|^Exec=.*|Exec=$exec_path|" "$here/$DESKTOP_FILE" > "$APPS_DIR/$DESKTOP_FILE"
    chmod 644 "$APPS_DIR/$DESKTOP_FILE"

    refresh_caches

    echo "Installed:"
    echo "  $APPS_DIR/$DESKTOP_FILE  (Exec=$exec_path)"
    echo "  $ICONS_DIR/*/apps/$ICON_NAME.png"
}

case "${1:-}" in
    --uninstall) do_uninstall ;;
    "") do_install ;;
    *) echo "usage: $(basename "$0") [--uninstall]" >&2; exit 2 ;;
esac
