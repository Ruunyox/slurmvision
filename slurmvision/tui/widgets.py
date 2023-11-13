from typing import List, Dict, Optional, Tuple, Union, Callable
import urwid
from urwid.command_map import ACTIVATE
import subprocess


class SelectableColumns(urwid.Columns):
    """Custom urwid.Columns child class that imbues a
    string column with a specific SLURM job ID and
    selectable/signal-emitting attributes/methods
    to emulate `urwid.Button` behavior

    Parameters
    ----------
    JOBID:
        string of numerical SLURM job ID
    """

    signals = ["click"]

    def __init__(self, *args, **kwargs):
        self.job_id = kwargs["JOBID"]
        del kwargs["JOBID"]
        super(SelectableColumns, self).__init__(*args, **kwargs)

    def selectable(self):
        return True

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        else:
            self._emit("click")


class TailText(urwid.Text):
    """Implementation of tail box, given a filepath to read.
    I prefer to not implement reverse file reading today,
    so as of now, the "tail" command is used to grab text
    via a subprocess call (yes I know its ugly). Sorry, bubz.
    This is essentially a Text widget infused with a "tail" call.
    """

    def __init__(self, file_path, num_lines: int = 10):
        self.file_path = file_path
        self.num_lines = num_lines
        stdout = TailText._read_lines(self.file_path, self.num_lines)
        super(TailText, self).__init__(stdout, wrap="ellipsis")

    @staticmethod
    def _read_lines(file_path, num_lines) -> str:
        out = subprocess.run(
            ["tail", "-n", str(num_lines), file_path], capture_output=True
        )
        return out.stdout

    def refresh(self, *args, **kwargs):
        """Run refresh tail call and updates Text widget text"""
        stdout = TailText._read_lines(self.file_path, self.num_lines)
        self.set_text(stdout)
