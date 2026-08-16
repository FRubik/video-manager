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
DESKTOP_FILE="video-manager.desktop"
ICON_NAME="video-manager"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_icons="$here/../video_manager/icons"

# nomes com prefixo de propósito: uma função chamada `install` teria
# precedência sobre /usr/bin/install e chamaria a si mesma sem parar
do_uninstall() {
    rm -f "$APPS_DIR/$DESKTOP_FILE"
    find "$ICONS_DIR" -name "$ICON_NAME.png" -o -name "$ICON_NAME.svg" 2>/dev/null \
        | while read -r icon; do rm -f "$icon"; done
    echo "Removed $DESKTOP_FILE and the $ICON_NAME icons from $DATA_HOME."
}

do_install() {
    if ! command -v video-manager >/dev/null 2>&1; then
        echo "Warning: 'video-manager' is not on the PATH — the launcher will not" >&2
        echo "work until you run 'uv tool install --editable .' in the project." >&2
    fi

    # os PNGs por tamanho: o tema do sistema escolhe o mais próximo sozinho
    for png in "$source_icons"/hicolor/*/apps/"$ICON_NAME".png; do
        size="$(basename "$(dirname "$(dirname "$png")")")"
        install -Dm644 "$png" "$ICONS_DIR/$size/apps/$ICON_NAME.png"
    done
    install -Dm644 "$source_icons/scalable/$ICON_NAME.svg" \
        "$ICONS_DIR/scalable/apps/$ICON_NAME.svg"
    install -Dm644 "$here/$DESKTOP_FILE" "$APPS_DIR/$DESKTOP_FILE"

    # os caches: sem eles o menu só percebe o novo item na próxima sessão
    command -v gtk-update-icon-cache >/dev/null 2>&1 &&
        gtk-update-icon-cache -qtf "$ICONS_DIR" 2>/dev/null || true
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database -q "$APPS_DIR" 2>/dev/null || true

    echo "Installed:"
    echo "  $APPS_DIR/$DESKTOP_FILE"
    echo "  $ICONS_DIR/*/apps/$ICON_NAME.png"
}

case "${1:-}" in
    --uninstall) do_uninstall ;;
    "") do_install ;;
    *) echo "usage: $(basename "$0") [--uninstall]" >&2; exit 2 ;;
esac
