# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# This shows off how to get the RAW event buffers from the GENX320.
#
# This script is meant to be run using https://github.com/openmv/openmv-python
# from a PC using desktop tools. No visualization or text output is generated
# by this script for OpenMV IDE.

import csi
import protocol

# Event buffers arrive from the camera and are stored in
# a fifo buffer before being processed by python.
CSI_FIFO_DEPTH = 8

# EVT_res: must be a power of two between 1024 and 65536.
event_length = 8192

# Initialize the sensor.
csi0 = csi.CSI(cid=csi.GENX320)
csi0.reset()
csi0.ioctl(csi.IOCTL_GENX320_SET_MODE, csi.GENX320_MODE_EVENT, event_length)
csi0.framebuffers(CSI_FIFO_DEPTH)

# Grab pointer to the internal FIFO buffer.
events = csi0.ioctl(csi.IOCTL_GENX320_READ_EVENTS_RAW)
events_mv = memoryview(events.bytearray())

# Prime DMA system before reading raw events.
# Prime on first size or poll request.
primed = False

# Only grab next frame when current FIFO buffer has been fully streamed.
frame_available = False

class EventChannel:
    def size(self):
        global primed
        if not primed:
            primed = True

        return event_length

    def shape(self):
        return (event_length, 1)

    def read(self, offset, size):
        global frame_available

        if frame_available:
            end = offset + size
            mv = events_mv[offset:end]
            if end == event_length:
                frame_available = False
            return mv
        return bytes(size) 

    def poll(self):
        global primed
        if not primed:
            primed = True
        
        return frame_available


protocol.register(name='events', backend=EventChannel())

while True:
    if not frame_available and primed:
        csi0.ioctl(csi.IOCTL_GENX320_READ_EVENTS_RAW)
        frame_available = True