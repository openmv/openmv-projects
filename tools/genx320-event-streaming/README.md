# GenX320 Event Streaming

A PC-side GUI for streaming and visualizing events from a Prophesee GenX320 event camera sensor attached to an OpenMV Cam. Two real-time visualizations run side by side: an event accumulation canvas and a per-pixel frequency map.

![GenX320 Event Streaming GUI](genx320-event-streaming.png)

## Platform Notes

macOS and Linux are recommended for the best GUI performance and throughput. On Windows, DearPyGui rendering can be noticeably slower, which may reduce the effective event visualization frame rate at high event rates. The camera script and serial protocol work on all platforms, but if you experience sluggish UI or dropped frames, consider switching to a Mac or Linux machine.

On macOS and Linux the companion script's `read` method is automatically renamed to `readp` before execution (this is handled transparently by the PC script).

CRC is disabled by default on macOS and Linux for better USB throughput. It is enabled by default on Windows where it improves reliability. Override with `--crc`.

## Prerequisites

1. **Python 3.12 or newer.** The `openmv` package uses enum membership tests that only work on Python 3.12+. The script will fail fast with a clear message on older Python versions. Install via [pyenv](https://github.com/pyenv/pyenv), the [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) on Ubuntu, or [python.org](https://www.python.org/downloads/).
2. **OpenMV IDE** v4.8.8 or later.
3. **OpenMV Cam Firmware** v5.0.0 or later. Update via `Tools → Install Latest Development Release` in the IDE.
4. **Python dependencies:**

```
pip install dearpygui numpy numba pyserial Pillow openmv
```

Numba is required for the GIL-free IIR frequency camera update. On first run it JIT-compiles the inner loop (a few seconds); subsequent runs use the cached build. Pillow is optional (used for legend rendering and frequency image saving).

If a required package is missing the script will exit at startup with a `pip install ...` command listing every missing package.

## Running

```
python genx320_event_mode_streaming_on_pc.py
```

The camera script is selected automatically based on the **Stream** mode chosen in the GUI. You can override any option from the command line:

| Flag | Default | Description |
|------|---------|-------------|
| `--port PORT` | *(GUI selector)* | Serial port to connect on |
| `--script PATH` | *(set by Stream mode)* | MicroPython script to run on the camera |
| `--evt-format FMT` | `EVT21` | Raw event stream format: `EVT20`, `EVT21`, `EVT30`, or `AER` (all decoded on the PC) |
| `--baudrate N` | `921600` | Serial baud rate |
| `--crc` | off (Linux/Mac), on (Windows) | Enable CRC on the serial protocol |
| `--seq` | on | Enable sequence numbers |
| `--ack` | off | Enable per-packet ACKs |
| `--quiet` | off | Suppress camera stdout |
| `--debug` | off | Enable verbose logging |
| `--benchmark` | off | Headless throughput benchmark (no GUI) |
| `--decode FILE` | — | Decode a recorded `.raw`/`.bin` to events and exit (see [Decoding Recordings Offline](#decoding-recordings-offline)) |
| `--npy` | off | With `--decode`, write a NumPy `.npy` array instead of CSV |
| `--out FILE` | *(input name)* | With `--decode`, output path |

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
| Stream | Raw (fastest) | **Raw (fastest)** — streams unprocessed sensor words, decoded on the PC; **Processed** — camera decodes events before sending |
| Format | EVT2.1 | Sensor output event format (Raw mode only): **EVT2.0**, **EVT2.1** *(default — Prophesee-recommended; the sensor's native vectorized format, fast/robust to decode)*, **EVT3.0**, **AER** — all decoded on the PC. See **Event Stream Formats** below. |
| CSI FIFO | 8 | Depth of the hardware CSI receive buffer |
| EVT FIFO | 8 | Depth of the software event FIFO (Processed mode only) |
| EVT Buffer | 8192 | Event array size (must be a power of two, 1024–65536) |

#### Event Stream Formats

In Raw mode the **Format** combo selects the sensor's output event format. The
on-camera script writes the format-selection registers before streaming
(`EDF_CONTROL` at `0x7044` for the PSEE formats, `CPI_PIPELINE_CONTROL` at
`0x8000` bit 4 for AER), and the PC decodes the stream accordingly.

| Format | Word size | Status |
|--------|-----------|--------|
| **EVT2.0** | 32-bit | Fully decoded on the PC. |
| **EVT2.1** *(default)* | 64-bit | Vectorized extension of EVT2.0 and the sensor's native internal format; Prophesee-recommended. Fully decoded on the PC with vectorized NumPy (fast, no JIT warmup). Best for high-rate/bursty scenes; least byte-dense on sparse scenes (8 bytes per isolated event). |
| **EVT3.0** | 16-bit | Compressed, stateful format — fully decoded on the PC (sequential numba-compiled decoder, with a brief first-batch JIT compile). Most byte-dense when activity clusters within rows. |
| **AER** | 19-bit (3 bytes) | Legacy SNN format — CD events only, **no timestamps** (so frequency visualization is unavailable; the event canvas still works). Decoded on the PC. |

> **AER byte packing:** AER encodes one CD event in 19 bits (`pol[18] | x[17:9] | y[8:0]`) packed into **3 little-endian bytes** (`AER_EVENT_BYTES` in `genx320_event_mode_streaming_on_pc.py`). The capture frame size (`EVT_RES * 4` bytes) is not a multiple of 3, so each frame ends with a few padding bytes — frames are decoded individually from their start and the remainder is dropped (frames do not straddle). Decoding the stream at a 4-byte stride instead byte-misaligns 2 of every 3 events and produces spurious "marching line" artifacts.

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
- `events_<timestamp>.csv` and `events_<timestamp>.npy` — all events that built the current canvas (`type, sec, ms, us, x, y`), written in both formats: CSV for eyeballing/portability and a compact `.npy` for instant `np.load()`. See **Camera Script Event Format** below for type values.

These files are excluded from git via `.gitignore`.

### Record Raw Events

Continuous recording of the unprocessed sensor stream to a file. The button is **only enabled when connected in Raw stream mode** — in Processed mode the camera firmware has already decoded the events, so there is no raw stream to capture.

Click **Record Raw Events** to begin a recording. The button changes to **Stop Recording** and the file grows as events stream in (no buffering — every USB packet is flushed as it arrives). Click again to stop; the file is closed and the elapsed time / byte count is logged.

The **File** combo selects the output container (locked while a recording is in progress). The recorded stream is whatever the **Format** combo (above) is set to; the Metavision header's `% format` line tracks it automatically (`EVT2`, `EVT21`, …). To get *decoded* events from a recording, decode it later with `--decode` (see [Decoding Recordings Offline](#decoding-recordings-offline)), or use the **Save** button for a snapshot of the current view in CSV + NumPy.

| File | Extension | Description |
|---|---|---|
| **Metavision RAW** *(default)* | `.raw` | ASCII header + raw event stream. Opens directly in Prophesee's [metavision_viewer](https://github.com/prophesee-ai/openeb) and the rest of the OpenEB / Metavision SDK toolchain. |
| **Verbatim** | `.bin` | Bit-for-bit copy of what the sensor emitted — no header, no metadata. Smallest, most predictable file; pair with the offline decoder below. |

A recording is also closed automatically on Disconnect and on window close so the file is never left half-written.

- `events_<timestamp>.raw` — Metavision RAW (see **Metavision RAW File Format** below).
- `events_<timestamp>_raw.bin` — verbatim byte stream (see **Verbatim File Format** below).

These files are excluded from git via `.gitignore`.

### Statistics

Live event throughput, updated at 5 Hz:

| Field | Description |
|-------|-------------|
| Events/batch | Raw event count in the most recent batch |
| Rate | Exponential moving average event rate (events/sec) |
| Bandwidth | EMA data rate (MB/s) |
| Density | Events per MB (rate ÷ bandwidth) — encoding efficiency; higher for denser formats like EVT3.0. Raw MB/s is fixed-frame-bound, so this is where format differences show up. |
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

**Raw mode** (`genx320_raw_event_mode_streaming_on_cam.py`) streams the sensor's unprocessed words and decodes them on the PC, so far less data crosses USB than processed mode's 12 bytes/event. The **Format** combo selects the encoding (EVT2.1 by default — the sensor's native vectorized format, recommended by Prophesee); see **Event Stream Formats** above for the per-format trade-offs and the **Verbatim File Format** section below for the byte layouts. The decoded output is identical regardless of format.

## Metavision RAW File Format

`events_<timestamp>.raw` (selected when **File = Metavision RAW**) is the Prophesee event stream wrapped in the ASCII header expected by [Prophesee's metavision_viewer / OpenEB SDK](https://github.com/prophesee-ai/openeb). Open the file directly in `metavision_viewer` or load it with any OpenEB-compatible decoder.

The file begins with this header (ASCII text, terminated by `% end\n`). The `% format` and `% evt` tokens track the selected event format (`EVT2`/`2.0`, `EVT21`/`2.1`, or `EVT3`/`3.0`):

```
% camera_integrator_name OpenMV
% date YYYY-MM-DD HH:MM:SS
% evt 3.0
% format EVT3;height=320;width=320
% geometry 320x320
% integrator_name OpenMV
% plugin_integrator_name OpenMV
% end
```

Immediately after the `% end` line, the file body is the **same verbatim byte stream** described in the next section — no padding, no per-event prefix. (AER has no Metavision RAW representation, so it is always recorded as a verbatim `.bin`.)

## Verbatim File Format

`events_<timestamp>_raw.bin` (selected when **File = Verbatim**) is a header-less dump of the sensor's stream, exactly as the GenX320 emitted it — the same bytes that follow the `% end` marker in a Metavision `.raw`. The word size and layout depend on the recorded **Format**:

| Format | Word size | Layout |
|--------|-----------|--------|
| EVT2.0 | 4 bytes (32-bit LE) | `type = word>>28`. CD: `ts=(word>>22)&0x3F`, `x=(word>>11)&0x7FF`, `y=word&0x7FF`, polarity = type. `0x8` TIME_HIGH, `0xA` TRIGGER. |
| EVT2.1 | 8 bytes (two 32-bit LE) | High word = an EVT2.0 word; low word = a 32-bit `valid` bitmask. CD events are vectorized — x is aligned to 32 and bit *n* flags an event at (x+n, y). |
| EVT3.0 | 2 bytes (16-bit LE) | Compressed and stateful (`type = word>>12`: ADDR_Y / ADDR_X / VECT_BASE / VECT_12 / VECT_8 / TIME_LOW / TIME_HIGH / TRIGGER). Decoder keeps running y, x, polarity and time. |
| AER | 3 bytes (19-bit LE) | CD only, no time. `val = b0 \| b1<<8 \| b2<<16`; `y=val&0x1FF`, `x=(val>>9)&0x1FF`, polarity=`(val>>18)&1`. Each capture frame is padded — decode per frame and drop the tail. |

Full bit-level field definitions for every format are in the header comment of `genx320_raw_event_mode_streaming_on_cam.py`.

Timestamps (EVT formats) are in microseconds: combine the running `time_high` with each event's low bits, then split as `s = t // 1_000_000`, `ms = (t // 1_000) % 1_000`, `us = t % 1_000`. AER carries no timestamps.

## Decoding Recordings Offline

Decode a recorded raw file to events without a camera or GUI, using the same decoders as the live stream:

```
python genx320_event_mode_streaming_on_pc.py --decode events_20260607.raw
python genx320_event_mode_streaming_on_pc.py --decode events_20260607_raw.bin --evt-format EVT30 --npy
```

- Output is **CSV by default** (`type,sec,ms,us,x,y`, the same columns the Save button writes). Add **`--npy`** to write a compact NumPy `.npy` array instead, or `--out PATH` to choose the filename.
- **Metavision RAW** (`.raw`): the format is read automatically from the `% format` / `% evt` header.
- **Verbatim** (`.bin`): pass the recorded format with **`--evt-format`** (the headerless `.bin` doesn't store it). AER recordings are always `.bin` (no Metavision representation) and decode cleanly — the padding bytes are dropped at record time, so no frame size is needed.

To call the decoders directly from your own code, use `decode_raw_events()` (EVT 2.0), `decode_raw_events_evt21()` (EVT 2.1), `decode_raw_events_evt3()` (EVT 3.0), or `decode_raw_events_aer()` (AER) in `genx320_event_mode_streaming_on_pc.py`.

**Processed mode** (`genx320_event_mode_streaming_on_cam.py`) has the camera firmware decode each event before transmission. The event buffer size, CSI FIFO depth, and (in processed mode) event FIFO depth are patched into the script at connect time from the GUI values.
