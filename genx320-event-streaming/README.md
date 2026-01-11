# GENX320 Event Streaming

This project shows off how to stream events from your OpenMV Cam to the PC with a GENX320 event sensor.

## Setup

1. You need to have OpenMV IDE v4.8.1 or later installed. Make sure to check the IDE version by clicking on Help -> About OpenMV IDE...
2. You need to have OpenMV Cam Firmware v5.0.0 or later installed. You can check your OpenMV Cam's firmware in the status bar of the IDE after you connect.
3. Install our [Python Library and CLI](https://github.com/openmv/openmv-python).

## Usage

Now that you have everything installed, you can stream events from your OpenMV Cam with the GENX320 camera sensor to the PC. Just do:

```
python3 -u --port=/dev/ttyACM0 --script=genx320_event_mode_streaming_on_cam.py
```

_Assuming the camera is on `/dev/ttyACM0` COM port on linux_

The script works for Windows, Mac, and Linux.

After running that command you should see an output like so:

[Event Streaming Video](event-streaming.mp4)

## Details

More details on how the script works and thoughts.

[Explainer Video](explainer.mp4)
