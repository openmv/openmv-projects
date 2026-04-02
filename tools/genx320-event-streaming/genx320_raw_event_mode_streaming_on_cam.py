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
# Raw EVT 2.0 format
# ------------------
# Each event is a 32-bit little-endian word. The firmware streams these words
# directly from the sensor without any decoding.
#
# Bit layout of each 32-bit word:
#
#   Bits [31:28]  type  (4 bits)  — event type:
#       0x0  TD_LOW       Pixel event — decrease in illumination (negative polarity)
#       0x1  TD_HIGH      Pixel event — increase in illumination (positive polarity)
#       0x8  EV_TIME_HIGH Upper 28 bits of the microsecond timestamp counter
#       0xA  EXT_TRIGGER  External trigger event
#       0xE  OTHERS       Reserved for future extension
#       0xF  CONTINUED    Extra data appended to the previous event
#
# TD_LOW / TD_HIGH pixel event (type == 0x0 or 0x1):
#   Bits [27:22]  ts   (6 bits)  — timestamp low, microseconds (0–63 µs)
#   Bits [21:11]  x    (11 bits) — pixel column  (0–319 for GenX320)
#   Bits [10:0]   y    (11 bits) — pixel row     (0–319 for GenX320)
#
#   Decoding:
#       type = (word >> 28) & 0xF
#       ts   = (word >> 22) & 0x3F
#       x    = (word >> 11) & 0x7FF
#       y    = (word      ) & 0x7FF
#       t_us = time_high | ts          # full microsecond timestamp
#       polarity = type                # 0 = negative, 1 = positive
#
# EV_TIME_HIGH (type == 0x8):
#   Bits [27:0]  time_high (28 bits) — upper bits of timestamp counter
#
#   Decoding:
#       time_high = (word & 0x0FFFFFFF) << 6   # units: microseconds
#
#   Must be tracked across the stream. Combine with ts from pixel events:
#       t_us = time_high | ts
#
#   Split into seconds / milliseconds / microseconds:
#       ts_s  = t_us // 1_000_000
#       ts_ms = (t_us // 1_000) % 1_000
#       ts_us = t_us % 1_000
#
# EXT_TRIGGER (type == 0xA):
#   Bits [27:22]  ts         (6 bits)  — timestamp low, microseconds
#   Bits [12:8]   trigger_id (5 bits)  — trigger channel ID
#   Bit  [0]      polarity   (1 bit)   — 0 = falling, 1 = rising
#
#   Decoding:
#       ts         = (word >> 22) & 0x3F
#       trigger_id = (word >>  8) & 0x1F
#       polarity   = (word      ) & 0x1
#       t_us       = time_high | ts
#
# Parsing pseudocode (Python):
#
#   time_high = 0
#   for word in struct.unpack_from('<' + 'I' * n, buf):
#       event_type = (word >> 28) & 0xF
#       if event_type == 0x8:                        # EV_TIME_HIGH
#           time_high = (word & 0x0FFFFFFF) << 6
#       elif event_type in (0x0, 0x1):               # TD pixel event
#           ts   = (word >> 22) & 0x3F
#           x    = (word >> 11) & 0x7FF
#           y    = (word      ) & 0x7FF
#           t_us = time_high | ts
#           pol  = event_type                        # 0=neg, 1=pos

import csi
import protocol

# Event buffers arrive from the camera and are stored in
# a fifo buffer before being processed by python.
CSI_FIFO_DEPTH = 8

# Must be a power of two between 1024 and 65536.
EVT_RES = 8192

# Initialize the sensor.
csi0 = csi.CSI(cid=csi.GENX320)
csi0.reset()
csi0.ioctl(csi.IOCTL_GENX320_SET_MODE, csi.GENX320_MODE_EVENT, EVT_RES)
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
