from typing import List, Dict, Optional, Tuple, Union, Callable
import subprocess
import json
from threading import Thread, Event
from time import sleep
import os

MAX_CHAR = 256


class Job(object):
    """Class for storing metadata about a SLURM job

    Parameters
    ----------
    attrs:
        Dictionary of SQUEUE header/job attribute key value pairs
    """

    _valid_fields = None

    def __init__(self, attrs: Dict[str, str]):
        self.attrs = attrs

    def __str__(self) -> str:
        return json.dumps(self.attrs, indent=2)


class Inspector(object):
    """Requests and Stores SQUEUE and SINFO output
    through subprocess calls

    Parameters
    ----------
    polling_interval:
        Number of seconds to wait in between each SQUEUE subprocess call
    squeue_getopts:
        Dictionary of flag/argument key/value pairs for use with SQUEUE.
        See https://slurm.schedmd.com/squeue.html for more information.
    squeue_formopts:
        Single entry dictionary with the key -O/--Format and the value
        specifying valid SQUEUE extended formatting options. See
        https://slurm.schedmd.com/squeue.html for more information.
    sinfo_getopts:
        Dictionary of flag/argument key/value pairs for use with SINFO.
        See https://slurm.schedmd.com/sinfo.html for more information.
    sinfo_formopts:
        Single entry dictionary with the key -o/--format and the value
        specifying valid SINFO formatting options. See
        https://slurm.schedmd.com/sinfo.html for more information.
    detail_formopts:
        Single entry dictionary with the key -O/--Format and the value
        specifying valid SQUEUE extended formatting options. See
        https://slurm.schedmd.com/squeue.html for more information. For
        use in inspecting single, specifc jobs.
    """

    def __init__(
        self,
        polling_interval: float = 1,
        squeue_getopts: Optional[Dict[str, str]] = None,
        squeue_formopts: Optional[Dict[str, str]] = None,
        sinfo_getopts: Optional[Dict[str, str]] = None,
        sinfo_formopts: Optional[Dict[str, str]] = None,
        detail_formopts: Optional[Dict[str, str]] = None,
    ):
        self.polling_interval = polling_interval
        if squeue_getopts != None:
            self.squeue_getopts = squeue_getopts
        else:
            self.squeue_getopts = {}

        if sinfo_getopts != None:
            self.sinfo_getopts = sinfo_getopts
        else:
            self.sinfo_getopts = {}

        if squeue_formopts == None:
            self.squeue_formopts = {
                "-O": f"JobId,UserName,Name:{MAX_CHAR},STATE,ReasonList,TimeUsed"
            }
        else:
            assert len(squeue_formopts) == 1
            self.squeue_formopts = squeue_formopts

        if sinfo_formopts == None:
            self.sinfo_formopts = {"-o": "%10P %5c %5a %10l %20G %4D %6t"}
        else:
            assert len(sinfo_formopts) == 1
            self.sinfo_formopts = sinfo_formopts

        if detail_formopts == None:
            self.detail_formopts = {
                "-O": f"JobId:{MAX_CHAR},UserName:{MAX_CHAR},Name:{MAX_CHAR},STATE:{MAX_CHAR},Reason:{MAX_CHAR},Nodes:{MAX_CHAR},NumCPUs:{MAX_CHAR},cpus-per-task:{MAX_CHAR},Partition:{MAX_CHAR},TimeUsed:{MAX_CHAR},TimeLeft:{MAX_CHAR},SubmitTime:{MAX_CHAR},StartTime:{MAX_CHAR},STDOUT:{MAX_CHAR},WorkDir:{MAX_CHAR}"
            }
        else:
            assert len(detail_formopts) == 1
            self.detail_formopts

        self.jobs = []
        self.squeue_header = None
        self.sinfo = []
        self.sinfo_header = None
        self.get_info()
        self.user = os.environ["USER"]
        self.detail_info = None
        self.detail_info_header = None

    def toggle_user_filter(self, *args):
        """Toggles filtering of user-only jobs"""
        if "-u" not in list(self.squeue_getopts.keys()):
            self.squeue_getopts["-u"] = self.user
        else:
            del self.squeue_getopts["-u"]

    def toggle_running_filter(self, *args):
        """Toggles filtering of running jobs"""
        if "--state" not in list(self.squeue_getopts.keys()):
            self.squeue_getopts["--state"] = "RUNNING"
        else:
            del self.squeue_getopts["--state"]

    @staticmethod
    def parse_squeue_output(squeue_output: str) -> Tuple[List[Job], str]:
        """Parses SQUEUE output and extracts jobs

        Parameters
        ----------
        squeue_output:
            stdout string from SQUEUE subprocess call

        Returns
        -------
        jobs:
            List of `Job` instances for each job parsed from the SQUEUE output
        header:
            SQUEUE output header string
        """

        lines = squeue_output.split("\n")[:-1]  # Final line is a double return
        header = lines[0].split()
        jobs = []
        for line in lines[1:]:
            tokens = line.split()
            job = Job({h: t for h, t in zip(header, tokens)})
            jobs.append(job)
        return jobs, header

    @staticmethod
    def parse_sinfo_output(sinfo_output: str) -> Tuple[List[Dict[str, str]], str]:
        """Parses SINFO output

        Parameters
        ----------
        sinfo_output:
            stdout string from SINFO subprocess call

        Returns
        -------
        strs:
            List of dictionaries, where each dictionary contains an sinfo output
            row parsed into SINFO header/value key/value pairs
        header:
            SINFO output header string
        """

        lines = sinfo_output.split("\n")[:-1]  # Final line is a double return
        header = lines[0].split()
        strs = []
        for line in lines[1:]:
            tokens = line.split()
            str_ = {h: t for h, t in zip(header, tokens)}
            strs.append(str_)
        return strs, header

    @staticmethod
    def build_s_cmd(
        base_cmd: str = "squeue",
        getopts: Optional[Dict[str, str]] = None,
        formopts: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Constructs SQUEUE/SINFO command for subprocess call

        Parameters
        ----------
        base_cmd:
            string representing the base command to use in a subprocess call
        getopts:
            Non-formatting based option dictionary constructed from flag/argument
            key/value pairs. See https://slurm.schedmd.com/sinfo.html and
            https://slurm.schedmd.com/squeue.html for more information.
        formopts:
            Formating option dictionary constructed from a single entry flag/argument
            key/value pair. See https://slurm.schedmd.com/sinfo.html and
            https://slurm.schedmd.com/sinfo.html for more information.

        Returns
        -------
        cmd:
            List of strings representing command tokens for subprocess calls
        """

        cmd = [base_cmd]
        if getopts != None:
            for optarg in getopts.items():
                cmd.extend(optarg)
        if formopts != None:
            cmd.extend(list(formopts.items())[0])
        return cmd

    def get_jobs(self):
        """Populates the jobs and squeue_header attributes according to
        user-specified SQUEUE options.
        """

        squeue_cmd = Inspector.build_s_cmd(
            "squeue", self.squeue_getopts, self.squeue_formopts
        )
        cmd_output = subprocess.run(squeue_cmd, capture_output=True)
        squeue_output = cmd_output.stdout.decode("utf-8")
        self.jobs, self.squeue_header = Inspector.parse_squeue_output(squeue_output)

    def get_info(self):
        """Populated the sinfo and sinfo_header attributes according to
        user-specified SINFO options.
        """

        sinfo_cmd = Inspector.build_s_cmd(
            "sinfo", self.sinfo_getopts, self.sinfo_formopts
        )
        cmd_output = subprocess.run(sinfo_cmd, capture_output=True)
        sinfo_output = cmd_output.stdout.decode("utf-8")
        self.sinfo, self.sinfo_header = Inspector.parse_sinfo_output(sinfo_output)

    def get_job_details(self, job_id: str) -> Job:
        """Get detailed information for a single specific job to store
        in the job_info attribute according to the job_formopts specifications

        Parameters
        ----------
        job_id:
            String of the numerical SLURM job ID for which detailed information
            has been requested
        """

        detail_cmd = Inspector.build_s_cmd(
            "squeue", {"-j": job_id}, self.detail_formopts
        )
        cmd_output = subprocess.run(detail_cmd, capture_output=True)
        detail_output = cmd_output.stdout.decode("utf-8")
        detail_info, _ = Inspector.parse_squeue_output(detail_output)
        return detail_info[0]

    def cancel_job(self, job_id: str) -> subprocess.CompletedProcess:
        """Calls SCANCEL on the specified job ID.

        Parameters
        ----------
        job_id:
            String specifying the numerical SLURM job ID associated with the
            job to be cancelled

        Return
        ------
        output:
            Subprocess output for checking command success/failure
        """

        output = subprocess.run(["scancel", job_id], capture_output=True)
        return output


class SlurmThread(Thread):
    """Thread for periodically polling SLURM info

    Parameters
    ----------
    inspector:
        Inspector instance from which SLURM commands may
        be subprocessed
    """

    def __init__(self, inspector: Inspector):
        Thread.__init__(self)
        self.stop_event = Event()
        self.inspector = inspector

    def run(self):
        """Main thread polling loop. Sleeps after each poll, as
        specified by the inspector.polling_interval attribute
        """
        while not self.stop_event.isSet():
            self.inspector.get_jobs()
            sleep(self.inspector.polling_interval)

    def join(self, timeout: Union[int, None] = None):
        """Safely request thread to end

        Parameters
        ----------
        timeout:
            Number of seconds to wait before thread join attempt ends.
        """
        self.stop_event.set()
        Thread.join(self, timeout=timeout)
