import subprocess


def slurm_check():
    cmds = ["squeue", "sinfo"]
    try:
        subprocess.check_output(["squeue"])
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            "Unable to communicate with SLURM services. Check SLURM/cluster status"
        )
