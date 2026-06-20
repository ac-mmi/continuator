"""Single-key input and clipboard helpers (no Textual)."""
from __future__ import annotations

import subprocess
import sys


def read_key() -> str | None:
    """Read one key from the controlling terminal. Returns None if unavailable."""
    if sys.platform == "win32":
        try:
            import msvcrt

            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                msvcrt.getch()
                return None
            return ch.decode("utf-8", errors="ignore").lower()
        except Exception:
            return None

    try:
        import termios
        import tty

        with open("/dev/tty", "r", encoding="utf-8") as tty_in:
            fd = tty_in.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                ch = tty_in.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if not ch:
            return None
        return ch.lower()
    except OSError:
        if not sys.stdin.isatty():
            return None
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            return (ch or "").lower()
        except Exception:
            return None


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard."""
    payload = (text or "").encode("utf-8")
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=payload, check=True, timeout=5)
            return True
        if sys.platform == "win32":
            subprocess.run(
                ["clip"],
                input=payload,
                check=True,
                timeout=5,
                shell=True,
            )
            return True
        for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            try:
                subprocess.run(cmd, input=payload, check=True, timeout=5)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return False
