#!/usr/bin/env python3
"""
Regenerate the animated demo the README embeds.

    uv run --with pillow python site/scripts/demo.py

Same machinery as [screenshots.py](screenshots.py) -- the real app, driven
headlessly through Textual's pilot against a throwaway database -- except that
a frame is taken after *every* keypress rather than once at the end, and the
frames are written out as one GIF.

The frames are rasterized here rather than exported as SVG and converted.
Rich's SVG export is text positioned over colored rectangles with the font
pulled in by `@font-face`, and no SVG rasterizer available offline honours an
embedded web font -- every Nerd Font icon would come out as a blank box. So
this walks the same segments Rich would have written and draws each cell with
Pillow, straight out of the real JetBrainsMono Nerd Font Mono file. One
character per cell at a fixed pitch, which is what a terminal does anyway.

Needs **JetBrainsMono Nerd Font Mono** installed, like the screenshots do.
`--font-dir <path>` if it cannot be found. `--frames <dir>` also writes every
frame out as a PNG, to check the script against.
"""

import asyncio
import io
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
OUT_FILE = REPO_ROOT / "site" / "docs" / "public" / "demo.gif"

# The terminal the demo is recorded in. As wide as the screenshots' frame and
# a fraction of its height: the task pane gives its leftover width to the
# description, so a narrower terminal wraps every task over three lines.
COLUMNS = 140
ROWS = 32

# A cell. The font is sized so one glyph advance (0.6em in JetBrainsMono) is
# exactly CELL_W, which is what keeps the box-drawing characters joined up
# when each one is drawn into a cell of its own.
FONT_SIZE = 13.34
CELL_W = 8
CELL_H = 18

# A terminal has no margin; an image in a README reads better with one
PADDING = 12

# Importing screenshots.py points TODOOIT_HOME at a throwaway directory and
# imports todooit, so it has to happen before anything from the app is touched
sys.path.insert(0, str(SCRIPTS))

import screenshots as shots  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from rich.cells import cell_len  # noqa: E402
from rich.color import blend_rgb  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.segment import Segment  # noqa: E402
from rich.style import Style  # noqa: E402
from rich.terminal_theme import SVG_EXPORT_THEME as THEME  # noqa: E402
from textual.pilot import Pilot  # noqa: E402

from todooit.ui.tui import Todooit  # noqa: E402

# --------------------------------------------------------------------------
# The workflow being demonstrated
# --------------------------------------------------------------------------

# A step is (key, milliseconds the frame it produces is held). A key of None
# holds the frame that is already up, which is how a beat is given time to be
# read before the next one starts.
Step = Tuple[Optional[str], int]

TYPE_MS = 55  # one keystroke of someone typing
KEY_MS = 240  # one keystroke of someone navigating


def hold(ms: int) -> List[Step]:
    return [(None, ms)]


def press(*keys: str, ms: int = KEY_MS) -> List[Step]:
    """Keys pressed one at a time, a frame after each"""

    return [(key, ms) for key in keys]


def type_(text: str, ms: int = TYPE_MS) -> List[Step]:
    return [(character, ms) for character in text]


# The flash labels of the three tasks the script jumps to, in Work
FLASH_CHANGELOG = "d"
FLASH_EXPENSES = "k"
FLASH_RELEASE = "s"


# Markdown as it is written, since that is the only way a note is formatted,
# then a word fixed the vim way (`b` back onto it, `ciw` to retype it). A note
# opens in NORMAL, so `i` first; it ends back in NORMAL, off the last line,
# since the cursor's own line is drawn as the raw markdown.
NOTE = (
    press("i", ms=TYPE_MS)
    + type_("# Release")
    + press("enter", ms=TYPE_MS)
    + type_("- Changelog from the commit log")
    + press("enter", ms=TYPE_MS)
    + press("tab", ms=TYPE_MS)
    + type_("Check the migration notes")
    + press("enter", ms=TYPE_MS)
    + press("shift+tab", ms=TYPE_MS)
    + type_("Announce it")
    + press("enter", ms=TYPE_MS)
    + press("enter", ms=TYPE_MS)
    + type_("> Nothing ships on a monday")
    + press("escape") + hold(500)
    + press("c", "i", "w") + hold(300)
    + type_("friday") + hold(300)
    + press("escape")
    + press("k")
)

# One morning, start to finish. The cursor starts on Today, where the app
# opens.
#
# The flash labels go out top to bottom over the rows on screen, one key each
# while the alphabet is enough, so which letter lands on which task depends on
# the seed; `--frames <dir>` dumps every frame to check them against.
SCRIPT: Sequence[Step] = (
    hold(1800)
    # --- a whole task typed in one line: project, priority, day -----------
    + press("C") + hold(400)
    + type_("Pick up the parcel #Home p1 tomorrow 17:00") + hold(900)
    + press("enter") + hold(900)
    # --- ...and Upcoming already has it under tomorrow --------------------
    + press("g", "u") + hold(2000)
    # --- the finder reaches across the whole tree, into the project -------
    + press("/") + hold(350)
    + type_("release") + hold(800)
    + press("enter") + hold(1500)
    # --- a new step, planned in words -------------------------------------
    + press("N") + hold(300)
    + type_("Smoke-test the wheel") + hold(400)
    + press("enter") + hold(700)
    + press("s") + hold(300)
    + type_("tom") + hold(700)
    + press("enter") + hold(1300)
    # --- flash: a label on every row, typing one jumps there --------------
    + press("f") + hold(1300)
    + press(FLASH_CHANGELOG) + hold(600)
    + press("c") + hold(1300)
    # --- a recurrence on the last working day of the month ----------------
    + press("f") + hold(900)
    + press(FLASH_EXPENSES) + hold(600)
    + press("r") + hold(300)
    + type_("eom") + hold(700)
    + press("enter") + hold(1500)
    # --- every task carries a note: markdown, edited with vim keys --------
    + press("f") + hold(700)
    + press(FLASH_RELEASE) + hold(500)
    + press(" ") + hold(600)
    + NOTE + hold(2000)
    + press("escape") + hold(700)
    # --- `?` lists every key ----------------------------------------------
    + press("?") + hold(2400)
    + press("escape") + hold(400)
    + press("g", "t") + hold(2200)
)


# --------------------------------------------------------------------------
# One frame
# --------------------------------------------------------------------------


def screen_segments(app: Todooit) -> List[Segment]:
    """
    What `App.export_screenshot` hands to Rich's SVG writer, taken before it
    is turned into markup
    """

    console = Console(
        width=app.size.width,
        height=app.size.height,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        record=True,
        legacy_windows=False,
        safe_box=False,
    )
    console.print(
        app.screen._compositor.render_update(
            full=True,
            screen_stack=app._background_screens,
            simplify=False,
        )
    )

    with console._record_buffer_lock:
        return list(Segment.filter_control(console._record_buffer))


class Frames:
    """Draws the segments of a frame into an image, one cell at a time"""

    def __init__(self, font_dir: Optional[Path]):
        regular = shots.find_font(shots.FONT_FILES["regular"], font_dir)
        bold = shots.find_font(shots.FONT_FILES["bold"], font_dir)

        self.regular = ImageFont.truetype(str(regular), FONT_SIZE)
        self.bold = ImageFont.truetype(str(bold), FONT_SIZE)

        # Sit the font's own line box in the middle of the cell, so the row a
        # glyph is drawn on is the row Rich counted it into
        ascent, descent = self.regular.getmetrics()
        self.baseline = ascent + (CELL_H - ascent - descent) // 2

    @staticmethod
    def colors(style: Style) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        """Rich's own reading of a style, minus the parts SVG needs"""

        color = (
            THEME.foreground_color
            if style.color is None or style.color.is_default
            else style.color.get_truecolor(THEME)
        )
        bgcolor = (
            THEME.background_color
            if style.bgcolor is None or style.bgcolor.is_default
            else style.bgcolor.get_truecolor(THEME)
        )

        if style.reverse:
            color, bgcolor = bgcolor, color
        if style.dim:
            color = blend_rgb(color, bgcolor, 0.4)

        return (color.red, color.green, color.blue), (
            bgcolor.red,
            bgcolor.green,
            bgcolor.blue,
        )

    def render(
        self,
        segments: Sequence[Segment],
        width: int,
        height: int,
        margin: str,
    ) -> Image.Image:
        image = Image.new(
            "RGB",
            (width * CELL_W + 2 * PADDING, height * CELL_H + 2 * PADDING),
            margin,
        )
        draw = ImageDraw.Draw(image)

        lines = Segment.split_and_crop_lines(
            segments,
            length=width,
            pad=True,
            include_new_lines=False,
        )

        for row, line in enumerate(lines):
            column = 0
            top = PADDING + row * CELL_H
            baseline = top + self.baseline

            for text, style, _ in line:
                style = style or Style()
                foreground, background = self.colors(style)
                font = self.bold if style.bold else self.regular

                for character in text:
                    cells = max(cell_len(character), 1)
                    left = PADDING + column * CELL_W
                    right = left + cells * CELL_W

                    draw.rectangle(
                        (left, top, right - 1, top + CELL_H - 1),
                        fill=background,
                    )

                    if not character.isspace():
                        draw.text(
                            (left, baseline),
                            character,
                            font=font,
                            fill=foreground,
                            anchor="ls",
                        )

                    if style.underline:
                        y = baseline + 2
                        draw.line((left, y, right - 1, y), fill=foreground)
                    if style.strike:
                        y = baseline - FONT_SIZE // 3
                        draw.line((left, y, right - 1, y), fill=foreground)

                    column += cells

        return image


# --------------------------------------------------------------------------
# Driving the app
# --------------------------------------------------------------------------


async def settle(pilot: Pilot, frames: Frames) -> None:
    """
    Waits until two renders in a row come out the same.

    `boot()` returns as soon as Today has focus, which is a refresh before the
    screen is repainted to match: taken then, the first frame is the default
    Textual theme with the panes half laid out.
    """

    margin = pilot.app.api.vars.theme.background1
    previous = b""

    for _ in range(40):
        await pilot.pause()
        await asyncio.sleep(0.05)

        current = frames.render(
            screen_segments(pilot.app), COLUMNS, ROWS, margin
        ).tobytes()
        if current == previous:
            return
        previous = current

    raise AssertionError("The screen never stopped changing after boot")


async def run(frames: Frames) -> Tuple[List[Image.Image], List[int]]:
    images: List[Image.Image] = []
    durations: List[int] = []

    async def play(pilot: Pilot, steps: Sequence[Step]) -> None:
        margin = pilot.app.api.vars.theme.background1

        for key, ms in steps:
            if key is not None:
                await pilot.press(key)

            await pilot.pause()
            await asyncio.sleep(0.02)

            image = frames.render(screen_segments(pilot.app), COLUMNS, ROWS, margin)

            # A key that drew nothing new -- a chord waiting on its second
            # half, a note keystroke that only moved the caret into a cell it
            # was already in -- holds the frame that is up rather than costing
            # one of its own
            if images and image.tobytes() == images[-1].tobytes():
                durations[-1] += ms
                continue

            images.append(image)
            durations.append(ms)

    db_path = shots._INSTANCE / "demo.db"
    app = Todooit(db_path=str(db_path))
    shots.seed()

    async with app.run_test(size=(COLUMNS, ROWS)) as pilot:
        await shots.boot(pilot)
        app.title = "todooit"
        await settle(pilot, frames)

        await play(pilot, SCRIPT)

    return images, durations


# --------------------------------------------------------------------------
# The GIF
# --------------------------------------------------------------------------


def dump_frames(
    images: Sequence[Image.Image], durations: Sequence[int], directory: Path
) -> None:
    """Every frame as a PNG, named by index and hold, for checking the script"""

    directory.mkdir(parents=True, exist_ok=True)
    for index, (image, ms) in enumerate(zip(images, durations)):
        image.save(directory / f"{index:03d}-{ms}ms.png")


def write_gif(images: Sequence[Image.Image], durations: Sequence[int]) -> None:
    """
    One palette for the whole animation. Quantizing each frame on its own
    gives every frame a palette of its own -- a bigger file, and a visible
    shimmer wherever two frames round the same antialiased pixel differently.
    """

    sample = list(images[:: max(len(images) // 40, 1)])
    width, height = images[0].size

    stack = Image.new("RGB", (width, height * len(sample)))
    for index, image in enumerate(sample):
        stack.paste(image, (0, index * height))

    palette = stack.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    mapped = [
        image.quantize(palette=palette, dither=Image.Dither.NONE) for image in images
    ]

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    mapped[0].save(
        OUT_FILE,
        save_all=True,
        append_images=mapped[1:],
        duration=list(durations),
        loop=0,
        optimize=True,
        disposal=1,
    )


async def main(font_dir: Optional[Path], frames_dir: Optional[Path]) -> int:
    frames = Frames(font_dir)

    print(f"recording {COLUMNS}x{ROWS}")
    images, durations = await run(frames)
    print(f"  {len(images)} frames, {sum(durations) / 1000:.1f}s")

    if frames_dir is not None:
        dump_frames(images, durations, frames_dir)
        print(f"  frames in {frames_dir}")

    write_gif(images, durations)
    print(f"wrote {OUT_FILE} ({OUT_FILE.stat().st_size / 1_000_000:.1f} MB)")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    directory = None
    frames_dir = None

    if "--font-dir" in argv:
        directory = Path(argv[argv.index("--font-dir") + 1]).expanduser()
    if "--frames" in argv:
        frames_dir = Path(argv[argv.index("--frames") + 1]).expanduser()

    try:
        raise SystemExit(asyncio.run(main(directory, frames_dir)))
    finally:
        shutil.rmtree(shots._INSTANCE, ignore_errors=True)
