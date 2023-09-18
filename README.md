# SlurmVision

---

Simple tool for browsing, inspecting, canceling SLURM jobs. Greatly inspired by
mil-ad's [stui](https://github.com/mil-ad/stui). Please be aware of your cluster's rules (if any) concerning
'squeue'/'sinfo' polling request frequency. Currently a minimum of 10 seconds for a polling interval
is suggested by default. If you wish to poll more frequently, do so at your own risk (per the license)
and/or after consultation with your cluster admin(s). Enjoy!

![slurmvision-a-tui-for-monitoring-inspecting-and-canceling-v0-c2x03yi3oz0a1](https://github.com/Ruunyox/slurmvision/assets/42926839/701ae6d0-6917-4f54-b59e-2f5330b08803)


## Install

```
git clone https://github.com/ruunyox/slurmvision
cd slurmvision
pip3 install .
```

## Usage

`slurmvision --help`

Press `h` for information on controls while running.

## Configuration

A user-specific YAML file of configuration options can be read from `$HOME/.config/slurmvision.yml` or the `--config` CLI argument can be used to specify a config file elsewhere. A sample configuration file is shown here:

```
squeue_opts:
  polling_interval: 10
  getopts: null
  formopts:
    "--Format": "JobId,UserName,Name:256,STATE,ReasonList:256,TimeUsed"
sinfo_opts:
  getopts: null
  formopts:
    "-o": "%10P %5c %5a %10l %20G %4D %6t"
detail_opts:
  formopts:
    "--Format": "JobId:256,UserName:256,Name:256,STATE:256,Reason:256,Nodes:256,NumCPUs:256,cpus-per-task:256,Partition:256,TimeUsed:256,TimeLeft:256,SubmitTime:256,StartTime:256,STDOUT:256,WorkDir:256"
tui_opts:
  select_advance: true
  my_jobs_first: true
  palette: null
```

The user configuration can also specify a specific palette using standard Urwid named colors as a nested list:

```
# all color specifications are represented by ["name", "fg", "bg"]
tui_opts:
  palette:
    -
      # Color of job/cluster window
      - "standard" 
      - "white"
      - "dark magenta"
    -
      # Color of header window
      - "header"
      - "black"
      - "white"
    -
      # Color of footer window
      - "footer"
      - "black"
      - "white"
    -
      # Color of jobs that have been selected
      - "selected"
      - "dark red"
      - "dark magenta"
    -
      # Color of warning pop-ups
      - "warning"
      - "black"
      - "dark red"
    -
      # Color of help messages
      - "help"
      - "black"
      - "yellow"
    -
      # Color of detailed job info pop-ups
      - "detail"
      - "black"
      - "white"
    -
      # Color of error pop-ups
      - "error"
      - "black"
      - "dark red"
    -
      # Color of currently highlighted job
      - "focus"
      - "black"
      - "dark magenta"
```
Any unspecified palette options will assume default options.
