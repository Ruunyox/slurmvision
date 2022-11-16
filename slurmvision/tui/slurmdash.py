from typing import List, Dict, Optional, Tuple, Union, Callable
import urwid
from urwid.command_map import ACTIVATE
from copy import deepcopy
import os
from .widgets import SelectableColumns
from ..slurm import Inspector, SlurmThread


class Tui(object):
    """SlurmVision urwid-based Text-user interface for
    browsing, tracking, canceling, and querying job info
    from a local SLURM database

    Parameters
    ----------
    inspector:
        `Inspector` instance that handles SQUEUE/SINFO query
        and storage.
    """

    _palette = [
        ("standard", "", ""),
        ("header", "brown", ""),
        ("footer", "brown", ""),
        ("lines", "black", ""),
        ("selected", "dark red", ""),
        ("warning", "white", "dark red"),
        ("help", "black", "yellow"),
        ("error", "dark red", "white"),
        ("focus", "dark blue", ""),
    ]

    _help_strs = [
        "space ->   Select/deselect jobs",
        "m     ->   Toggle user jobs",
        "r     ->   Toggle running jobs",
        "i     ->   View SINFO output",
        "j     ->   View jobs",
        "c     ->   Deselect all currently selected jobs",
        "/     ->   Global search",
        "bksp  ->   Cancel selected jobs",
        "tab   ->   Refocus to job panel",
        "q     ->   Quit",
    ]

    _box_style_kwargs = {
        "tline": "\N{BOX DRAWINGS DOUBLE HORIZONTAL}",
        "trcorner": "\N{BOX DRAWINGS DOWN SINGLE AND LEFT DOUBLE}",
        "tlcorner": "\N{BOX DRAWINGS DOWN SINGLE AND RIGHT DOUBLE}",
    }

    def __init__(self, inspector):
        self.inspector = inspector
        self.inspector.get_jobs()
        self.selected_jobs = set()
        self.view = "squeue"
        self.filter_str = ""
        self.top = self._create_top()
        self.loop = urwid.MainLoop(
            self.top, palette=Tui._palette, unhandled_input=self._handle_input
        )
        self.loop.set_alarm_in(
            sec=self.inspector.polling_interval, callback=self.update_top
        )

    def start(self):
        """Creates and starts the polling thread as well as the TUI main loop"""
        self.poll_thread = SlurmThread(self.inspector)
        self.poll_thread.start()
        self.loop.run()

    def _urwid_quit(self, *args):
        """Deconstructs the TUI and quits the program"""
        self.poll_thread.join()
        raise urwid.ExitMainLoop()

    def _handle_input(self, key: str):
        """Handles general keyboard input during the TUI loop"""
        if key in ("Q", "q"):
            self._urwid_quit()
        if key in ("J", "j"):
            self._set_view("squeue")
        if key in ("I", "i"):
            self._set_view("sinfo")
        if key in ("M", "m"):
            self._toggle_my_jobs()
        if key in ("R", "r"):
            self._toggle_running_jobs()
        if key in ("C", "c"):
            if self.view == "squeue":
                self._deselect_check()
        if key == "/":
            if self.view == "squeue":
                self._enter_search()
        if key == "backspace":
            if self.view == "squeue":
                if len(self.selected_jobs) > 0:
                    self._scancel_check()
        if key == "tab":
            self.top.focus_position = "body"
        if key in ("H", "h"):
            self._help_box()

    def _scancel_check(self):
        self._yes_no_prompt(
            f"Are you sure you want to cancel {len(self.selected_jobs)} selected job(s)?",
            self.cancel_selected_jobs,
            self._return_to_top,
        )

    def _deselect_check(self):
        self._yes_no_prompt(
            f"Are you sure you want to clear selection?",
            self.clear_selection,
            self._return_to_top,
        )

    def _enter_search(self):
        self.top.focus_position = "footer"
        self.top.footer.original_widget.original_widget.focus_col = 3

    def _set_view(self, view: str):
        self.view = view
        self.draw_body()
        self.draw_header()

    def _return_to_top(self, *args):
        self.loop.widget = self.top

    def _force_refresh(self):
        if self.view == "squeue":
            self.inspector.get_jobs()
        if self.view == "sinfo":
            self.inspector.get_info()

    def _toggle_my_jobs(self):
        self.top.footer.original_widget.original_widget[0].toggle_state()

    def _toggle_running_jobs(self):
        self.top.footer.original_widget.original_widget[1].toggle_state()

    def _create_top(self) -> urwid.Frame:
        """Creates main urwid.Frame widget"""
        headstr = urwid.AttrMap(
            self.build_headstr(self.inspector.squeue_header), "header", None
        )
        footstr = urwid.AttrMap(self.build_footstr(), "footer", None)
        jstrs = self.build_squeue_list()

        job_list = urwid.SimpleFocusListWalker(jstrs)
        self.list_focus_pos = 0
        job_win = urwid.ListBox(job_list)
        job_linebox = urwid.LineBox(job_win, **Tui._box_style_kwargs)
        body = job_linebox

        top = urwid.Frame(
            body,
            header=urwid.LineBox(headstr, title="SlurmVision", **Tui._box_style_kwargs),
            footer=urwid.LineBox(footstr, **Tui._box_style_kwargs),
        )
        return top

    def _help_box(self):
        """Creates temporary Help overlay displaying
        command keystrokes for using the TUI.
        """
        ok = urwid.Button("OK")
        urwid.connect_signal(ok, "click", self._return_to_top)

        help_text = [urwid.Divider()]
        for s in Tui._help_strs:
            help_text.append(urwid.Padding(urwid.Text(s), left=3, right=3))
        help_text.append(urwid.Divider())
        help_text.append(ok)

        help_pile = urwid.Pile(help_text)
        help_box = urwid.AttrMap(
            urwid.LineBox(help_pile, title="Help", **Tui._box_style_kwargs),
            "help",
            None,
        )

        w = urwid.Overlay(
            urwid.Filler(help_box),
            self.top,
            align="center",
            width=("relative", 60),
            valign="middle",
            height=("relative", 60),
        )
        self.loop.widget = w

    def _error_box(self, error_msg: str):
        """Displays a temporary error message"""
        ok = urwid.Button("OK")
        urwid.connect_signal(ok, "click", self._return_to_top)

        error_text = [urwid.Divider()]
        error_text.append(urwid.Padding(urwid.Text(error_msg), left=3, right=3))
        error_text.append(urwid.Divider())
        error_text.append(ok)

        error_pile = urwid.Pile(error_text)
        error_box = urwid.AttrMap(
            urwid.LineBox(error_pile, title="Error", **Tui._box_style_kwargs),
            "error",
            None,
        )

        w = urwid.Overlay(
            urwid.Filler(error_box),
            self.top,
            align="center",
            width=("relative", 60),
            valign="middle",
            height=("relative", 60),
        )
        self.loop.widget = w

    def _yes_no_prompt(self, prompt: str, yes_call: Callable, no_call: Callable):
        """Displays a prompt to the user and expects a yes/no
        answer. The two answers are signal-linked to "yes" and "no"
        callables.

        Parameters
        ----------
        prompt:
            String asking the user a question.
        yes_call:
            Function that is called if "Yes" is chosen
        no_call:
            Function that is called if "No" is chosen
        """
        yes = urwid.Button("Yes")
        no = urwid.Button("No")

        urwid.connect_signal(yes, "click", yes_call)
        urwid.connect_signal(no, "click", no_call)

        buttons = urwid.Columns([yes, no])
        pile = urwid.Pile(
            [urwid.Text(prompt, align="center"), urwid.Divider(), buttons]
        )
        message_box = urwid.AttrMap(
            urwid.LineBox(pile, title="Warning", **Tui._box_style_kwargs),
            "warning",
            None,
        )

        w = urwid.Overlay(
            urwid.Filler(message_box),
            self.top,
            align="center",
            width=("relative", 30),
            valign="middle",
            height=("relative", 30),
        )
        self.loop.widget = w

    def cancel_selected_jobs(self, *args):
        """Instructs the inspector to cancel all currently
        selected jobs. If a job cannot be cancelled (e.g., if
        the user does not possess appropriate permissions),
        an error message is displayed relaying the stderr
        of the SCANCEL subprocess call.
        """

        self._return_to_top()
        for job in deepcopy(self.selected_jobs):
            output = self.inspector.cancel_job(job)
            if output.stderr:
                self._error_box(output.stderr.decode("utf-8"))
            else:
                self.selected_jobs.remove(job)
                self.top.footer.original_widget.original_widget[2].set_text(
                    f"[{len(self.selected_jobs)}] Selected"
                )

    def clear_selection(self, *args):
        """Clears the users currently selected jobs"""
        self.selected_jobs = set()
        self.top.footer.original_widget.original_widget[2].set_text(
            f"[{len(self.selected_jobs)}] Selected"
        )
        self._return_to_top()
        self.draw_body()

    def update_filter_str(self, edit: urwid.Edit, *args):
        """Updates job filtering string based on 'change'
        signals emitted from the footer 'Search' edit box.

        Parameters
        ----------
        edit:
            urwid Edit box associated with the TUI footer
            'Search' column
        """

        self.filter_str = edit.get_edit_text()
        self.draw_body()

    def build_headstr(self, header: List[str]) -> urwid.Columns:
        """Builds TUI header according to parsed SQUEUE/SINFO header strings

        Parameters
        ----------
        header:
            List of tokenized SQUEUE/SINFO strings

        Returns
        -------
        headstr:
            Padded header strings organized in an `urwid.Columns` instance
        """

        headstr = urwid.Columns(
            [
                urwid.Padding(urwid.Text(h, align="left", wrap="clip"), right=2, left=2)
                for h in header
            ]
        )
        return headstr

    def build_footstr(self) -> urwid.Columns:
        """Builds TUI footer, containg user/running job filter checkboxes, selected job counter,
        and search string entry.

        Returns
        -------
        footstr:
            Footer widgets organized in an `urwid.Columns` instance.
        """

        my_jobs = urwid.Padding(
            urwid.CheckBox("My Jobs", state=False, has_mixed=False), right=2, left=2
        )
        urwid.connect_signal(
            my_jobs.original_widget, "change", self.inspector.toggle_user_filter
        )

        running_jobs = urwid.Padding(
            urwid.CheckBox("Running", state=False, has_mixed=False), right=2, left=2
        )
        urwid.connect_signal(
            running_jobs.original_widget, "change", self.inspector.toggle_running_filter
        )

        job_counter = urwid.Padding(
            urwid.Text(f"[{len(self.selected_jobs)}] Selected"), right=2, left=2
        )

        name_search = urwid.Padding(
            urwid.Edit(caption="Search: ", edit_text="", wrap="any"), right=2, left=2
        )

        urwid.connect_signal(
            name_search.original_widget,
            "postchange",
            self.update_filter_str,
            user_args=[name_search.original_widget],
        )

        footstr = urwid.Columns([my_jobs, running_jobs, job_counter, name_search])
        return footstr

    def build_squeue_list(self) -> List[SelectableColumns]:
        """Builds SQUEUE job list according to current filters

        Returns
        -------
        jstrs:
            List of `SelectableColumns` instances, each one imbued with
            a specific SLURM job ID and colored according to its selection
            status.
        """

        jstrs = []
        for j in self.inspector.jobs:
            if any(
                [self.filter_str in j.attrs[h] for h in self.inspector.squeue_header]
            ):
                col = urwid.AttrMap(
                    SelectableColumns(
                        [
                            urwid.Padding(
                                urwid.Text(j.attrs[h], align="left", wrap="clip"),
                                right=2,
                                left=2,
                            )
                            for h in self.inspector.squeue_header
                        ],
                        JOBID=j.attrs["JOBID"],
                    ),
                    attr_map=(
                        "selected"
                        if j.attrs["JOBID"] in self.selected_jobs
                        else "standard"
                    ),
                    focus_map="focus",
                )
                urwid.connect_signal(
                    col.original_widget, "click", self._toggle_selected, user_args=[col]
                )
                jstrs.append(col)
        return jstrs

    def build_sinfo_list(self) -> List[urwid.Columns]:
        """Builds SINFO output list.

        Returns
        -------
        strs:
            List of `urwid.Columns`, each one containing
            an output row from SINFO.
        """

        istrs = []
        for i in self.inspector.sinfo:
            col = urwid.AttrMap(
                urwid.Columns(
                    [
                        urwid.Padding(
                            urwid.Text(i[h], align="left", wrap="clip"), right=2, left=2
                        )
                        for h in self.inspector.sinfo_header
                    ],
                ),
                attr_map="standard",
                focus_map="standard",
            )
            istrs.append(col)
        return istrs

    def draw_header(self):
        """Draws current TUI header"""
        if self.view == "squeue":
            headstr = self.build_headstr(self.inspector.squeue_header)
        if self.view == "sinfo":
            headstr = self.build_headstr(self.inspector.sinfo_header)
        self.top.header.original_widget.original_widget = headstr

    def draw_body(self):
        """Draws current TUI body"""
        if self.view == "squeue":
            strs = self.build_squeue_list()
        if self.view == "sinfo":
            strs = self.build_sinfo_list()
        if len(strs) == 0:
            self.top.body.original_widget.body.clear()
        else:
            original_focus = self.top.body.original_widget.body.focus
            if original_focus == None:
                original_focus = 0
            self.top.body.original_widget.body.clear()
            self.top.body.original_widget.body.extend(strs)
            self.top.body.original_widget.body.set_focus(original_focus % len(strs))

    def update_top(self, *args):
        """Updates the TUI and sets an urwid loop alarm to re-draw the TUI
        according to the inspector's polling interval
        """
        self.draw_body()
        self.loop.set_alarm_in(self.inspector.polling_interval, self.update_top)

    def _toggle_selected(self, col: SelectableColumns, *args):
        """Toggles the job under the cursor to be added/removed
        from the set of selected jobs. Selected jobs are colored. The cursor
        is automatically advanced to the next item to allow for fast selection
        of contiguous jobs.

        Parameters
        ----------
        col:
            `SelectableColumn` instance identifying the job to be
             selected/deselected
        """

        if col.original_widget.job_id not in self.selected_jobs:
            self.selected_jobs.add(col.original_widget.job_id)
            self.top.footer.original_widget.original_widget[2].set_text(
                f"[{len(self.selected_jobs)}] Selected"
            )
            col.set_attr_map({None: "selected"})
            original_focus = self.top.body.original_widget.body.focus
            self.top.body.original_widget.set_focus(
                (original_focus + 1) % len(self.top.body.original_widget.body)
            )
        else:
            self.selected_jobs.remove(col.original_widget.job_id)
            self.top.footer.original_widget.original_widget[2].set_text(
                f"[{len(self.selected_jobs)}] Selected"
            )
            col.set_attr_map({None: None})
            original_focus = self.top.body.original_widget.body.focus
            self.top.body.original_widget.set_focus(
                (original_focus + 1) % len(self.top.body.original_widget.body)
            )
