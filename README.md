[![GitHub license](https://img.shields.io/github/license/openmv/openmv-projects?label=license%20%E2%9A%96)](https://github.com/openmv/openmv-projects/blob/master/LICENSE)
[![GitHub forks](https://img.shields.io/github/forks/openmv/openmv-projects?color=green)](https://github.com/openmv/openmv-projects/network)
[![GitHub stars](https://img.shields.io/github/stars/openmv/openmv-projects?color=yellow)](https://github.com/openmv/openmv-projects/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/openmv/openmv-projects?color=orange)](https://github.com/openmv/openmv-projects/issues)

<img width="480" src="https://raw.githubusercontent.com/openmv/openmv-media/master/logos/openmv-logo/logo.png">

# OpenMV Projects

A collection of projects built with the [OpenMV Cam](https://openmv.io) — a small, low-power microcontroller board with a built-in camera, designed for machine vision applications at the edge.

- [PC Tools](#pc-tools)
- [Robotics](#robotics)
- [Contributing to the project](#contributing-to-the-project)
  + [Contribution guidelines](#contribution-guidelines)

---

## PC Tools

Desktop GUI applications that pair with an OpenMV Cam over USB to provide real-time visualization, calibration, and analysis workflows. These tools run on your PC while the camera handles capture and streaming.

| Project | Description |
|---------|-------------|
| [GenX320 Viz](tools/genx320-event-streaming/README.md) | Real-time event camera visualization with per-pixel frequency mapping for the Prophesee GenX320 sensor. |
| [Thermal Overlay Calibration](tools/thermal-overlay-calibration/README.md) | Streams color and FLIR Lepton thermal frames simultaneously and composites them with manual or automatic heated-checkerboard homography alignment. |
| [CCM Tuning](tools/ccm-tuning/README.md) | Interactive Color Correction Matrix tuner — streams raw Bayer frames and replicates the N6 ISP pipeline in software. |

[Browse all tools](tools/README.md)

---

## Robotics

Complete robotics projects that use the OpenMV Cam as the primary perception system — from autonomous rovers to self-driving cars.

| Project | Description |
|---------|-------------|
| [Donkey Car](robotics/donkey-car/README.md) | OpenMV-powered Donkey Car build with line following and autonomous driving. |
| [Autonomous Rover](robotics/autonomous-rover/README.md) | Tracked rover using monocular edge detection for obstacle avoidance, controlled by a Teensy 3.5. |

[Browse all robotics projects](robotics/README.md)

---

## Contributing to the project

Contributions are most welcome. If you are interested in contributing to the project, start by creating a fork of the following repository:

* https://github.com/openmv/openmv-projects.git

Clone the forked repository, and add a remote to the main repository:
```bash
git clone https://github.com/<username>/openmv-projects.git
git -C openmv-projects remote add upstream https://github.com/openmv/openmv-projects.git
```

Now the repository is ready for pull requests. To send a pull request, create a new feature branch and push it to origin, and use GitHub to create the pull request from the forked repository to the upstream openmv/openmv-projects repository. For example:
```bash
git checkout -b <some_branch_name>
<commit changes>
git push origin -u <some_branch_name>
```

### Contribution guidelines

Please follow the [best practices](https://developers.google.com/blockly/guides/modify/contribute/write_a_good_pr) when sending pull requests upstream. In general, the pull request should:
* Fix one problem. Don't try to tackle multiple issues at once.
* Split the changes into logical groups using git commits.
* Pull request title should be less than 78 characters, and match this pattern:
  * `<scope>:<1 space><description><.>`
* Commit subject line should be less than 78 characters, and match this pattern:
  * `<scope>:<1 space><description><.>`
