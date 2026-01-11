#!/usr/bin/env python3
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2025 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# This example shows off using the genx320 event camera from Prophesee
# using event streaming mode and sending the data back to the PC.
#
# This script is meant to be run using https://github.com/openmv/openmv-python
# from a PC using desktop tools. Statistics on the events being transferred
# are printed to the console.

import sys
import os
import argparse
import time
import logging
import signal
import atexit
import numpy as np
from openmv.camera import Camera


COLOR_CAMERA = "\033[32m"  # green
COLOR_RESET  = "\033[0m"


def cleanup_and_exit():
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
                        type=str2bool, nargs='?', const=True, default=False,
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

    parser.add_argument('--quiet',
                        action='store_true',
                        help='Suppress script output text')

    parser.add_argument("--alpha",
                        type=float, default=0.2,
                        help="EMA smoothing factor (0<alpha<=1). Default: 0.2")

    args = parser.parse_args()

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
            logging.info("Script executed...")

            # Stat variables
            start_time = time.perf_counter()
            last_time = start_time
            total_events = 0
            total_bytes = 0
            event_rate_ema = 0.0
            mbps_ema = 0.0

            while True:
                # Read camera status
                status = camera.read_status()

                # Read text output
                if not args.quiet and status and status.get('stdout'):
                    if text := camera.read_stdout():
                        print(f"{COLOR_CAMERA}{text}{COLOR_RESET}", end='')

                if not camera.has_channel('events'):
                    time.sleep(0.01)
                    continue

                if not status.get('events'):
                    time.sleep(0.01)
                    continue

                size = camera.channel_size('events')
                if size <= 0:
                    time.sleep(0.01)
                    continue

                now = time.perf_counter()
                dt = now - last_time
                last_time = now
                if dt <= 0.0:
                    continue

                data = camera.channel_read('events', size)

                # Each event row: 6 x uint16 (little-endian)
                if (len(data) % (6 * 2)) != 0:
                    print(f"Warning: misaligned packet: {len(data)} bytes (not multiple of 12)")
                    continue

                events = np.frombuffer(data, dtype='<u2').reshape(-1, 6)
                # Shape: (event_count, 6)
                # Columns:
                #   [0]  Event type
                #   [1]  Seconds timestamp
                #   [2]  Milliseconds timestamp
                #   [3]  Microseconds timestamp
                #   [4]  X coordinate 0 to 319 for GENX320
                #   [5]  Y coordinate 0 to 319 for GENX320
                event_count = events.shape[0]

                # Instantaneous rates
                events_per_sec = event_count / dt
                mb_per_sec = len(data) / 1048576.0 / dt

                # EMA smoothing
                if event_rate_ema == 0.0:
                    event_rate_ema = events_per_sec
                else:
                    event_rate_ema = event_rate_ema * (1.0 - args.alpha) + events_per_sec * args.alpha

                if mbps_ema == 0.0:
                    mbps_ema = mb_per_sec
                else:
                    mbps_ema = mbps_ema * (1.0 - args.alpha) + mb_per_sec * args.alpha

                total_events += event_count
                total_bytes += len(data)

                elapsed = now - start_time

                logging.info(
                    f"events={event_count:6d}    "
                    f"rate={event_rate_ema:9.0f} ev/s    "
                    f"bw={mbps_ema:6.2f} MB/s    "
                    f"total_events={total_events:10d}    "
                    f"uptime={elapsed:7.1f}s"
                )

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
