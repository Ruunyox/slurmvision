from typing import List, Dict, Optional, Tuple, Union, Callable
import urwid
from urwid.command_map import ACTIVATE


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
