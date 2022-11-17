# SlurmVision

---

Simple tool for browsing, inspecting, canceling SLURM jobs. Greatly inspired by
mil-ad's [stui](https://github.com/mil-ad/stui).

## Install

Urwid and python >= 3.6 

```
git clone https://github.com/ruunyox/slurmvision
cd slurmvision
pip3 install .
```

## Usage

`slurmvision --help`

Press `h` for information on controls.

## Configuration

A user-specific YAML file of configuration options can be read from `$HOME/.config/slurmvision.yml` or the `--config` CLI argument can be used to specify a config file elsewhere. A sample configuration file is shown here:

```
squeue_opts:
  polling_interval: 1
  getopts: null
  formopts:
    "--Format": "JobId,UserName,Name:256,STATE,ReasonList,TimeUsed"
sinfo_opts:
  getopts: null
  formopts:
    "-o": "%10P %5c %5a %10l %20G %4D %6t"
detail_opts:
  formopts:
    "--Format": "JobId:256,UserName:256,Name:256,STATE:256,Reason:256,Nodes:256,NumCPUs:256,cpus-per-task:256,Partition:256,TimeUsed:256,TimeLeft:256,SubmitTime:256,StartTime:256,STDOUT:256,WorkDir:256"
tui_opts:
  select_advance: false
```

