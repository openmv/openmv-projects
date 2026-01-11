# This work is licensed under the MIT license.
# Copyright (c) 2013-2025 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# This example shows off using the genx320 event camera from Prophesee
# using event streaming mode and sending the data back to the PC.
#
# This script is meant to be run using https://github.com/openmv/openmv-python
# from a PC using desktop tools. No visualization or text output is generated
# by this script for OpenMV IDE.

import csi
import protocol
# https://micropython-ulab.readthedocs.io/en/latest/index.html
from ulab import numpy as np

# Event buffers arrive from the camera and are stored in
# a fifo buffer before being processed by python.
CSI_FIFO_DEPTH = 8

# Raw events post-processed by python, put into another
# fifo buffer, and then sent to the PC.
EVENT_FIFO_DEPTH = 8

# Stores camera events (8 buffers)
# Shape: (EVT_res, 6) where EVT_res is the event resolution
# EVT_res: must be a power of two between 1024 and 65536.
# Columns:
#   [0]  Event type
#   [1]  Seconds timestamp
#   [2]  Milliseconds timestamp
#   [3]  Microseconds timestamp
#   [4]  X coordinate 0 to 319 for GENX320
#   [5]  Y coordinate 0 to 319 for GENX320
events = [np.zeros((8192, 6), dtype=np.uint16) for i in range(EVENT_FIFO_DEPTH)]
event_counts = [0 for i in range(EVENT_FIFO_DEPTH)]

# ULAB .tobytes() creates shallow copy bytearrays. Wrap these in memoryviews
# for fast slicing without copies.
mv_events = [memoryview(events[i].tobytes()) for i in range(EVENT_FIFO_DEPTH)]

# Event buffer fifo pointers.
wr_index = 0
rd_index = 0


def read_available():
    a = wr_index - rd_index
    if a < 0:
        a += EVENT_FIFO_DEPTH
    return a


def write_available():
    return EVENT_FIFO_DEPTH - 1 - read_available()


# Initialize the sensor.
csi0 = csi.CSI(cid=csi.GENX320)
csi0.reset()
csi0.ioctl(csi.IOCTL_GENX320_SET_MODE, csi.GENX320_MODE_EVENT, events[0].shape[0])
csi0.framebuffers(CSI_FIFO_DEPTH)


class EventChannel:
    def size(self):
        if read_available():
            return event_counts[rd_index] * 12
        return 0

    def readp(self, offset, size):
        global rd_index

        if read_available():
            end = offset + size
            mv = mv_events[rd_index][offset:end]
            # Free the buffer after all data has been read.
            if end == event_counts[rd_index] * 12:
                rd_index = (rd_index + 1) % EVENT_FIFO_DEPTH
            return mv
        return bytes(size)

    def poll(self):
        return read_available()


protocol.register(name='events', backend=EventChannel())

while True:
    if (write_available()):
        # Reads up to 32768 events from the camera.
        # Returns the number of valid events (0-32768) or a negative error code.
        # Note that old events in the buffer are not cleared to save CPU time.
        event_counts[wr_index] = csi0.ioctl(csi.IOCTL_GENX320_READ_EVENTS, events[wr_index])
        wr_index = (wr_index + 1) % EVENT_FIFO_DEPTH
