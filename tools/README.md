# OpenMV PC Tools

Desktop GUI applications that pair with an OpenMV Cam over USB serial. Each tool runs a companion MicroPython script on the camera that handles capture and streaming, while the PC side provides real-time visualization, analysis, and parameter tuning.

All tools are built with [DearPyGui](https://github.com/hoffstadt/DearPyGui) and communicate with the camera via the [openmv](https://pypi.org/project/openmv/) Python package.

> **Platform note:** macOS and Linux give the best performance. On Windows, GUI rendering and USB transfer throughput can be lower, which may reduce frame or event rates at high data volumes.

---

## [GenX320 Event Streaming](genx320-event-streaming/README.md)

Real-time streaming and visualization for the [Prophesee GenX320](https://www.prophesee.ai/event-camera-genx320/) event camera sensor attached to an OpenMV Cam. Events are displayed as an accumulation canvas alongside a per-pixel frequency map computed in real time using a second-order IIR bandpass filter (FrequencyCam algorithm).

![GenX320 Event Streaming GUI](genx320-event-streaming/genx320-event-streaming.png)

**Key features:**
- Dual visualization: event canvas + frequency heatmap side by side
- Adaptive layout that maximizes image size as the window resizes
- Colorbar legend with log or linear frequency scale
- Save event CSV and frequency PNG to disk
- Configurable FIFO depths, event buffer size, contrast, and colormap

```
pip install dearpygui numpy pyserial Pillow openmv
python genx320-event-streaming/genx320_event_mode_streaming_on_pc.py
```

---

## [CCM Tuning](ccm-tuning/README.md)

An interactive Color Correction Matrix (CCM) tuner for the OpenMV N6 camera. Streams raw Bayer frames over USB and applies a full software replica of the N6 ISP pipeline — debayer, black level, auto white balance, CCM, brightness/contrast/gamma — so you can tune every parameter live without reflashing.

![CCM Tuning GUI](ccm-tuning/ccm-tuning.jpg)

**Key features:**
- Live ISP pipeline: Raw Bayer → Debayer → Black Level → AWB → CCM → BCG
- ColorChecker Classic solver: click four corners, get a least-squares CCM instantly
- Multi-illuminant workflow: solve under each light source, record R/G and B/G ratios for piecewise interpolation in firmware
- Save processed frame (BMP) and full pipeline state (TXT) to disk

```
pip install dearpygui opencv-python numpy pyserial Pillow openmv
python ccm-tuning/ccm_tuning_on_pc.py
```
