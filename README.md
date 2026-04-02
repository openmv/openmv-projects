[![GitHub forks](https://img.shields.io/github/forks/openmv/openmv-projects?color=green)](https://github.com/openmv/openmv-projects/network)
[![GitHub stars](https://img.shields.io/github/stars/openmv/openmv-projects?color=yellow)](https://github.com/openmv/openmv-projects/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/openmv/openmv-projects?color=orange)](https://github.com/openmv/openmv-projects/issues)
[![GitHub license](https://img.shields.io/github/license/openmv/openmv-projects?label=license%20%E2%9A%96)](https://github.com/openmv/openmv-projects/blob/master/LICENSE)

<img width="480" src="https://raw.githubusercontent.com/openmv/openmv-media/master/logos/openmv-logo/logo.png">

# OpenMV Projects

A collection of projects built with the [OpenMV Cam](https://openmv.io) — a small, low-power microcontroller board with a built-in camera, designed for machine vision applications at the edge.

- [PC Tools](#pc-tools)
- [Robotics](#robotics)
- [Contributing](#contributing)

---

## PC Tools

Desktop GUI applications that pair with an OpenMV Cam over USB to provide real-time visualization, calibration, and analysis workflows. These tools run on your PC while the camera handles capture and streaming.

| Project | Description |
|---------|-------------|
| [GenX320 Event Streaming](tools/genx320-event-streaming/README.md) | Real-time event camera visualization with per-pixel frequency mapping for the Prophesee GenX320 sensor |
| [CCM Tuning](tools/ccm-tuning/README.md) | Interactive Color Correction Matrix tuner — streams raw Bayer frames and replicates the N6 ISP pipeline in software |

Browse all tools → [tools/](tools/README.md)

---

## Robotics

Complete robotics projects that use the OpenMV Cam as the primary perception system — from autonomous rovers to self-driving cars.

| Project | Description |
|---------|-------------|
| [Donkey Self-Driving Car](robotics/donkey-car/README.md) | OpenMV-powered Donkey Car build with line following and autonomous driving |
| [Autonomous Rover](robotics/autonomous-rover/README.md) | Tracked rover using monocular edge detection for obstacle avoidance, controlled by a Teensy 3.5 |

Browse all robotics projects → [robotics/](robotics/README.md)

---

## Contributing

Contributions are welcome. If you have a project built with an OpenMV Cam that you'd like to share, open a pull request with your project in the appropriate subfolder (`tools/` or `robotics/`) along with a `README.md` and any supporting images.

Please follow the existing folder structure and include:
- A clear `README.md` describing what the project does and how to run it
- Any images or screenshots in an `images/` subfolder
- Source code and dependencies listed
