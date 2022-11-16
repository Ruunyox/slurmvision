#! /usr/bin/env python

from slurmvision.slurm.utils import slurm_check
from slurmvision.tui import Tui
from slurmvision.slurm import Inspector


def main():
    slurm_check()
    inspector = Inspector()
    tui = Tui(inspector)
    tui.start()


if __name__ == "__main__":
    main()
