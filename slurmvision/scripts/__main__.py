#! /usr/bin/env python

from slurmvision.slurm.utils import slurm_check
from slurmvision.tui import Tui
from slurmvision.slurm import Inspector
import argparse
from ruamel.yaml import YAML
import os
from time import sleep


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="TUI for inspecting and managing SLURM jobs."
    )
    parser.add_argument(
        "--config",
        default=None,
        type=str,
        help="Specifies the absolute path to a slurmvision configuration YAML",
    )
    return parser


def main():
    slurm_check()

    yaml = YAML(typ="safe")
    yaml.default_flow_style = False

    parser = parse_arguments()
    opts = parser.parse_args()

    if opts.config != None:
        with open(opts.config, "r") as yfile:
            config = yaml.load(yfile)
    else:
        default_config_dir = os.path.join(os.environ["HOME"], ".config/slurmvision.yml")
        try:
            with open(default_config_dir, "r") as yfile:
                config = yaml.load(yfile)
        except:
            print(
                f"Unable to load user config at {default_config_dir}. Proceeding with default options..."
            )
            outer_keys = ["squeue_opts", "sinfo_opts", "detail_opts", "tui_opts"]
            config = {outer_key: {} for outer_key in outer_keys}
            config["delimeter"] = " "
            config["squeue_opts"] = {
                "polling_interval": 10,
                "getopts": None,
                "formopts": {
                    "--Format": "JobId: ,UserName: ,Name: ,STATE: ,ReasonList: ,TimeUsed: "
                },
            }
            config["sinfo_opts"] = {
                "getopts": None,
                "formopts": {"-o": "%10P %5c %5a %10l %20G %4D %6t"},
            }
            config["detail_opts"] = {
                "formopts": {
                    "--Format": "JobId: ,UserName: ,Name: ,STATE: ,Reason:, Nodes: ,NumCPUs: ,cpus-per-task: ,Partition: ,TimeUsed: ,TimeLeft: ,SubmitTime: ,StartTime: ,STDOUT: ,WorkDir: "
                }
            }
            config["tui_opts"] = {"select_advance": True, "my_jobs_first": True}

    if "palette" not in list(config["tui_opts"].keys()):
        config["tui_opts"]["palette"] = None

    inspector = Inspector(
        polling_interval=config["squeue_opts"]["polling_interval"],
        squeue_getopts=config["squeue_opts"]["getopts"],
        squeue_formopts=config["squeue_opts"]["formopts"],
        sinfo_getopts=config["sinfo_opts"]["getopts"],
        sinfo_formopts=config["sinfo_opts"]["formopts"],
        detail_formopts=config["detail_opts"]["formopts"],
        delimeter=config["delimeter"],
    )
    tui = Tui(inspector, **config["tui_opts"])
    tui.start()


if __name__ == "__main__":
    main()
