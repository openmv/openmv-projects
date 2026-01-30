# GENX320 Event Streaming

This project shows off how to get the raw bayer image from your OpenMV Cam to the PC.

## Setup

1. You need to have OpenMV IDE v4.8.4 or later installed. Make sure to check the IDE version by clicking on Help -> About OpenMV IDE...
2. You need to have OpenMV Cam Firmware v5.0.0 or later installed. You can check your OpenMV Cam's firmware in the status bar of the IDE after you connect. You can update your OpenMV Cams firmware to the latest by doing `Tools->Install Latest Development Release` after you connect.
3. Install our [Python Library and CLI](https://github.com/openmv/openmv-python).

## Usage

Now that you have everything installed, get the raw bayer image from your OpenMV Cam. Just do:

```
python3 -u ccm_tuning_on_pc.py --port=/dev/ttyACM0 --script=ccm_tuning_on_cam.py
```

_Assuming the camera is on `/dev/ttyACM0` COM port on linux_

The script works for Windows, Mac, and Linux.
