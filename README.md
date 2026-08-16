<img src="video_manager/icons/hicolor/128x128/apps/video-manager.png" width="96" align="right" alt="">

# Video Manager

*[Leia em português](README.pt-BR.md)*

A desktop app (PySide6) that builds *contact sheets* for a folder of videos and
lets you triage them from the keyboard: what stays, and what goes to quarantine.

Built for the folder that grew past the point of watching everything again — a
grid of frames is usually enough to decide, and the ones it isn't enough for get
their own pile.

The frame-extraction engine comes from the `Thumbnail Maker` notebook, naming
convention included (`my_video.mp4.jpg`), so thumbnails you generated earlier are
reused instead of being made again.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A desktop session (Linux, macOS or Windows)

## Install

```bash
git clone https://github.com/FRubik/video-manager.git
cd video-manager
uv tool install --editable .
```

This puts a `video-manager` command in `~/.local/bin`, so it runs from any
folder, with no `uv` in front:

```bash
video-manager
```

Because the install is `--editable`, the command points at the code in this
folder: editing a file already counts on the next run, with no reinstall. You
only need `uv tool upgrade video-manager` when the project's **dependencies**
change.

To uninstall: `uv tool uninstall video-manager`.

### Menu entry and icon (Linux)

The app carries its own icon, but the desktop only knows about it once the
launcher is installed:

```bash
./packaging/install-desktop-entry.sh
```

That copies the icons into `~/.local/share/icons/hicolor` and the launcher into
`~/.local/share/applications` — no root needed. `--uninstall` removes the same
files.

It matters on Wayland: there the taskbar icon comes from the `.desktop` file,
matched to the window by app id, so without this step the window keeps the
compositor's generic icon no matter what the app sets.

Skipping it is fine — the app runs the same, and it stays quiet about it: the
desktop file name is only declared when the file is actually there, because
claiming one that does not exist makes the freedesktop portal print a
`Could not register app ID` error on every start.

## Running without installing

From inside the project folder:

```bash
uv run video-manager        # command declared in [project.scripts]
uv run python -m video_manager
```

Careful: this folder has **no `.venv`** on purpose — the installed tool's
environment already has everything, and keeping both duplicated ~900 MB (PySide6
is heavy, and uv does not share those files between the two environments). Any
`uv run` here recreates the `.venv` and brings the duplication back.

To run a one-off script against the project's dependencies without recreating
anything, use the tool's own Python:

```bash
~/.local/share/uv/tools/video-manager/bin/python my_test.py
```

## Language

The interface speaks **English** and **Brazilian Portuguese**. The selector sits
at the top right of the start screen and switches on the spot — no restart, and
a review session in progress survives the switch. The choice is saved in
`config.json`; with nothing saved, the app follows the system locale and falls
back to English.

The language also drives what isn't text: the decimal separator (`1,234.5 GB`
against `1.234,5 GB`), the date format, and the default name of the discards and
*maybe* folders (`_to_delete` / `_maybe` in English, `_para_apagar` / `_talvez`
in Portuguese). Those are directories on disk, so both names are always
recognised as "still the default" — switching languages never orphans a folder
you already have.

## How it works

### 1. Start screen

- **Folders**: videos, thumbnails, discards (`<videos folder>/_to_delete`) and
  *maybe* (`<videos folder>/_maybe`). The last two fill themselves in and follow
  the videos folder around for as long as they hold the default value; the
  **Default** button next to each one rebuilds the path at any time, and nothing
  stops you from pointing them somewhere else.
- **Generate thumbnails**: unchecked, the app goes straight to the review screen
  using existing thumbnails. Checked, it generates first — with the *only videos
  that have no thumbnail yet* option, which is the common case when you add new
  videos.
- **Review session**:
  - *Review every video* — goes through everything that has a thumbnail;
  - *Random check* — draws N videos and the session ends with them, to slice a
    large folder across several days;
  - *Skip videos I already reviewed* — uses the history so you don't redo what
    you decided in earlier sessions;
  - *Show in random order* — shuffles the display instead of following the
    alphabet. In a folder where names group the content, alphabetical order makes
    you watch everything of one kind in a row;
  - *Videos in "maybe"* — **leave out**, **include in the session** (alongside
    the rest) or **only those**, for a round dedicated to the doubts you have
    piled up (see below).

Drawing *which* videos and choosing what *order* to show them in are separate
things: the random check draws the sample and shows it alphabetically, unless you
also check random order.

When an **interrupted session** is stored for those folders, an orange panel
appears above the summary, with **Resume** and **Discard** — see "Stopping
halfway and picking it up later".

The summary panel shows how many videos exist, how many have a thumbnail, how
many were already reviewed and how many are in this session. Right below it comes
the **volume** panel — see "How much will be left".

### 2. Review screen

One thumbnail at a time, filling the window, with the session list on the right.

The default keys sit on the left of the keyboard, so you can review one-handed:

| Key | Action |
|---|---|
| `A` or `←` | previous video (you can go back and change the decision) |
| `D`, `→` or `Space` | next video, without deciding |
| `E` | marks it to keep and moves on |
| `W` | marks it as *maybe* — review later — and moves on |
| `Q` or `Del` | marks it to delete and moves on |
| `G` | opens the video in the system's default player |
| `Z` or click | toggles between fit-to-window and 1:1 zoom |
| `Enter` | applies the decisions and ends the session |

The **Shortcuts…** button, on the start screen, changes the key for each action —
the choice is saved in `config.json`. The alternatives in the table (`←`, `→`,
`Space`, `Del`) keep working, and `Enter` cannot be remapped.

Nothing is moved while you decide — the marks are only applied on **Apply and
finish** (or at the end of the session, which asks), always with a confirmation.
Next to it, **Save and leave** stores the session for another day without moving
anything.

### 3. The "maybe"

For the video a thumbnail can't settle — you need to watch a stretch, compare it
with another one, decide with a cooler head. `W` sends it to the *maybe* folder
instead of forcing a decision right now.

What separates *maybe* from a decision: it **does not go into the history as
reviewed**. With *include in the session*, those videos come back in later
sessions alongside the new ones, without you touching a single field. When you
finally decide:

- **keep** returns the video to the videos folder and only then records it as
  reviewed;
- **delete** sends it to quarantine, like any other;
- **maybe** again leaves it where it is, for the next round.

The *only those* option exists for the other end of that cycle: a whole session
made of the accumulated doubts, with no new video in between. That's the moment
to sit down and clear the pile — compare the similar ones, open in the player
what the thumbnail can't settle — instead of deferring each one again. Worth
combining with the random check when the pile got too big for one sitting.

### 4. What happens when you apply

- Videos marked *delete* are **moved** to the discards folder (never deleted);
  repeated names get a `(2)`, `(3)`… suffix instead of overwriting.
- The **thumbnail stays** in the thumbs folder, so you can reassess a discard by
  the image before deleting it for good.
- Every move is recorded in `_movimentos.jsonl` (origin, destination, date and
  reason), inside the destination folder — or inside the *maybe* folder, in the
  case of a return, so no log file is dumped into your videos folder.
- A move that fails (permissions, full disk) is **not** recorded in the history:
  the video shows up again in the next session, with the decision still to make.

### 5. How much will be left

The question the volume panel answers: *what size will this folder settle at once
I'm done triaging everything?*

On the start screen it shows what the folder takes up today, what is in *maybe*,
what is sitting in quarantine (still using disk until you actually delete it)
and, based on the history:

```
1.8 TB across 2,431 video(s) · 12.4 GB in “maybe” · 210.5 GB sitting in quarantine
You discard 43% of the volume you decide on (612 videos decided, 890.0 GB).
1.1 TB still to decide — at this pace, 1.3 TB should be left when it is over.
```

The math is direct: the fraction of **bytes** you sent to quarantine, out of
everything you already decided, applied to the volume still to be decided. It is
not the fraction of *files* — discarding ten 20 MB clips does not say the same
thing as discarding one 8 GB file, and what matters here is the disk.

On the review screen the same line follows the session: how much you already
marked to delete, to *maybe* and to keep, with the projection reacting to each
decision — including this session's, before applying anything.

The rate only appears after **5 videos decided with their size recorded**; before
that it would be 0% or 100%. Since the size only started being written to the
history in this version, decisions you made earlier don't count — the projection
starts to mean something after the next few sessions.

### 6. Stopping halfway and picking it up later

A folder with thousands of videos doesn't fit one sitting, and interruptions
don't announce themselves. There are two ways to drop a session halfway, for two
different problems.

**Apply and continue another day.** Hit `Enter`, apply, and that's it: the
decided videos go into the history and *Skip videos I already reviewed* leaves
them out of the next sessions. Re-randomise as much as you like — what you have
already seen doesn't come back. Closing the window with pending decisions offers
**Apply and leave**, which does exactly that without asking you to remember
`Enter`.

**Store the whole session.** That's what the *random check* calls for: applying
halfway ends that draw, and the videos you haven't seen go back into the pot —
maybe never landing together again. **Save and leave** freezes the session as it
stands: the drawn list, the marks you already made and the position you stopped
at. Next time you open the app, **Resume** gives it all back, colours in the side
list included, and you carry on from the video after the last one decided.

You don't have to remember to save: **each decision writes the session to disk**.
If the program dies, the machine shuts down or you close the window in a panic,
the session is there when you come back. The file is small and disappears on its
own when you apply.

The world may have changed between saving and resuming, and resuming deals with
that:

- video deleted or moved out of the folders → drops out of the session, with a
  notice of how many were left out, and the saved position follows the shrinking;
- video that changed folders (from *maybe* to the videos folder, say) → found
  again by name, with its origin corrected;
- **starting a new session** with one pending → the app asks first, because that
  throws the stored marks away.

There is only one saved session per thumbnails folder, and it is only offered when
the videos folder is the same as when it was saved. Leaving without having decided
anything saves nothing — there is nothing to preserve in a session you only
browsed.

## State files

| File | Where | What for |
|---|---|---|
| `.video_manager_state.json` | thumbnails folder | decision history, with each video's size (feeds "skip already reviewed" and the volume projection; *maybe* is recorded but does not count as reviewed) |
| `.video_manager_session.json` | thumbnails folder | interrupted session: list, unapplied marks and position (disappears once applied) |
| `_movimentos.jsonl` | discards and *maybe* folders | log of the videos that were moved |
| `config.json` | `~/.config/video_manager/` | language, last folders, options used and shortcuts |

The history lives next to the thumbnails on purpose: if the folder moves to
another place or another machine, it goes along.

## A note on opening the video in the player (`G` key)

Two traps cost a VLC crash and are solved — worth knowing, because any new code
that launches an external program runs into them again:

1. **Don't pass a `file://` URL.** VLC's `.desktop` receives the URL through
   `%U`, and names with `#`, `%`, `&` or spaces can be reinterpreted inside the
   path. The path goes as a single argument to `xdg-open`.

2. **Don't let the child process inherit the dirty environment.** `import cv2`
   overwrites `QT_QPA_PLATFORM_PLUGIN_PATH`, `QT_QPA_FONTDIR` and
   `LD_LIBRARY_PATH` pointing inside OpenCV's site-packages, which ships a single
   `libqxcb.so` linked against its own Qt libs. A Qt app launched as a child
   tries to load that plugin and aborts with `Could not load the Qt platform
   plugin "xcb"` — VLC died with SIGABRT before even looking at the file.
   That's why `video_manager/__init__.py` keeps `PRISTINE_ENV` (a copy of the
   environment taken before any heavy import) and `library.launch_env()` hands it
   to external processes.

## Layout

```
video_manager/
├── config.py      persisted preferences
├── i18n.py        interface strings in English and Portuguese
├── icons.py       loads the app icon
├── icons/         the icon itself (hicolor sizes + SVG)
├── library.py     scanning, video↔thumb pairing, saved session, quarantine
├── shortcuts.py   review actions and the keys that trigger them
├── thumbs.py      frame extraction and grid assembly (the notebook's engine)
├── worker.py      generation on a separate thread
├── ui_setup.py    start screen
├── ui_review.py   review screen
├── ui_shortcuts.py  key customisation dialog
└── app.py         main window
```

## Contributing

Issues and pull requests are welcome. Two things worth knowing before touching
the code:

- **No user-visible text goes straight into a UI module.** Add a key to
  `i18n.py`, with both languages, and call `tr("your.key")`. A missing key shows
  up raw on screen, on purpose — a silent fallback would hide the omission.
- Screens that can be re-rendered implement `retranslate()`, which rewrites every
  fixed label. A new widget with text needs a line there, otherwise it stays
  frozen in the language it was created in.

## License

MIT — see [LICENSE](LICENSE).
