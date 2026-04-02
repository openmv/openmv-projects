# GenX320 Event Streaming

A PC-side GUI for streaming and visualizing events from a Prophesee GenX320 event camera sensor attached to an OpenMV Cam. Two real-time visualizations run side by side: an event accumulation canvas and a per-pixel frequency map.

![GenX320 Event Streaming GUI](genx320-event-streaming.png)

## Platform Notes

macOS and Linux are recommended for the best GUI performance and throughput. On Windows, DearPyGui rendering can be noticeably slower, which may reduce the effective event visualization frame rate at high event rates. The camera script and serial protocol work on all platforms, but if you experience sluggish UI or dropped frames, consider switching to a Mac or Linux machine.

On macOS and Linux the companion script's `read` method is automatically renamed to `readp` before execution (this is handled transparently by the PC script).

CRC is disabled by default on macOS and Linux for better USB throughput. It is enabled by default on Windows where it improves reliability. Override with `--crc`.

## Prerequisites

1. **OpenMV IDE** v4.8.8 or later.
2. **OpenMV Cam Firmware** v5.0.0 or later. Update via `Tools → Install Latest Development Release` in the IDE.
3. **Python dependencies:**

```
pip install dearpygui numpy numba pyserial Pillow openmv
```

Numba is required for the GIL-free IIR frequency camera update. On first run it JIT-compiles the inner loop (a few seconds); subsequent runs use the cached build.

## Running

```
python genx320_event_mode_streaming_on_pc.py
```

The camera script is selected automatically based on the **Stream** mode chosen in the GUI. You can override any option from the command line:

| Flag | Default | Description |
|------|---------|-------------|
| `--port PORT` | *(GUI selector)* | Serial port to connect on |
| `--script PATH` | *(set by Stream mode)* | MicroPython script to run on the camera |
| `--baudrate N` | `921600` | Serial baud rate |
| `--crc` | off (Linux/Mac), on (Windows) | Enable CRC on the serial protocol |
| `--seq` | on | Enable sequence numbers |
| `--ack` | off | Enable per-packet ACKs |
| `--quiet` | off | Suppress camera stdout |
| `--debug` | off | Enable verbose logging |
| `--benchmark` | off | Headless throughput benchmark (no GUI) |

## Benchmark Mode

Run without the GUI to measure raw USB throughput:

```
python genx320_event_mode_streaming_on_pc.py --benchmark
python genx320_event_mode_streaming_on_pc.py --benchmark --port /dev/ttyACM0
```

Prints at 10 Hz:

```
elapsed=3.2s    rate=1,243,500 ev/s    bw=8.94 MB/s    total=3,982,400
```

Press **Ctrl+C** to stop.

## GUI Overview

The window has two panes: a **left image area** and a **right control panel**. The two images resize and reflow automatically — side by side when the window is wide, stacked when tall — to maximize how large they appear. When Frequency Visualization is disabled, the event canvas expands to fill the full image area.

### Connection

- **Script** — path to the MicroPython script. Click `...` to browse.
- **Port** — serial port drop-down. Hit **Ref** to refresh.
- **Connect / Disconnect** — starts or stops the camera worker thread.

### Camera Parameters *(applied at connect)*

These patch the on-camera script before it is executed. They are locked while connected.

| Control | Default | Description |
|---------|---------|-------------|
| Stream | Raw (fastest) | **Raw (fastest)** — streams unprocessed EVT 2.0 words, decoded on the PC; **Processed** — camera decodes events before sending |
| CSI FIFO | 8 | Depth of the hardware CSI receive buffer |
| EVT FIFO | 8 | Depth of the software event FIFO (Processed mode only) |
| EVT Buffer | 8192 | Event array size (must be a power of two, 1024–65536) |

### Event Visualization

Controls for the accumulation canvas (left image).

| Control | Default | Description |
|---------|---------|-------------|
| Contrast | 16 | Per-event brightness step added to the canvas (±) |
| Color | Grayscale | Color LUT: **Grayscale**, **Evt Dark**, or **Evt Light** (OpenMV rainbow palette) |
| Mode | Sliding Window | **Sliding Window** — shows the last N batches live; **Canvas** — accumulates until N batches then auto-clears (0 = manual clear only) |
| Window | 4 | Number of batches kept or accumulated |
| Clear | *(button)* | Available in Canvas mode with Window = 0; manually clears the canvas |

The canvas is initialized to mid-gray (128). Each event adds `±contrast` to its pixel and the result is clamped to [0, 255].

#### Frequency Visualization

Real-time per-pixel frequency map (right image) using a second-order IIR bandpass filter that reconstructs approximate brightness from the polarity event stream and measures the time between zero crossings. Uncheck **Frequency Visualization** to hide the frequency image entirely and expand the event canvas — this also reduces CPU load and disables frequency image saving.

Algorithm based on: [FrequencyCam — Imaging Periodic Signals in Real-Time](https://arxiv.org/abs/2211.00198)

| Control | Default | Description |
|---------|---------|-------------|
| Cutoff T | 5.0 | Filter cutoff period in events. Higher values smooth more but respond slower. Reference recommends 5.0. |
| Min Hz | 10 | Lowest frequency shown (pixels below this are black) |
| Max Hz | 1000 | Highest frequency shown |
| Timeout | 2 | Number of silent periods before a pixel goes dark |
| Log frequency scale | on | Log₁₀ color mapping (recommended for wide frequency ranges) |
| Overlay active pixels | off | Show pixels that have event activity but no locked frequency in grey |
| Show legend | on | Display a colorbar on the right edge of the frequency image |
| Bins | 11 | Number of labeled color patches in the legend |
| Reset | *(button)* | Clear all per-pixel filter state |

Colors run blue (low frequency) → red (high frequency). Black pixels either have no events yet or have timed out.

### Save Images and Events

Saves the current state to disk. The button label reflects whether frequency visualization is enabled.

- `events_<timestamp>_evt.png` — the event canvas rendered with the current color LUT.
- `events_<timestamp>_freq.png` — the frequency image (only saved when Frequency Visualization is enabled). If the legend is enabled it is composited onto the right side of the image.
- `events_<timestamp>.csv` — all events that built the current canvas (`type, sec, ms, us, x, y`). See **Camera Script Event Format** below for type values.

These files are excluded from git via `.gitignore`.

### Statistics

Live event throughput, updated at 5 Hz:

| Field | Description |
|-------|-------------|
| Events/batch | Raw event count in the most recent batch |
| Rate | Exponential moving average event rate (events/sec) |
| Bandwidth | EMA data rate (MB/s) |
| Total events | Cumulative event count since connect |
| Uptime | Seconds since connect |

## Architecture

The script uses a three-thread pipeline to keep USB throughput high while running the GUI:

```
camera_worker  →  raw_q  →  processing_worker  →  result_q  →  render loop
```

- **camera_worker** — reads raw event packets from the camera as fast as possible and drops them onto `raw_q`. Does no processing, never blocks on GUI.
- **processing_worker** — pulls batches from `raw_q`, accumulates the canvas, and runs the per-pixel IIR frequency filter via a Numba-compiled `nogil` function so it does not block the camera thread.
- **render loop** — drains `result_q`, uploads textures to DearPyGui, and updates the stats panel.

## Camera Script Event Format

Both camera scripts produce the same event format on the PC side — a stream of 6 × uint16 little-endian rows:

| Column | Value |
|--------|-------|
| 0 | Type — see table below |
| 1 | Timestamp — whole seconds |
| 2 | Timestamp — milliseconds within the second (0–999) |
| 3 | Timestamp — microseconds within the millisecond (0–999) |
| 4 | X coordinate (0–319); 0 for trigger events |
| 5 | Y coordinate (0–319); 0 for trigger events |

| Type value | Meaning |
|------------|---------|
| 0 | Pixel off event (decrease in illumination) |
| 1 | Pixel on event (increase in illumination) |
| 2 | External trigger — falling edge |
| 3 | External trigger — rising edge |
| 4 | Reset trigger — falling edge |
| 5 | Reset trigger — rising edge |

**Raw mode** (`genx320_raw_event_mode_streaming_on_cam.py`) streams unprocessed 32-bit EVT 2.0 words from the sensor (4 bytes/event vs 12 bytes/event in processed mode — 3× less data over USB). The PC decodes them vectorized using numpy with no Python loop. The decoded output is identical to processed mode.

**Processed mode** (`genx320_event_mode_streaming_on_cam.py`) has the camera firmware decode each event before transmission. The event buffer size, CSI FIFO depth, and (in processed mode) event FIFO depth are patched into the script at connect time from the GUI values.
