# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# This shows off how to get the RAW image for color matrix tuning.
#
# This script is meant to be run using https://github.com/openmv/openmv-python
# from a PC using desktop tools. No visualization or text output is generated
# by this script for OpenMV IDE.

import csi
import protocol

CSI_FIFO_DEPTH = 8

event_length = 8192 * 4

# Initialize the sensor.
csi0 = csi.CSI(cid=csi.GENX320)
csi0.reset()
csi0.ioctl(csi.IOCTL_GENX320_SET_MODE, csi.GENX320_MODE_EVENT, event_length)
csi0.framebuffers(CSI_FIFO_DEPTH)

events = csi0.ioctl(csi.IOCTL_GENX320_READ_EVENTS_RAW)
events_mv = memoryview(events.bytearray())

primed = False
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
    if not frame_available:
        csi0.ioctl(csi.IOCTL_GENX320_READ_EVENTS_RAW)
        frame_available = True