# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# This script pulls color and event images from the camera.
#
# This script is meant to be run using https://github.com/openmv/openmv-python
# from a PC using desktop tools. No visualization or text output is generated
# by this script for OpenMV IDE.

import csi
import protocol
import json

MAIN_PIXFORMAT = csi.RGB565
MAIN_FRAME_SIZE = csi.VGA

# Initialize the main camera.
csi0 = csi.CSI()
csi0.reset(hard=True)
csi0.pixformat(MAIN_PIXFORMAT)
csi0.framesize(MAIN_FRAME_SIZE)
csi0_img = csi0.snapshot()
csi0_img_mv = memoryview(csi0_img.bytearray())
csi0_frame_available = True

# Parse image info from string representation.
csi0_img_info = json.loads(str(csi0_img))
csi0_img_width = csi0_img_info['w']
csi0_img_height = csi0_img_info['h']
csi0_img_size = csi0_img_info['size']

# Initialize the GenX320 in histogram mode — outputs 320x320 grayscale.
csi1 = csi.CSI(cid=csi.GENX320)
csi1.reset(hard=False)
csi1.pixformat(csi.GRAYSCALE)
csi1.framesize((320, 320))
csi1.brightness(128)
csi1.contrast(64)
csi1_img = csi1.snapshot()
csi1_img_mv = memoryview(csi1_img.bytearray())
csi1_frame_available = True

# Parse image info from string representation.
csi1_img_info = json.loads(str(csi1_img))
csi1_img_width = csi1_img_info['w']
csi1_img_height = csi1_img_info['h']
csi1_img_size = csi1_img_info['size']


class MainChannel:
    def size(self):
        return csi0_img_size

    def shape(self):
        return (csi0_img_height, csi0_img_width, csi0_img_size)

    def read(self, offset, size):
        global csi0_frame_available

        if csi0_frame_available:
            end = offset + size
            mv = csi0_img_mv[offset:end]
            if end == csi0_img_size:
                csi0_frame_available = False
            return mv
        return bytes(size)

    def poll(self):
        return csi0_frame_available


class GenX320Channel:
    def size(self):
        return csi1_img_size

    def shape(self):
        return (csi1_img_height, csi1_img_width, csi1_img_size)

    def read(self, offset, size):
        global csi1_frame_available

        if csi1_frame_available:
            end = offset + size
            mv = csi1_img_mv[offset:end]
            if end == csi1_img_size:
                csi1_frame_available = False
            return mv
        return bytes(size)

    def poll(self):
        return csi1_frame_available


protocol.register(name='main',    backend=MainChannel())
protocol.register(name='genx320', backend=GenX320Channel())

while True:
    if not csi0_frame_available:
        csi0_img = csi0.snapshot()
        csi0_img_mv = memoryview(csi0_img.bytearray())
        csi0_frame_available = True

    if not csi1_frame_available:
        csi1_img = csi1.snapshot()
        csi1_img_mv = memoryview(csi1_img.bytearray())
        csi1_frame_available = True
