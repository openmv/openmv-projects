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
import json

# Bayer type string to integer mapping
# Maps camera's internal Bayer naming to integer pattern IDs.
#
# IMPORTANT: Camera's naming differs from OpenCV's by a 180° rotation.
# The PC-side script handles the conversion:
#   Camera BGGR (0) → OpenCV RGGB
#   Camera GBRG (1) → OpenCV GRBG
#   Camera GRBG (2) → OpenCV GBRG
#   Camera RGGB (3) → OpenCV BGGR
BAYER_TYPE_MAP = {
    'bayer_bggr': 0,
    'bayer_gbrg': 1,
    'bayer_grbg': 2,
    'bayer_rggb': 3,
}

# Initialize the sensor.
csi0 = csi.CSI()
csi0.reset()
csi0.pixformat(csi.BAYER)
csi0.framesize(csi.HD)
csi0.framebuffers(1)
img = csi0.snapshot()
img_mv = memoryview(img.bytearray())
frame_available = False

# Parse image info from string representation
img_info = json.loads(str(img))
img_width = img_info['w']
img_height = img_info['h']
img_type = img_info['type']
img_size = img_info['size']
bayer_pattern = BAYER_TYPE_MAP.get(img_type, 0)  # Default to BGGR if unknown

# How to read/write sensor registers in python:
# csi.write_reg(0x00, 0x01)  # Example: Write 0x01 to register 0x00
# reg_value = csi.read_reg(0x00)  # Example: Read register


class BayerChannel:
    def size(self):
        return img_size

    def shape(self):
        return (img_height, img_width, bayer_pattern, img_size)

    def read(self, offset, size):
        global frame_available

        if frame_available:
            end = offset + size
            mv = img_mv[offset:end]
            if end == img_size:
                frame_available = False
            return mv
        return bytes(size) 

    def poll(self):
        return frame_available


protocol.register(name='bayer', backend=BayerChannel())

while True:
    if not frame_available:
        csi0.snapshot()
        frame_available = True
