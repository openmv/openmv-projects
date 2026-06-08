# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# This example shows off using the genx320 raw event camera from Prophesee
# using event streaming mode and sending the data back to the PC.
#
# This script is meant to be run using https://github.com/openmv/openmv-python
# from a PC using desktop tools. No visualization or text output is generated
# by this script for OpenMV IDE.
#
# Output event formats
# =====================
# This script only configures the sensor and streams its raw bytes to the PC;
# all decoding happens PC-side (genx320_event_mode_streaming_on_pc.py). The
# reference below describes the byte stream the PC receives for each EVT_FORMAT.
#
# Conventions: `type` is the top 4 bits of a word. Polarity 0 = OFF (decrease in
# light), 1 = ON (increase). x = pixel column, y = pixel row (both 0–319 on the
# GenX320). Times are in microseconds; combine the running time_high with each
# event's ts/time_low to get the full timestamp, then split it as:
#   ts_s = t_us // 1_000_000;  ts_ms = (t_us // 1_000) % 1_000;  ts_us = t_us % 1_000
#
# -------------------------------------------------------------------------
# EVT2.0  —  32-bit little-endian words (4 bytes/event)   [default]
# -------------------------------------------------------------------------
#   type = word >> 28
#     0x0/0x1  CD event   ts=(word>>22)&0x3F  x=(word>>11)&0x7FF  y=word&0x7FF
#                         polarity = type;  t_us = time_high | ts
#     0x8      TIME_HIGH  time_high = (word & 0x0FFFFFFF) << 6  (track across stream)
#     0xA      TRIGGER    ts=(word>>22)&0x3F  id=(word>>8)&0x1F  value=word&1
#
# -------------------------------------------------------------------------
# EVT2.1  —  64-bit little-endian word pairs (8 bytes/event)
# -------------------------------------------------------------------------
#   Vectorized EVT2.0. The high 32-bit word is an EVT2.0 word (type/ts/x/y); the
#   low 32-bit word is a 32-bit `valid` bitmask. For CD events x is aligned to
#   32 and bit n flags an event at (x+n, y) — up to 32 events per pair.
#   TIME_HIGH and TRIGGER use the high word exactly as in EVT2.0 (low word = 0).
#
# -------------------------------------------------------------------------
# EVT3.0  —  16-bit little-endian words (2 bytes/event)
# -------------------------------------------------------------------------
#   Compressed and stateful: y, x, polarity and time are re-sent only when they
#   change, so the decoder keeps running state.  type = word >> 12
#     0x0  ADDR_Y     y = word & 0x7FF
#     0x2  ADDR_X     pol=(word>>11)&1  x=word&0x7FF       -> CD event at (x, y)
#     0x3  VECT_BASE  pol=(word>>11)&1  base_x=word&0x7FF  (sets vector origin)
#     0x4  VECT_12    12-bit mask vs base_x; bit i -> (base_x+i, y); base_x += 12
#     0x5  VECT_8      8-bit mask vs base_x; bit i -> (base_x+i, y); base_x += 8
#     0x6  TIME_LOW   time_low  = word & 0xFFF   (low 12 bits of 24-bit time)
#     0x8  TIME_HIGH  time_high = word & 0xFFF   (high 12 bits; wraps ~16.7 s)
#     0xA  TRIGGER    id=(word>>8)&0xF  value=word&1
#
# -------------------------------------------------------------------------
# AER  —  19-bit value in 3 little-endian bytes (3 bytes/event)   [legacy]
# -------------------------------------------------------------------------
#   CD events only — no timestamps, no triggers.  val = b0 | b1<<8 | b2<<16
#     y = val & 0x1FF   x = (val >> 9) & 0x1FF   polarity = (val >> 18) & 1
#   Capture frames are padded (the frame size is not a multiple of 3), so decode
#   each frame from its start and drop the few trailing bytes.

import csi
import protocol

# Event buffers arrive from the camera and are stored in
# a fifo buffer before being processed by python.
CSI_FIFO_DEPTH = 8

# Must be a power of two between 1024 and 65536.
EVT_RES = 8192

# Sensor output event format: "EVT20", "EVT21", "EVT30", or "AER" (see the
# format reference at the top of this file). The PC GUI patches this value in
# before exec; the default here matches the GUI default.
EVT_FORMAT = "EVT20"

# Registers that select the output event format. Prophesee registers are 32-bit,
# but csi.__write_reg only writes the low 16 bits (bits >= 16 are unreliable from
# MicroPython) — every field touched below lives in the low 16 bits, so it's safe.
#
#   EDF_CONTROL (0x7044) bits[1:0] — PSEE format: 0=EVT2.0, 1=EVT3.0, 2=EVT2.1
#   CPI_PIPELINE_CONTROL (0x8000) bit 4 (0x10) — output data path: 0=PSEE, 1=AER
_EDF_CONTROL = 0x7044
_CPI_PIPELINE_CONTROL = 0x8000
_EDF_FORMAT_BITS = {"EVT20": 0, "EVT30": 1, "EVT21": 2, "AER": 0}

# Initialize the sensor.
csi0 = csi.CSI(cid=csi.GENX320)
csi0.reset()
csi0.ioctl(csi.IOCTL_GENX320_SET_MODE, csi.GENX320_MODE_EVENT, EVT_RES)

# Apply the requested output event format. SET_MODE configures the sensor for
# legacy EVT2.0, so this runs after it to override the format. The PSEE event
# format (EVT2.0/2.1/3.0) is selected via EDF_CONTROL; AER is a separate output
# data path selected via CPI_PIPELINE_CONTROL bit 4.
csi0.__write_reg(_EDF_CONTROL, _EDF_FORMAT_BITS[EVT_FORMAT])
if EVT_FORMAT == "AER":
    # AER is encoded from EVT2.0 inside the CPI module, so EDF stays EVT2.0 (0)
    # and we just enable the AER output data path. Read-modify-write to keep the
    # configured pipeline bits. The 16-bit write drops bit 16 (part of
    # clk_timeout), but clock gating is disabled in this config so clk_timeout
    # has no effect — the result is functionally identical.
    cpi = csi0.__read_reg(_CPI_PIPELINE_CONTROL)
    csi0.__write_reg(_CPI_PIPELINE_CONTROL, cpi | 0x10)

csi0.framebuffers(CSI_FIFO_DEPTH)

# Grab pointer to the internal FIFO buffer.
events = csi0.ioctl(csi.IOCTL_GENX320_READ_EVENTS_RAW)
events_mv = memoryview(events.bytearray())
frame_available = True


class RawEventChannel:

    def size(self):
        return len(events_mv)

    def shape(self):
        return (len(events_mv), 1)

    def read(self, offset, size):
        global frame_available
        if frame_available:
            end = offset + size
            mv = events_mv[offset:end]
            if end == len(events_mv):
                frame_available = False
            return mv
        return bytes(size)

    def poll(self):
        return frame_available


protocol.register(name='raw_events', backend=RawEventChannel())

while True:
    if not frame_available:
        events = csi0.ioctl(csi.IOCTL_GENX320_READ_EVENTS_RAW)
        events_mv = memoryview(events.bytearray())
        frame_available = True
