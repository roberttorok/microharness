"""A pinned status line at the bottom of the terminal, with no dependencies.

The last terminal row is taken out of the scroll region, so ordinary printing -
including token-by-token streaming - scrolls above it while the bar stays put.
"""
import shutil
import sys
import time

ESC = "\033"

# Repainting on every streamed token would be hundreds of writes a second and
# would flicker; ten times a second reads as smooth.
MIN_INTERVAL = 0.1
_last_paint = 0.0
_last_text = ""


def _size():
    """Terminal size, guarded.

    shutil only applies its fallback when the ioctl raises - a pty that
    reports 0x0 comes straight through, which produced escape codes like
    `ESC[1;-1r` and a zero-width bar.
    """
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    return (cols if cols > 0 else 80), (rows if rows > 0 else 24)


def _enable_windows_vt():
    """Windows consoles understand these sequences but ignore them until
    ENABLE_VIRTUAL_TERMINAL_PROCESSING is set on the output handle. Windows
    Terminal sets it already; the older conhost window does not, and without
    it the escape codes print as literal junk.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False                             # not a real console
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


_vt = None


def supported():
    global _vt
    if _vt is None:
        _vt = _enable_windows_vt()
    return _vt and sys.stdout.isatty()


def setup():
    """Reserve the last row: everything else scrolls above it."""
    if not supported():
        return
    _, rows = _size()
    sys.stdout.write(f"{ESC}[1;{rows - 1}r")   # scroll region = rows 1..rows-1
    sys.stdout.write(f"{ESC}[{rows - 1};1H")   # park the cursor inside it
    sys.stdout.flush()


def draw(text, force=True):
    """Paint the reserved row without disturbing the cursor.

    With force=False the call is dropped if the bar was painted very recently,
    which is what makes it safe to call from inside a streaming loop.
    """
    global _last_paint, _last_text
    _last_text = text
    if not supported():
        return
    now = time.monotonic()
    if not force and now - _last_paint < MIN_INTERVAL:
        return
    _last_paint = now
    cols, rows = _size()
    sys.stdout.write(
        f"{ESC}7"                      # save cursor position
        f"{ESC}[{rows};1H"             # jump to the last row
        f"{ESC}[2K"                    # clear it
        f"{ESC}[7m{text[:cols]:<{cols}}{ESC}[0m"   # reverse video, full width
        f"{ESC}8"                      # restore cursor
    )
    sys.stdout.flush()


def redraw():
    """Repaint the bar with whatever it last showed."""
    if _last_text:
        draw(_last_text)


def prompt(text="> "):
    """Read a line with the cursor pinned inside the scroll region.

    Plain input() echoes wherever the cursor happens to be - and after a
    streamed response that is mid-line, at an unpredictable row. Opening a
    fresh line at the bottom of the region first means typing can only ever
    land inside it, and the repaint afterwards restores the bar if echo or
    line-wrapping disturbed it.
    """
    if not supported():
        return input(text)
    _, rows = _size()
    sys.stdout.write(f"\n{ESC}[{rows - 1};1H{ESC}[2K")
    sys.stdout.flush()
    try:
        return input(text)
    finally:
        redraw()


def teardown():
    """Hand the full screen back. Must run even on a crash."""
    if not supported():
        return
    _, rows = _size()
    sys.stdout.write(f"{ESC}[1;{rows}r{ESC}[{rows};1H\n")
    sys.stdout.flush()
