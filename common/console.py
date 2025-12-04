import sys
import shutil

from common.system import clear_screen

CSI = "\x1b["  # Control Sequence Introducer

def clear_line():
    sys.stdout.write(f"{CSI}2K\r")  # clear entire line + carriage return

def cursor_up(n=1):
    if n > 0:
        sys.stdout.write(f"{CSI}{n}A")

def cursor_down(n=1):
    if n > 0:
        sys.stdout.write(f"{CSI}{n}B")

def insert_lines(n=1):
    # IL (Insert Line): insert n blank lines at cursor, pushing content down
    sys.stdout.write(f"{CSI}{n}L")

def hide_cursor():
    sys.stdout.write(f"{CSI}?25l")

def show_cursor():
    sys.stdout.write(f"{CSI}?25h")

class SplitConsole:
    def __init__(self, barrier_char="=", barrier_len=None):
        # Enable ANSI on Windows 10+ terminals (PowerShell/VSCode support it)
        # No special setup needed; colorama is optional for older setups.

        clear_screen()

        self.status = ""
        width = shutil.get_terminal_size(fallback=(80, 20)).columns
        line_len = barrier_len or max(3, min(120, width))
        self.barrier = barrier_char * line_len

        hide_cursor()
        # Start with barrier + empty status
        print(self.barrier)
        print("")  # status line (empty to start)
        # Put cursor back on the status line (beginning)
        cursor_up(1)
        sys.stdout.flush()

    def set_status(self, text):
        """Rewrite the bottom status line in place (no newline)."""
        clear_line()
        self.status = text
        sys.stdout.write(text)
        sys.stdout.flush()

    def add_update(self, text):
        """
        Insert a new permanent line above the barrier.
        This pushes the barrier and status down automatically.
        """
        # We are currently on the status line.
        # Move up to the barrier line:
        cursor_up(1)
        # Insert one line ABOVE the barrier:
        insert_lines(1)
        # Write the permanent text into that newly inserted line:
        clear_line()
        sys.stdout.write(text + "\n")
        # After writing, we're now on the line after the permanent text
        # which is the barrier line. Move down to the status line again:
        cursor_down(1)
        # Repaint status (since cursor position may have shifted)
        self.set_status(self.status)

    def close(self):
        # Move to next line so the prompt doesn't land mid-status
        sys.stdout.write("\n")
        show_cursor()
        sys.stdout.flush()
