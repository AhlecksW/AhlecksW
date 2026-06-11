# AhlecksW Macro Automator

A Windows desktop tool that **records mouse + keyboard macros**, **replays them on
repeat** (a set number of times or until you stop), and can **trigger on an image
it recognizes on screen** using OpenCV template matching (your "80% or more"
similarity threshold).

## Features

- **Record macros** — mouse clicks, scrolls, optional mouse movement, and key
  presses, all with original timing. Press **F9** to stop recording.
- **Replay** — set a repeat count (`0` = loop forever) with a delay between runs.
  Press **F9** or the **Stop** button to halt at any time.
- **Image recognition** — attach a target image to a macro and pick a mode:
  - *No image* — just replay the actions.
  - *Run only if image is on screen* — each loop runs only when the image is found.
  - *Wait for image, then run* — block until the image appears, then run.
  - *Click on the image* — find the image and click its center (ignores recorded clicks).
- **Add an image two ways** — **Crop from screen** (drag a box over a frozen
  screenshot) or **Paste image** from the clipboard.
- **Match %** slider (default **80%**) and a **Test match** button that reports the
  current best similarity so you can tune the threshold.
- **Global hotkeys** — assign a system-wide start hotkey to a macro (click **Set**
  and press the combo, e.g. `Ctrl+Alt+1`). Pressing it starts the macro from
  anywhere — even when the window isn't focused — and pressing it again (or **F9**)
  stops it.
- **Step editor** — click **Edit steps…** to see every recorded action, the delay
  before it, and its details. Double-click a delay to retime that step (the rest
  shifts to follow), delete steps, or **Scale all delays ×** to speed up / slow
  down the whole macro. A **Speed ×** field also scales timing at playback.
- **Share codes** — **Export** turns a macro (image included) into one copy-paste
  code on your clipboard; **Import** recreates it from a pasted code, so you can
  send a macro to someone else to use.
- **Macro list** — scroll, select, rename, create, and delete saved macros. Macros
  persist in a `data/` folder next to the program.

## UI overview

```
+----------------------+--------------------------------------------------+
|  Macros              |  Name: [______________________]                  |
|  🖼 Login bot [C-A-1]|  Record: [● Record] 12 events [Edit steps…]      |
|    Farm loop         |  Image:  [thumb] [Crop][Paste][Clear][Test]      |
|    ...               |          Mode: Run only if image is on screen    |
|                      |          Match %: ====[80%]====                   |
|  [New]   [Delete]    |  Run opts: hotkey [Ctrl+Alt+1][Set] Speed ×[1.0] |
|  [Export][Import]    |  Playback: Repeat [0] Delay [0.5] [▶ Play][■]    |
+----------------------+--------------------------------------------------+
  status: Best similarity 87.3% at (640, 360) — MATCH (need 80%)
```

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

## Build the Windows .exe

On a Windows machine with Python 3.9+ installed, double-click **`build.bat`**
(or run it from a command prompt). When it finishes, your executable is at:

```
dist\AhlecksWMacro.exe
```

The `.exe` is self-contained — copy it anywhere. It creates a `data/` folder
beside itself to store your macros and images.

> **Note:** Building must be done on Windows to produce a Windows `.exe`.
> PyInstaller does not cross-compile.

## Project layout

```
main.py                  # entry point
requirements.txt
build.bat                # one-click Windows build
src/macroapp/
    app.py               # Tkinter UI
    recorder.py          # captures mouse/keyboard -> events
    player.py            # replays events, image-trigger gating, speed
    matcher.py           # OpenCV screen template matching
    cropper.py           # drag-a-box screen crop tool
    editor.py            # step/timing editor window
    hotkeys.py           # global hotkey manager + capture dialog
    share.py             # export/import macro share codes
    storage.py           # JSON + PNG persistence
```

## Sharing a macro

1. Select a macro and click **Export** — the share code is copied to your
   clipboard (and shown in a box). It includes the macro's actions, timing,
   settings, and its trigger image.
2. Send that code to someone (chat, email, a text file — it's just text).
3. They click **Import**, paste the code, and click **Import**. The macro shows
   up in their list ready to use. Hotkeys aren't shared, so each person sets
   their own.

## How image matching works

The matcher grabs the current screen and runs OpenCV
`matchTemplate` (`TM_CCOEFF_NORMED`) across a few scales, returning a similarity
score from 0–100%. If that score is at or above your **Match %** threshold, it
counts as a match. Use **Test match** to see the live score and dial it in.

## Tips & limitations

- Run as the foreground app you want to automate; global hotkey **F9** stops
  recording/playback from anywhere.
- Template matching is pixel-based, so it's best for icons, buttons, and stable
  UI elements. Big changes in scale, rotation, or theme can lower the score.
- If clicks land in the wrong place, check Windows **display scaling** (set it to
  100% on the target monitor for the most reliable coordinates).
