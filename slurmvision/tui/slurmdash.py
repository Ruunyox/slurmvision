from typing import List, Dict, Optional, Tuple, Union, Callable
import urwid
from urwid.command_map import ACTIVATE
from copy import deepcopy
import os
from .widgets import SelectableColumns, TailText
from ..slurm import Inspector, SlurmThread

default_palette = {
    "standard": ("standard", "", ""),
    "header": ("header", "brown", ""),
    "footer": ("footer", "brown", ""),
    "selected": ("selected", "dark red", ""),
    "warning": ("warning", "white", "dark red"),
    "help": ("help", "black", "yellow"),
    "detail": ("detail", "black", "white"),
    "tail": ("tail", "white", "dark green"),
    "error": ("error", "dark red", "white"),
    "focus": ("focus", "dark blue", ""),
}


class Tui(object):
    """SlurmVision urwid-based Text-user interface for
    browsing, tracking, canceling, and querying job info
    from a local SLURM database

    Parameters
    ----------
    inspector:
        `Inspector` instance that handles SQUEUE/SINFO query
        and storage.
    select_advance:
        If True, the cursor for the job list is advanced forward
        automatically when a (de)selection is performed.
    my_jobs_first:
        If True, slurmvision will start with "My Jobs" toggled ON.
        Useful if you are working with a big/busy cluster.
    palette:
        Nested list of lists/tuples specifying color options for
        the TUI. See https://urwid.org/manual/displayattributes.html
        for more information on color/palette options. If None,
        the default palette is used. If palette options are missing,
        they will be filled with default color options.
    """

    _help_strs = [
        "space/enter ->   Select/deselect jobs",
        "m           ->   Toggle user jobs",
        "r           ->   Toggle running jobs",
        "p           ->   Manual SQUEUE/SINFO poll",
        "i           ->   View SINFO output",
        "j           ->   View jobs",
        "c           ->   Deselect all currently selected jobs",
        "d           ->   Detailed view of currently highlighted job",
        "t           ->   Tail ouput for the currently highlighed job",
        "/           ->   Global search",
        "bksp        ->   Cancel selected jobs",
        "tab         ->   Refocus to job panel/leave search box",
        "q           ->   Quit",
    ]

    _box_style_kwargs = {
        "tline": "\N{BOX DRAWINGS DOUBLE HORIZONTAL}",
        "trcorner": "\N{BOX DRAWINGS DOWN SINGLE AND LEFT DOUBLE}",
        "tlcorner": "\N{BOX DRAWINGS DOWN SINGLE AND RIGHT DOUBLE}",
    }

    def __init__(
        self,
        inspector: Inspector,
        select_advance: bool = True,
        my_jobs_first: bool = False,
        palette: Optional[List[List[str]]] = None,
    ):
        if palette:
            defined_items = set([color_opt[0] for color_opt in palette])
            full_items = set(default_palette.keys())
            undefined_items = full_items - defined_items
            for ui in undefined_items:
                palette.append(default_palette[ui])
            self.palette = palette
        else:
            self.palette = [val for val in default_palette.values()]

        self.num_tail_lines = 8
        self.tail_sleep = 1
        self.inspector = inspector
        self.selected_jobs = set()
        self.my_jobs_first = my_jobs_first

        if self.my_jobs_first:
            self.inspector.toggle_user_filter()

        self.inspector.get_jobs()
        self.view = "squeue"
        self.filter_str = ""
        self.top = self._create_top()
        self.select_advance = select_advance
        self.loop = urwid.MainLoop(
            self.top, palette=self.palette, unhandled_input=self._handle_input
        )
        self.handle = self.loop.set_alarm_in(
            sec=self.inspector.polling_interval, callback=self.update_top
        )
        self.tail_handle = None

    def start(self):
        """Creates and starts the polling thread as well as the TUI main loop"""
        self.poll_thread = SlurmThread(self.inspector)
        self.poll_thread.start()
        self.loop.run()

    def _urwid_quit(self, *args):
        """Deconstructs the TUI and quits the program"""
        self.poll_thread.join()
        self.loop.remove_alarm(self.handle)
        raise urwid.ExitMainLoop()
        print("Polling thread closing... either wait or CTRL-C.")

    def _handle_input(self, key: str):
        """Handles general keyboard input during the TUI loop

        Parameters
        ----------
        key:
            String representing the user input
        """
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
        if key in ("P", "p"):
            if self.view == "squeue":
                self.inspector.get_jobs()
            if self.view == "sinfo":
                self.inspector.get_info()
            self.loop.remove_alarm(self.handle)
            self.update_top()
        if key in ("D", "d"):
            if self.view == "squeue":
                self._inspect_detail()
        if key in ("T", "t"):
            if self.view == "squeue":
                self._inspect_tail()
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

    def _inspect_detail(self):
        """Creates a pop-up with detailed job info for the currently highlighted job"""
        current_focus = self.top.body.original_widget.original_widget.body.focus
        row = self.top.body.original_widget.original_widget.body[current_focus]
        job_id = row.original_widget.job_id
        detail_info = self.inspector.get_job_details(job_id)
        self._info_box(detail_info.attrs)

    def _inspect_tail(self):
        """Creates a pop-up with tailbox for the slurm output of the currently
        highlighted job
        """
        current_focus = self.top.body.original_widget.original_widget.body.focus
        row = self.top.body.original_widget.original_widget.body[current_focus]
        job_id = row.original_widget.job_id
        file_path = self.inspector.get_job_details(job_id).attrs["STDOUT"]
        self._tail_box(file_path)

    def _scancel_check(self):
        """Prompts the user with yes/no prompt to cancel selected jobs"""
        self._yes_no_prompt(
            f"Are you sure you want to cancel {len(self.selected_jobs)} selected job(s)?",
            self.cancel_selected_jobs,
            self._return_to_top,
        )

    def _deselect_check(self):
        """Prompts the user with yes/no prompt for clearing current selection"""
        self._yes_no_prompt(
            f"Are you sure you want to clear selection?",
            self.clear_selection,
            self._return_to_top,
        )

    def _enter_search(self):
        """Sets the focus on the footer search urwid.EditBox"""
        self.top.focus_position = "footer"
        self.top.footer.original_widget.original_widget.focus_col = 3

    def _set_view(self, view: str):
        """Sets main TUI view"""
        if view not in ["squeue", "sinfo"]:
            raise ValueError(f"'{view}' is not a valid TUI view")
        self.view = view
        self.draw_header()
        self.draw_body()

    def _return_to_top(self, *args):
        """Removes any currently overlaid widgets and returns to the TUI urwid.Frame widget"""
        if self.tail_handle is not None:
            self.loop.remove_alarm(self.tail_handle)
            self.tail_handle = None
        self.loop.widget = self.top

    def _toggle_my_jobs(self):
        """Toggles the user-only job filter in SQUEUE calls"""
        self.top.footer.original_widget.original_widget[0].toggle_state()

    def _toggle_running_jobs(self):
        """Toggles the RUNNING state job filter in SQUEUE calls"""
        self.top.footer.original_widget.original_widget[1].toggle_state()

    def _create_top(self) -> urwid.Frame:
        """Creates main urwid.Frame widget

        Returns
        -------
        top:
            urwid.Frame instance containing a header for labeling SQUEUE/SINFO
            output columns, a body for displaying jobs/cluster options
            and a footer with useful widgets for filtering output.
        """
        headstr = self.build_headstr(self.inspector.squeue_header)
        footstr = self.build_footstr()
        jstrs = self.build_squeue_list()

        job_list = urwid.SimpleFocusListWalker(jstrs)
        self.list_focus_pos = 0
        job_win = urwid.ListBox(job_list)
        job_linebox = urwid.LineBox(job_win, **Tui._box_style_kwargs)
        body = urwid.AttrMap(job_linebox, "standard", None)

        top = urwid.Frame(
            body,
            header=urwid.AttrMap(
                urwid.LineBox(headstr, title="SlurmVision", **Tui._box_style_kwargs),
                "header",
                None,
            ),
            footer=urwid.AttrMap(
                urwid.LineBox(footstr, **Tui._box_style_kwargs), "footer", None
            ),
        )
        return top

    def _help_box(self):
        """Creates temporary Help overlay displaying
        command keystrokes for using the TUI.
        """
        if not isinstance(self.loop.widget, urwid.Overlay):
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
                urwid.AttrMap(urwid.Filler(help_box), "standard", None),
                self.top,
                align="center",
                width=("relative", 80),
                valign="middle",
                height=len(help_text) + 4,
                top=2,
                bottom=2,
                left=2,
                right=2,
            )
            self.loop.widget = w

    def _info_box(self, str_pairs: Dict[str, str]):
        """Displays an information box given a mapping of attributes
        and descriptions

        Parameters
        ----------
        str:
            Dictionary of field/values string pairs concerning
            specified job detail attributes.
        """
        if not isinstance(self.loop.widget, urwid.Overlay):
            ok = urwid.Button("OK")
            urwid.connect_signal(ok, "click", self._return_to_top)

            infos = []
            for key, value in str_pairs.items():
                infos.append(
                    urwid.Padding(urwid.Text(f"{key} : {value}"), right=3, left=3)
                )

            info_walker = urwid.SimpleListWalker(infos)
            info_list = urwid.BoxAdapter(urwid.ListBox(info_walker), height=len(infos))
            info_pile = urwid.Pile([info_list, urwid.Divider(), ok])

            info_box = urwid.AttrMap(
                urwid.LineBox(info_pile, title="Job Detail", **Tui._box_style_kwargs),
                "detail",
                None,
            )

            w = urwid.Overlay(
                urwid.AttrMap(urwid.Filler(info_box), "standard", None),
                self.top,
                align="center",
                width=("relative", 80),
                valign="middle",
                height=len(infos) + 4,
                top=2,
                bottom=2,
                left=2,
                right=2,
            )
            self.loop.widget = w

    def _tail_refresh(self, *args):
        # Grab the top (-1) widget of the Overlay
        self.loop.widget.contents[1][
            0
        ].original_widget.original_widget.original_widget.original_widget.contents[0][
            0
        ].refresh()
        self.tail_handle = self.loop.set_alarm_in(
            sec=self.tail_sleep, callback=self._tail_refresh
        )

    def _tail_box(self, file_path: str):
        """Displays tail box for STDOUT of selected job

        Parameters
        ----------
        str:
            Dictionary of field/values string pairs concerning
            specified job detail attributes.
        """
        if not isinstance(self.loop.widget, urwid.Overlay):
            ok = urwid.Button("OK")
            urwid.connect_signal(ok, "click", self._return_to_top)

            tail_text = TailText(file_path, self.num_tail_lines)
            tail_pile = urwid.Pile([tail_text, urwid.Divider(), ok])
            tail_box = urwid.AttrMap(
                urwid.LineBox(tail_pile, title="Job Output", **Tui._box_style_kwargs),
                "tail",
                None,
            )

            w = urwid.Overlay(
                urwid.AttrMap(urwid.Filler(tail_box), "standard", None),
                self.top,
                align="center",
                width=("relative", 80),
                valign="middle",
                height=self.num_tail_lines + 8,
                top=2,
                bottom=2,
                left=2,
                right=2,
            )
            self.loop.widget = w
            self.tail_handle = self.loop.set_alarm_in(
                sec=self.tail_sleep, callback=self._tail_refresh
            )

    def _error_box(self, error_msg: str):
        """Displays a temporary error message

        Parameters
        ----------
        error_msg:
            Error message to be displayed to the user
        """
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
            urwid.AttrMap(urwid.Filler(error_box), "standard", None),
            self.top,
            align="center",
            width=("relative", 60),
            valign="middle",
            height=6,
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
            urwid.AttrMap(urwid.Filler(message_box), "standard", None),
            self.top,
            align="center",
            width=("relative", 30),
            valign="middle",
            height=6,
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
            urwid.CheckBox(
                "My Jobs", state=True if self.my_jobs_first else False, has_mixed=False
            ),
            right=2,
            left=2,
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
        self.top.header = urwid.AttrMap(
            urwid.LineBox(headstr, title="SlurmVision", **Tui._box_style_kwargs),
            "header",
            None,
        )

    def draw_body(self):
        """Draws current TUI body"""
        if self.view == "squeue":
            strs = self.build_squeue_list()
        if self.view == "sinfo":
            strs = self.build_sinfo_list()
        if len(strs) == 0:
            self.top.body.original_widget.original_widget.body.clear()
        else:
            original_focus = self.top.body.original_widget.original_widget.body.focus
            if original_focus == None:
                original_focus = 0
            self.top.body.original_widget.original_widget.body.clear()
            self.top.body.original_widget.original_widget.body.extend(strs)
            self.top.body.original_widget.original_widget.body.set_focus(
                original_focus % len(strs)
            )

    def update_top(self, *args):
        """Updates the TUI and sets an urwid loop alarm to re-draw the TUI
        according to the inspector's polling interval
        """
        self.draw_body()
        self.handle = self.loop.set_alarm_in(
            self.inspector.polling_interval, self.update_top
        )

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
            if self.select_advance:
                original_focus = (
                    self.top.body.original_widget.original_widget.body.focus
                )
                self.top.body.original_widget.original_widget.set_focus(
                    (original_focus + 1)
                    % len(self.top.body.original_widget.original_widget.body)
                )
        else:
            self.selected_jobs.remove(col.original_widget.job_id)
            self.top.footer.original_widget.original_widget[2].set_text(
                f"[{len(self.selected_jobs)}] Selected"
            )
            col.set_attr_map({None: None})
            if self.select_advance:
                original_focus = (
                    self.top.body.original_widget.original_widget.body.focus
                )
                self.top.body.original_widget.original_widget.set_focus(
                    (original_focus + 1)
                    % len(self.top.body.original_widget.original_widget.body)
                )
