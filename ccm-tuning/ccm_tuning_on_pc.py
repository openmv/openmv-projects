#!/usr/bin/env python3
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# This shows off how to get the RAW image for color matrix tuning.
#
# This script is meant to be run using https://github.com/openmv/openmv-python
# from a PC using desktop tools. Statistics on the events being transferred
# are printed to the console.

import sys
import os
import argparse
import time
import logging
import pygame
import signal
import atexit
import numpy as np
import cv2
from openmv.camera import Camera


COLOR_CAMERA = "\033[32m"  # green
COLOR_RESET  = "\033[0m"

# Bayer pattern integer to OpenCV conversion code mapping
#
# IMPORTANT: Camera's Bayer naming differs from OpenCV's by a 180° rotation.
# This mapping converts from camera's pattern IDs to OpenCV's color codes:
#   0 (Camera BGGR) → OpenCV RGGB (COLOR_BAYER_RG2RGB)
#   1 (Camera GBRG) → OpenCV GRBG (COLOR_BAYER_GR2RGB)
#   2 (Camera GRBG) → OpenCV GBRG (COLOR_BAYER_GB2RGB)
#   3 (Camera RGGB) → OpenCV BGGR (COLOR_BAYER_BG2RGB)
BAYER_PATTERNS = {
    0: cv2.COLOR_BAYER_RG2RGB,
    1: cv2.COLOR_BAYER_GR2RGB,
    2: cv2.COLOR_BAYER_GB2RGB,
    3: cv2.COLOR_BAYER_BG2RGB,
}


def cleanup_and_exit():
    """Force cleanup pygame and exit"""
    try:
        pygame.quit()
    except Exception:
        pass
    os._exit(0)


def signal_handler(signum, frame):
    cleanup_and_exit()


def str2bool(v):
    """Convert string to boolean for argparse"""
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--port',
                        action='store', default='/dev/ttyACM0',
                        help='Serial port (default: /dev/ttyACM0)')

    parser.add_argument("--script",
                        action="store", required=True,
                        help="Script file")

    parser.add_argument('--poll', action='store',
                        default=4, type=int,
                        help='Poll rate in ms (default: 4)')

    parser.add_argument('--scale', action='store',
                        default=1, type=int,
                        help='Display scaling factor (default: 1)')

    parser.add_argument('--timeout',
                        action='store', type=float, default=1.0,
                        help='Protocol timeout in seconds')

    parser.add_argument('--debug',
                        action='store_true',
                        help='Enable debug logging')

    parser.add_argument('--baudrate',
                        type=int, default=921600,
                        help='Serial baudrate (default: 921600)')

    parser.add_argument('--crc',
                        type=str2bool, nargs='?', const=True, default=True,
                        help='Enable CRC validation (default: false)')

    parser.add_argument('--seq',
                        type=str2bool, nargs='?', const=True, default=True,
                        help='Enable sequence number validation (default: true)')

    parser.add_argument('--ack',
                        type=str2bool, nargs='?', const=True, default=False,
                        help='Enable packet acknowledgment (default: false)')

    parser.add_argument('--events',
                        type=str2bool, nargs='?', const=True, default=True,
                        help='Enable event notifications (default: true)')

    parser.add_argument('--max-retry',
                        type=int, default=3,
                        help='Maximum number of retries (default: 3)')

    parser.add_argument('--max-payload',
                        type=int, default=4096,
                        help='Maximum payload size in bytes (default: 4096)')

    parser.add_argument('--drop-rate',
                        type=float, default=0.0,
                        help='Packet drop simulation rate (0.0-1.0, default: 0.0)')

    parser.add_argument('--ccm',
                        type=str, default=None,
                        help='Color correction matrix as 9 comma-separated floats '
                             '(row-major 3x3), e.g. "1.5,-0.3,-0.2,-0.2,1.4,-0.2,-0.1,-0.3,1.4"')

    parser.add_argument('--ccm-offsets',
                        type=str, default=None,
                        help='Per-channel R,G,B offsets added after CCM, '
                             'e.g. "-10,5,15"')

    parser.add_argument('--quiet',
                        action='store_true',
                        help='Suppress script output text')

    args = parser.parse_args()

    # Parse CCM if provided
    ccm_matrix = None
    if args.ccm:
        try:
            values = [float(v.strip()) for v in args.ccm.split(',')]
            if len(values) != 9:
                parser.error(f"CCM requires exactly 9 values, got {len(values)}")
            ccm_matrix = np.array(values, dtype=np.float32).reshape(3, 3)
            logging.info(f"Color correction matrix:\n{ccm_matrix}")
        except ValueError as e:
            parser.error(f"Invalid CCM values: {e}")

    # Parse CCM offsets if provided
    ccm_offsets = None
    if args.ccm_offsets:
        try:
            offset_values = [float(v.strip()) for v in args.ccm_offsets.split(',')]
            if len(offset_values) != 3:
                parser.error(f"CCM offsets requires exactly 3 values (R,G,B), got {len(offset_values)}")
            ccm_offsets = np.array(offset_values, dtype=np.float32)
            logging.info(f"CCM offsets (R,G,B): {ccm_offsets}")
        except ValueError as e:
            parser.error(f"Invalid CCM offset values: {e}")

    ccm_enabled = ccm_matrix is not None

    # Register signal handlers for clean exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup_and_exit)

    # Configure logging
    if args.debug:
        log_level = logging.DEBUG
    elif not args.quiet:
        log_level = logging.INFO
    else:
        log_level = logging.ERROR

    logging.basicConfig(
        format="%(relativeCreated)010.3f - %(message)s",
        level=log_level,
    )

    # Load script
    with open(args.script, 'r') as f:
        script = f.read()
    logging.info(f"Loaded script from {args.script}")

    # Initialize pygame
    pygame.init()

    screen = None
    clock = pygame.time.Clock()

    if ccm_matrix is not None:
        pygame.display.set_caption("OpenMV Camera - CCM ON")
    else:
        pygame.display.set_caption("OpenMV Camera")

    try:
        with Camera(args.port, baudrate=args.baudrate, crc=args.crc, seq=args.seq,
                    ack=args.ack, events=args.events,
                    timeout=args.timeout, max_retry=args.max_retry,
                    max_payload=args.max_payload, drop_rate=args.drop_rate) as camera:
            logging.info(f"Connected to OpenMV camera on {args.port}")

            # Stop any running script
            camera.stop()
            time.sleep(0.500)

            # Execute script
            camera.exec(script)
            logging.info("Script executed, starting display...")

            while True:
                # Handle pygame events first to keep UI responsive
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise KeyboardInterrupt
                    if event.type != pygame.KEYDOWN:
                        continue
                    if event.key == pygame.K_ESCAPE:
                        raise KeyboardInterrupt
                    if event.key == pygame.K_c and ccm_matrix is not None:
                        ccm_enabled = not ccm_enabled
                        state = "ON" if ccm_enabled else "OFF"
                        logging.info(f"CCM {state}")
                        pygame.display.set_caption(f"OpenMV Camera - CCM {state}")

                # Read camera status
                status = camera.read_status()

                # Read text output
                if not args.quiet and status and status.get('stdout'):
                    if text := camera.read_stdout():
                        print(f"{COLOR_CAMERA}{text}{COLOR_RESET}", end='')

                if not camera.has_channel('bayer'):
                    time.sleep(0.01)
                    continue

                if not status.get('bayer'):
                    time.sleep(0.01)
                    continue

                size = camera.channel_size('bayer')
                if size <= 0:
                    time.sleep(0.01)
                    continue

                # Get image dimensions and bayer pattern from channel shape
                # shape format: (height, width, bayer_pattern, size)
                shape = camera._channel_shape(camera.get_channel(name="bayer"))
                if not shape or len(shape) < 3:
                    time.sleep(0.01)
                    continue

                h, w, bayer_pattern = shape[0], shape[1], shape[2]

                # Validate bayer pattern
                if bayer_pattern not in BAYER_PATTERNS:
                    logging.error(f"Unknown bayer pattern: {bayer_pattern}")
                    time.sleep(0.01)
                    continue

                # Read raw Bayer data
                data = camera.channel_read('bayer', size)

                # Convert to numpy array and reshape as Bayer image
                bayer_raw = np.frombuffer(data, dtype=np.uint8).reshape(h, w)

                # Debayer using the pattern from shape
                rgb_image = cv2.cvtColor(bayer_raw, BAYER_PATTERNS[bayer_pattern])

                # Apply color correction matrix if enabled
                if ccm_enabled and ccm_matrix is not None:
                    # Reshape to (N, 3), apply 3x3 matrix multiply, add offsets, reshape back
                    pixels = rgb_image.reshape(-1, 3).astype(np.float32)
                    corrected = pixels @ ccm_matrix.T
                    if ccm_offsets is not None:
                        corrected += ccm_offsets
                    rgb_image = np.clip(corrected, 0, 255).astype(np.uint8).reshape(h, w, 3)

                rgb_data = rgb_image.tobytes()

                # Create pygame image from RGB data
                image = pygame.image.frombuffer(rgb_data, (w, h), 'RGB')
                image = pygame.transform.smoothscale(image, (w * args.scale, h * args.scale))

                # Create/resize screen if needed
                if screen is None:
                    screen = pygame.display.set_mode((w * args.scale, h * args.scale), pygame.DOUBLEBUF, 32)

                # Draw frame
                screen.blit(image, (0, 0))

                pygame.display.flip()

                # Control main loop timing
                clock.tick(1000 // args.poll)

    except KeyboardInterrupt:
        logging.info("Interrupted by user")
    except Exception as e:
        logging.error(f"Error: {e}")
        if args.debug:
            import traceback
            logging.error(f"{traceback.format_exc()}")
        sys.exit(1)


if __name__ == '__main__':
    main()
