#!/usr/bin/env python3
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# Thermal overlay calibration GUI for OpenMV cameras on PC.
# Requires: pip install dearpygui numpy pyserial Pillow openmv
#
# Streams RGB565/Grayscale frames from a main camera and a FLIR Lepton
# simultaneously, displays them side by side, and composites them into
# a third image below. A homography computed from 4 point correspondences
# can be used to align the Lepton onto the main camera frame.

import sys
import os
import argparse
import time
import logging
import signal
import threading
import queue
import numpy as np
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
import serial.tools.list_ports
import dearpygui.dearpygui as dpg
from openmv.camera import Camera


COLOR_CAMERA = "\033[32m"
COLOR_RESET  = "\033[0m"

EMA_ALPHA = 0.2
CTRL_WIDTH = 320

# Resolution options sent to the camera script as constants.
MAIN_RES_OPTIONS   = ['QVGA (320×240)', 'VGA (640×480)', 'HD (1280×720)']
LEPTON_RES_OPTIONS = ['QQVGA (160×120)', 'QVGA (320×240)', 'VGA (640×480)']
PIXFMT_OPTIONS     = ['RGB565', 'GRAYSCALE']
PALETTE_OPTIONS    = ['IRONBOW', 'RAINBOW']

MAIN_RES_MAP = {
    'QVGA (320×240)': 'csi.QVGA',
    'VGA (640×480)':  'csi.VGA',
    'HD (1280×720)':  'csi.HD',
}
LEPTON_RES_MAP = {
    'QQVGA (160×120)': 'csi.QQVGA',
    'QVGA (320×240)':  'csi.QVGA',
    'VGA (640×480)':   'csi.VGA',
}
PIXFMT_MAP = {
    'RGB565':    'csi.RGB565',
    'GRAYSCALE': 'csi.GRAYSCALE',
}
PALETTE_MAP = {
    'IRONBOW': 'image.PALETTE_IRONBOW',
    'RAINBOW': 'image.PALETTE_RAINBOW',
}

# Tags
MAIN_TEX_TAG    = "main_tex"
LEPTON_TEX_TAG  = "lepton_tex"
COMP_TEX_TAG    = "comp_tex"
TEX_REG_TAG     = "tex_reg"


# ---------------------------------------------------------------------------
# RGB565 → RGB888 conversion (vectorized)
# ---------------------------------------------------------------------------

def rgb565_to_rgb888(data, w, h):
    """Convert a bytes-like object of RGB565 pixels to (H,W,3) uint8."""
    words = np.frombuffer(data, dtype='<u2').reshape(h, w)
    r = ((words >> 11) & 0x1F) * 255 // 31
    g = ((words >>  5) & 0x3F) * 255 // 63
    b = ( words        & 0x1F) * 255 // 31
    return np.stack([r, g, b], axis=2).astype(np.uint8)


def gray_to_rgb888(data, w, h):
    """Convert a bytes-like object of 8-bit grayscale to (H,W,3) uint8."""
    gray = np.frombuffer(data, dtype=np.uint8).reshape(h, w)
    return np.stack([gray, gray, gray], axis=2)


def to_dpg_rgba(rgb888):
    """Convert (H,W,3) uint8 RGB to flat float32 RGBA for DearPyGui texture."""
    h, w = rgb888.shape[:2]
    rgba = np.empty((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = rgb888.astype(np.float32) * (1.0 / 255.0)
    rgba[:, :,  3] = 1.0
    return rgba.ravel()


# ---------------------------------------------------------------------------
# Script patching
# ---------------------------------------------------------------------------

def patch_script(script, main_res, lepton_res, main_pixfmt, lepton_pixfmt, lepton_palette):
    """Patch cam script constants before exec.

    Replaces MAIN_FRAME_SIZE, LEPTON_FRAME_SIZE, MAIN_PIXFORMAT, LEPTON_PIXFORMAT,
    and LEPTON_PALETTE constant assignments.
    On macOS/Linux also renames 'def read' → 'def readp'.
    """
    import re
    main_csi    = MAIN_RES_MAP[main_res]
    lepton_csi  = LEPTON_RES_MAP[lepton_res]
    main_fmt    = PIXFMT_MAP[main_pixfmt]
    lepton_fmt  = PIXFMT_MAP[lepton_pixfmt]
    palette     = PALETTE_MAP[lepton_palette]

    script = re.sub(r'MAIN_FRAME_SIZE\s*=\s*\S+',
                    f'MAIN_FRAME_SIZE = {main_csi}', script)
    script = re.sub(r'LEPTON_FRAME_SIZE\s*=\s*\S+',
                    f'LEPTON_FRAME_SIZE = {lepton_csi}', script)
    script = re.sub(r'MAIN_PIXFORMAT\s*=\s*\S+',
                    f'MAIN_PIXFORMAT = {main_fmt}', script)
    script = re.sub(r'LEPTON_PIXFORMAT\s*=\s*\S+',
                    f'LEPTON_PIXFORMAT = {lepton_fmt}', script)
    script = re.sub(r'LEPTON_PALETTE\s*=\s*\S+',
                    f'LEPTON_PALETTE = {palette}', script)

    if sys.platform != 'win32':
        script = script.replace('def read(self, offset, size):',
                                'def readp(self, offset, size):')
    return script


# ---------------------------------------------------------------------------
# Camera worker
# ---------------------------------------------------------------------------

def camera_worker(args, state_lock, state, frame_q, stop_evt):
    try:
        with Camera(
            args.port, baudrate=args.baudrate, crc=args.crc, seq=args.seq,
            ack=args.ack, events=args.events, timeout=args.timeout,
            max_retry=args.max_retry, max_payload=args.max_payload,
            drop_rate=args.drop_rate,
        ) as camera:
            logging.info(f"Connected to OpenMV on {args.port}")
            camera.stop()
            time.sleep(0.5)

            with open(args.script) as f:
                script = f.read()
            with state_lock:
                main_res       = state['main_res']
                lepton_res     = state['lepton_res']
                main_pixfmt    = state['main_pixfmt']
                lepton_pixfmt  = state['lepton_pixfmt']
                lepton_palette = state['lepton_palette']
            script = patch_script(script, main_res, lepton_res,
                                  main_pixfmt, lepton_pixfmt, lepton_palette)
            logging.debug(f"Patched script: main={main_res}/{main_pixfmt} "
                          f"lepton={lepton_res}/{lepton_pixfmt}/{lepton_palette} "
                          f"readp={'yes' if sys.platform != 'win32' else 'no'}")
            camera.exec(script)
            logging.info("Script running, streaming frames...")

            start_time  = time.perf_counter()
            last_time   = start_time
            total_bytes = 0
            mbps_ema    = 0.0
            fps_ema     = 0.0
            frame_count = 0

            while not stop_evt.is_set():
                status = camera.read_status()

                if not args.quiet and status and status.get('stdout'):
                    if text := camera.read_stdout():
                        print(f"{COLOR_CAMERA}{text}{COLOR_RESET}", end='')

                has_main   = camera.has_channel('main')   and status and status.get('main')
                has_lepton = camera.has_channel('lepton') and status and status.get('lepton')

                if not has_main and not has_lepton:
                    time.sleep(0.005)
                    continue

                main_frame   = None  # (data, w, h)
                lepton_frame = None

                if has_main:
                    sz = camera.channel_size('main')
                    if sz > 0:
                        shape = camera._channel_shape(camera.get_channel(name='main'))
                        if shape and len(shape) >= 2:
                            h, w = shape[0], shape[1]
                            data = camera.channel_read('main', sz)
                            if data:
                                main_frame = (data, w, h)

                if has_lepton:
                    sz = camera.channel_size('lepton')
                    if sz > 0:
                        shape = camera._channel_shape(camera.get_channel(name='lepton'))
                        if shape and len(shape) >= 2:
                            h, w = shape[0], shape[1]
                            data = camera.channel_read('lepton', sz)
                            if data:
                                lepton_frame = (data, w, h)

                if main_frame is None and lepton_frame is None:
                    time.sleep(0.005)
                    continue

                now       = time.perf_counter()
                dt        = max(now - last_time, 1e-6)
                last_time = now

                batch_bytes = ((len(main_frame[0])   if main_frame   else 0) +
                               (len(lepton_frame[0]) if lepton_frame else 0))
                total_bytes += batch_bytes
                frame_count += 1
                elapsed      = now - start_time

                mb_per_sec     = batch_bytes / 1048576.0 / dt
                frames_per_sec = 1.0 / dt

                mbps_ema = (mb_per_sec if mbps_ema == 0.0
                            else mbps_ema * (1 - EMA_ALPHA) + mb_per_sec * EMA_ALPHA)
                fps_ema  = (frames_per_sec if fps_ema == 0.0
                            else fps_ema  * (1 - EMA_ALPHA) + frames_per_sec * EMA_ALPHA)

                stats = {
                    'fps':          fps_ema,
                    'mbps':         mbps_ema,
                    'total_frames': frame_count,
                    'elapsed':      elapsed,
                }

                if frame_q.full():
                    try:
                        frame_q.get_nowait()
                    except queue.Empty:
                        pass
                frame_q.put((main_frame, lepton_frame, stats))

    except Exception as e:
        logging.error(f"Camera error: {e}")
        if args.debug:
            import traceback
            logging.error(traceback.format_exc())


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description='OpenMV thermal overlay calibration GUI')
    p.add_argument('--port',        default=None)
    p.add_argument('--script',      default=None)
    p.add_argument('--baudrate',    default=921600,  type=int)
    p.add_argument('--crc',         default=None,    action=argparse.BooleanOptionalAction)
    p.add_argument('--seq',         default=True,    action=argparse.BooleanOptionalAction)
    p.add_argument('--ack',         default=False,   action=argparse.BooleanOptionalAction)
    p.add_argument('--events',      default=True,    action=argparse.BooleanOptionalAction)
    p.add_argument('--timeout',     default=5.0,     type=float)
    p.add_argument('--max_retry',   default=5,       type=int)
    p.add_argument('--max_payload', default=65536,   type=int)
    p.add_argument('--drop_rate',   default=0,       type=int)
    p.add_argument('--quiet',       default=False,   action='store_true')
    p.add_argument('--debug',       default=False,   action='store_true')
    p.add_argument('--benchmark',   default=False,   action='store_true',
                   help='Headless throughput benchmark — no GUI')
    args = p.parse_args()

    # CRC default: off on Mac/Linux (faster), on on Windows (more reliable)
    if args.crc is None:
        args.crc = sys.platform == 'win32'

    return args


def list_com_ports():
    return sorted(p.device for p in serial.tools.list_ports.comports())


# ---------------------------------------------------------------------------
# Benchmark (headless)
# ---------------------------------------------------------------------------

def run_benchmark(args):
    """Headless throughput benchmark — no GUI, prints stats to terminal."""
    if not args.port:
        ports = list_com_ports()
        if not ports:
            print("No serial ports found. Use --port to specify one.")
            sys.exit(1)
        args.port = ports[0]
        print(f"Auto-selected port: {args.port}")

    if args.script is None:
        args.script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'thermal_overlay_calibration_on_cam.py',
        )

    state_lock = threading.Lock()
    state = {
        'main_res':       'VGA (640×480)',
        'lepton_res':     'QQVGA (160×120)',
        'main_pixfmt':    'RGB565',
        'lepton_pixfmt':  'RGB565',
        'lepton_palette': 'IRONBOW',
    }

    frame_q  = queue.Queue(maxsize=4)
    stop_evt = threading.Event()

    def handle_exit(signum, frame):
        stop_evt.set()

    signal.signal(signal.SIGINT,  handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    t = threading.Thread(
        target=camera_worker,
        args=(args, state_lock, state, frame_q, stop_evt),
        daemon=True,
    )
    t.start()
    print(f"Connecting to {args.port} ...")

    last_print = time.perf_counter()
    while not stop_evt.is_set():
        try:
            _, _, stats = frame_q.get(timeout=0.1)
        except queue.Empty:
            if not t.is_alive():
                print("Camera thread died unexpectedly.")
                break
            continue

        now = time.perf_counter()
        if now - last_print >= 0.1:
            last_print = now
            print(f"elapsed={stats['elapsed']:.1f}s\t"
                  f"fps={stats['fps']:.1f}\t"
                  f"bw={stats['mbps']:.2f} MB/s\t"
                  f"frames={stats['total_frames']:,}")

    stop_evt.set()
    print("\nDone.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args=None):
    if args is None:
        _args = parse_args()
        if _args.benchmark:
            run_benchmark(_args)
            return
        args = _args

    if args.script is None:
        args.script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'thermal_overlay_calibration_on_cam.py',
        )

    logging.basicConfig(
        format="%(relativeCreated)010.3f - %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    state_lock = threading.Lock()
    state = {
        'main_res':       'VGA (640×480)',
        'lepton_res':     'QQVGA (160×120)',
        'main_pixfmt':    'RGB565',
        'lepton_pixfmt':  'RGB565',
        'lepton_palette': 'IRONBOW',
    }

    # Current pixel dimensions — start at 1×1, updated on first received frame
    main_wh   = [1, 1]
    lepton_wh = [1, 1]

    # Overlay alpha: fraction of Lepton blended onto main (0.0–1.0)
    overlay_alpha = [0.5]

    # Homography matrix (3×3 float64), None = identity / no warp
    homography = [None]

    # Point correspondences for homography computation:
    # Each list holds up to 4 (x, y) points in image pixel space
    # pick_state: None | 'main' | 'lepton'
    main_pts   = []
    lepton_pts = []
    pick_state = [None]

    # Latest decoded frames (H,W,3 uint8), kept for save and composite
    last_main_rgb   = [None]
    last_lepton_rgb = [None]

    conn = {'thread': None, 'stop_evt': None}
    frame_q = queue.Queue(maxsize=4)

    signal.signal(signal.SIGINT, lambda *_: dpg.stop_dearpygui())

    # -----------------------------------------------------------------------
    # DPG setup
    # -----------------------------------------------------------------------
    dpg.create_context()

    # Placeholder textures (dark gray)
    def _make_placeholder(w, h):
        buf = np.full(w * h * 4, 0.05, dtype=np.float32)
        buf[3::4] = 1.0
        return buf

    with dpg.texture_registry(tag=TEX_REG_TAG):
        dpg.add_dynamic_texture(1, 1, _make_placeholder(1, 1), tag=MAIN_TEX_TAG)
        dpg.add_dynamic_texture(1, 1, _make_placeholder(1, 1), tag=LEPTON_TEX_TAG)
        dpg.add_dynamic_texture(1, 1, _make_placeholder(1, 1), tag=COMP_TEX_TAG)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _reset_textures(mw, mh, lw, lh):
        for old_tag in (MAIN_TEX_TAG, LEPTON_TEX_TAG, COMP_TEX_TAG):
            dpg.delete_item(old_tag)
            if dpg.does_alias_exist(old_tag):
                dpg.remove_alias(old_tag)
        dpg.add_dynamic_texture(mw, mh, _make_placeholder(mw, mh),
                                tag=MAIN_TEX_TAG,   parent=TEX_REG_TAG)
        dpg.add_dynamic_texture(lw, lh, _make_placeholder(lw, lh),
                                tag=LEPTON_TEX_TAG, parent=TEX_REG_TAG)
        dpg.add_dynamic_texture(mw, mh, _make_placeholder(mw, mh),
                                tag=COMP_TEX_TAG,   parent=TEX_REG_TAG)
        if dpg.does_item_exist("main_img"):
            dpg.configure_item("main_img",   texture_tag=MAIN_TEX_TAG)
            dpg.configure_item("lepton_img", texture_tag=LEPTON_TEX_TAG)
            dpg.configure_item("comp_img",   texture_tag=COMP_TEX_TAG)

    def _do_connect(port):
        args.port = port
        # Reset to 1×1 — actual dimensions come from the camera via _channel_shape
        main_wh[0], main_wh[1]     = 1, 1
        lepton_wh[0], lepton_wh[1] = 1, 1
        _reset_textures(1, 1, 1, 1)
        homography[0] = None
        main_pts.clear()
        lepton_pts.clear()
        pick_state[0] = None

        stop_evt = threading.Event()
        conn['stop_evt'] = stop_evt
        t = threading.Thread(
            target=camera_worker,
            args=(args, state_lock, state, frame_q, stop_evt),
            daemon=True,
        )
        t.start()
        conn['thread'] = t
        dpg.configure_item("connect_btn", label="Disconnect")
        _set_cam_settings_enabled(False)
        logging.info(f"Connecting to {port}...")

    def _do_disconnect():
        if conn['stop_evt']:
            conn['stop_evt'].set()
        conn['thread']   = None
        conn['stop_evt'] = None
        dpg.configure_item("connect_btn", label="Connect")
        _set_cam_settings_enabled(True)

    CAM_SETTING_TAGS = ["main_res_combo", "lepton_res_combo",
                        "main_pixfmt_combo", "lepton_pixfmt_combo", "lepton_palette_combo"]

    def _set_cam_settings_enabled(enabled):
        for tag in CAM_SETTING_TAGS:
            dpg.configure_item(tag, enabled=enabled)

    def _fmt_homography(H):
        rows = []
        for row in H:
            rows.append("  [ " + ",  ".join(f"{v:12.6f}" for v in row) + " ]")
        return "transform =\n[\n" + ",\n".join(rows) + "\n]"

    def _recompute_homography():
        if len(main_pts) == 4 and len(lepton_pts) == 4:
            try:
                import cv2
                src = np.float32(lepton_pts)
                dst = np.float32(main_pts)
                H, _ = cv2.findHomography(src, dst)
                homography[0] = H
                dpg.set_value("pick_status", "Homography computed.")
            except ImportError:
                # Manual least-squares DLT without cv2
                A = []
                lw, lh = lepton_wh
                for (sx, sy), (dx, dy) in zip(lepton_pts, main_pts):
                    A.append([-sx, -sy, -1,  0,   0,  0, sx*dx, sy*dx, dx])
                    A.append([ 0,   0,  0, -sx, -sy, -1, sx*dy, sy*dy, dy])
                A = np.array(A, dtype=np.float64)
                _, _, Vt = np.linalg.svd(A)
                H = Vt[-1].reshape(3, 3)
                H /= H[2, 2]
                homography[0] = H
                dpg.set_value("pick_status", "Homography computed (no cv2).")
            if homography[0] is not None:
                dpg.set_value("homography_text", _fmt_homography(homography[0]))
                dpg.configure_item("save_btn", label="Save Images + Transform")

    def _make_composite():
        main_rgb   = last_main_rgb[0]
        lepton_rgb = last_lepton_rgb[0]
        if main_rgb is None:
            return None
        mw, mh = main_wh
        alpha  = overlay_alpha[0]
        comp   = main_rgb.copy().astype(np.float32)
        if lepton_rgb is not None:
            lh, lw = lepton_rgb.shape[:2]
            H = homography[0]
            if H is not None:
                try:
                    import cv2
                    warped = cv2.warpPerspective(lepton_rgb, H, (mw, mh))
                    # Warp an all-ones mask to find which output pixels are
                    # actually covered by the lepton — avoids false positives
                    # from palette colors that map to exactly (0,0,0).
                    # INTER_NEAREST keeps coverage exactly 0 or 1 so the
                    # mask has a hard edge with no dark fringe.
                    coverage = cv2.warpPerspective(
                        np.ones((lh, lw), dtype=np.float32), H, (mw, mh),
                        flags=cv2.INTER_NEAREST)
                except ImportError:
                    warped = np.array(Image.fromarray(lepton_rgb).resize(
                        (mw, mh), Image.BILINEAR))
                    coverage = np.ones((mh, mw), dtype=np.float32)
                mask = (coverage > 0).reshape(mh, mw, 1).astype(np.float32)
                comp = comp * (1 - mask * alpha) + warped.astype(np.float32) * alpha
            else:
                # Stretch Lepton over main frame — full coverage, no mask needed
                try:
                    import cv2
                    warped = cv2.resize(lepton_rgb, (mw, mh))
                except ImportError:
                    warped = np.array(Image.fromarray(lepton_rgb).resize(
                        (mw, mh), Image.BILINEAR))
                comp = comp * (1 - alpha) + warped.astype(np.float32) * alpha
        return np.clip(comp, 0, 255).astype(np.uint8)

    def _fit_images():
        """Scale all three image widgets to fill the available space."""
        vp_w = max(dpg.get_viewport_width()  - CTRL_WIDTH - 30, 1)
        vp_h = max(dpg.get_viewport_height() - 60, 1)
        mw, mh = main_wh
        lw, lh = lepton_wh

        # Top row: each image gets half the available width as its slot.
        # Scale each to fit its slot, then clamp both to the same display height.
        slot_w   = vp_w / 2
        slot_h   = vp_h * 0.55
        main_s   = min(slot_w / max(mw, 1), slot_h / max(mh, 1))
        lepton_s = min(slot_w / max(lw, 1), slot_h / max(lh, 1))
        target_h = min(mh * main_s, lh * lepton_s)
        main_s   = target_h / max(mh, 1)
        lepton_s = target_h / max(lh, 1)

        # Bottom: composite fills the remaining height
        comp_scale = min(vp_w / max(mw, 1), (vp_h * 0.4) / max(mh, 1))

        for tag, w, h, s in [
            ("main_img",   mw, mh, main_s),
            ("lepton_img", lw, lh, lepton_s),
            ("comp_img",   mw, mh, comp_scale),
        ]:
            dpg.configure_item(tag,
                               width=max(1, int(w * s)),
                               height=max(1, int(h * s)))

        # Center the composite horizontally
        comp_w = max(1, int(mw * comp_scale))
        indent = max(0, (vp_w - comp_w) // 2)
        dpg.configure_item("comp_row", indent=indent)

    # -----------------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------------

    def cb_main_res(s, v, u=None):
        with state_lock:
            state['main_res'] = v

    def cb_lepton_res(s, v, u=None):
        with state_lock:
            state['lepton_res'] = v

    def cb_main_pixfmt(s, v, u=None):
        with state_lock:
            state['main_pixfmt'] = v

    def cb_lepton_pixfmt(s, v, u=None):
        with state_lock:
            state['lepton_pixfmt'] = v
        dpg.configure_item("lepton_palette_group", show=(v == 'RGB565'))

    def cb_lepton_palette(s, v, u=None):
        with state_lock:
            state['lepton_palette'] = v

    def cb_refresh(s=None, v=None, u=None):
        items = list_com_ports()
        dpg.configure_item("port_combo", items=items)
        if items and not dpg.get_value("port_combo"):
            dpg.set_value("port_combo", items[0])

    def cb_connect(s=None, v=None, u=None):
        if conn['thread'] and conn['thread'].is_alive():
            _do_disconnect()
        else:
            port = dpg.get_value("port_combo")
            if not port:
                return
            _do_connect(port)

    def cb_save(s=None, v=None, u=None):
        ts = int(time.time())
        if _PIL_AVAILABLE:
            if last_main_rgb[0] is not None:
                name = f"thermal_main_{ts}.png"
                Image.fromarray(last_main_rgb[0]).save(name)
                print(f"Saved: {name}")
            if last_lepton_rgb[0] is not None:
                name = f"thermal_lepton_{ts}.png"
                Image.fromarray(last_lepton_rgb[0]).save(name)
                print(f"Saved: {name}")
            comp = _make_composite()
            if comp is not None:
                name = f"thermal_composite_{ts}.png"
                Image.fromarray(comp).save(name)
                print(f"Saved: {name}")
        else:
            print("pip install Pillow  to enable image saving.")
        H = homography[0]
        if H is not None:
            name = f"thermal_transform_{ts}.txt"
            with open(name, 'w') as f:
                f.write(_fmt_homography(H) + "\n")
            print(f"Saved: {name}")

    def cb_pick_main(s=None, v=None, u=None):
        main_pts.clear()
        lepton_pts.clear()
        homography[0] = None
        pick_state[0] = 'main'
        dpg.set_value("pick_status", "Click 4 points on the main image.")

    def cb_pick_lepton(s=None, v=None, u=None):
        lepton_pts.clear()
        pick_state[0] = 'lepton'
        dpg.set_value("pick_status",
                      f"Click 4 matching points on the Lepton image "
                      f"({len(main_pts)}/4 main points set).")

    def cb_align_mode(s, v, u=None):
        is_auto = (v == 'Automatic')
        dpg.configure_item("manual_group", show=not is_auto)
        dpg.configure_item("auto_group",   show=is_auto)

    def _find_board(img_rgb, board_size):
        """Try multiple detection methods and preprocessing variants.

        Accepts an RGB image so individual channels can be tried — important
        because different thermal palettes (IRONBOW, RAINBOW, etc.) achieve
        best hot/cold contrast on different channels after grayscale conversion.

        Returns (True, corners) or (False, None).
        """
        import cv2
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))

        def _variants(g):
            enhanced = clahe.apply(g)
            blurred  = cv2.GaussianBlur(enhanced, (0, 0), 3)
            sharp    = cv2.addWeighted(enhanced, 2.0, blurred, -1.0, 0)
            _, otsu     = cv2.threshold(g,     0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            _, otsu_inv = cv2.threshold(255-g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return [enhanced, 255 - enhanced, sharp, 255 - sharp,
                    otsu, otsu_inv, g, 255 - g]

        # Build candidate list: standard grayscale + each individual channel
        gray   = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        r, g, b = img_rgb[:, :, 0], img_rgb[:, :, 1], img_rgb[:, :, 2]
        candidates = (_variants(gray) + _variants(r) +
                      _variants(g)    + _variants(b))

        flags_classic = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE

        # findChessboardCornersSB (OpenCV 4+, saddle-point, most robust)
        if hasattr(cv2, 'findChessboardCornersSB'):
            for img in candidates:
                ret, corners = cv2.findChessboardCornersSB(img, board_size, flags=0)
                if ret:
                    return True, corners

        # Classic detector fallback
        for img in candidates:
            ret, corners = cv2.findChessboardCorners(img, board_size, flags=flags_classic)
            if ret:
                return True, corners

        return False, None

    def cb_auto_detect(s=None, v=None, u=None):
        try:
            import cv2
        except ImportError:
            dpg.set_value("pick_status", "Auto mode requires opencv-python.")
            return
        main_rgb   = last_main_rgb[0]
        lepton_rgb = last_lepton_rgb[0]
        if main_rgb is None or lepton_rgb is None:
            dpg.set_value("pick_status", "No frames available yet.")
            return
        cols = dpg.get_value("board_cols")
        rows = dpg.get_value("board_rows")
        board_size = (cols, rows)

        # Lepton is very low-res; upscale 4× so corners have enough spread
        lh, lw = lepton_rgb.shape[:2]
        SCALE = 4
        lepton_up = cv2.resize(lepton_rgb, (lw * SCALE, lh * SCALE),
                               interpolation=cv2.INTER_CUBIC)

        ret_m, corners_m = _find_board(main_rgb,  board_size)
        ret_l, corners_l = _find_board(lepton_up, board_size)

        if not ret_m and not ret_l:
            dpg.set_value("pick_status",
                          f"Board ({cols}×{rows}) not found in either image. "
                          f"Ensure the full board is visible in both cameras.")
            return
        if not ret_m:
            dpg.set_value("pick_status",
                          f"Board ({cols}×{rows}) not found in main image.")
            return
        if not ret_l:
            dpg.set_value("pick_status",
                          f"Board ({cols}×{rows}) not found in Lepton image.")
            return

        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        gray_m = cv2.cvtColor(main_rgb,  cv2.COLOR_RGB2GRAY)
        gray_l = cv2.cvtColor(lepton_up, cv2.COLOR_RGB2GRAY)
        corners_m = cv2.cornerSubPix(gray_m, corners_m, (11, 11), (-1, -1), criteria)
        corners_l = cv2.cornerSubPix(gray_l, corners_l, (5,  5),  (-1, -1), criteria)

        # Scale Lepton corners back to original pixel space
        corners_l = corners_l / SCALE

        src = corners_l.reshape(-1, 2).astype(np.float32)
        dst = corners_m.reshape(-1, 2).astype(np.float32)
        H, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None:
            dpg.set_value("pick_status", "Homography computation failed.")
            return
        inliers = int(inlier_mask.sum()) if inlier_mask is not None else len(src)
        homography[0] = H
        dpg.set_value("homography_text", _fmt_homography(H))
        dpg.configure_item("save_btn", label="Save Images + Transform")
        dpg.set_value("pick_status",
                      f"Auto: {cols}×{rows} board, {inliers}/{len(src)} inliers.")

    def cb_reset_homography(s=None, v=None, u=None):
        homography[0] = None
        main_pts.clear()
        lepton_pts.clear()
        pick_state[0] = None
        dpg.set_value("pick_status", "Homography reset.")
        dpg.set_value("homography_text", "")
        dpg.configure_item("save_btn", label="Save Images")

    def _handle_image_click(tag, img_wh, pts_list, other_list, this_label):
        """Record a clicked point in image pixel space."""
        mx, my = dpg.get_mouse_pos(local=False)
        try:
            imin = dpg.get_item_rect_min(tag)
            imax = dpg.get_item_rect_max(tag)
        except Exception:
            return
        if not (imin[0] <= mx <= imax[0] and imin[1] <= my <= imax[1]):
            return
        w, h = img_wh
        dw = imax[0] - imin[0]
        dh = imax[1] - imin[1]
        px = int((mx - imin[0]) / max(dw, 1) * w)
        py = int((my - imin[1]) / max(dh, 1) * h)
        pts_list.append((px, py))
        n = len(pts_list)
        if n < 4:
            dpg.set_value("pick_status",
                          f"{n}/4 {this_label} points. Keep clicking.")
        else:
            if len(other_list) == 4:
                _recompute_homography()
            else:
                other_label = 'Lepton' if this_label == 'main' else 'main'
                dpg.set_value("pick_status",
                              f"4 {this_label} points set. Now click 4 {other_label} points.")

    def cb_mouse_click(s=None, v=None, u=None):
        if pick_state[0] == 'main':
            if len(main_pts) < 4:
                _handle_image_click("main_img", main_wh,
                                    main_pts, lepton_pts, 'main')
        elif pick_state[0] == 'lepton':
            if len(lepton_pts) < 4:
                _handle_image_click("lepton_img", lepton_wh,
                                    lepton_pts, main_pts, 'Lepton')

    # -----------------------------------------------------------------------
    # UI layout
    # -----------------------------------------------------------------------
    with dpg.window(tag="main_win", no_scrollbar=True, no_title_bar=True):
        with dpg.table(
            header_row=False, resizable=True,
            borders_innerV=True, tag="layout_table",
            scrollX=False, scrollY=False,
        ):
            dpg.add_table_column(init_width_or_weight=1.0)
            dpg.add_table_column(init_width_or_weight=CTRL_WIDTH, width_fixed=True)

            with dpg.table_row():

                # ── Left: image panels ──────────────────────────────────────
                with dpg.table_cell():
                    # Top row: main + lepton side by side
                    with dpg.group(horizontal=True, tag="top_images"):
                        dpg.add_image(MAIN_TEX_TAG,   tag="main_img",
                                      width=1, height=1)
                        dpg.add_image(LEPTON_TEX_TAG, tag="lepton_img",
                                      width=1, height=1)
                    dpg.add_separator()
                    # Bottom: composite (centered via indent set in _fit_images)
                    with dpg.group(tag="comp_row"):
                        dpg.add_image(COMP_TEX_TAG, tag="comp_img",
                                      width=1, height=1)

                # ── Right: controls ─────────────────────────────────────────
                with dpg.table_cell():
                    with dpg.child_window(width=CTRL_WIDTH, border=False):

                        # Windows performance warning
                        if sys.platform == 'win32':
                            dpg.add_text(
                                "Warning: Windows reduces transfer speed.\n"
                                "Use macOS or Linux for best performance.",
                                color=(255, 200, 0, 255))
                            dpg.add_separator()

                        # ── Connection ──────────────────────────────────────
                        init_ports = list_com_ports()
                        init_port  = args.port or (init_ports[0] if init_ports else "")
                        with dpg.group(horizontal=True):
                            dpg.add_text("Port  ")
                            dpg.add_combo(
                                items=init_ports, default_value=init_port,
                                tag="port_combo", width=CTRL_WIDTH - 90)
                            dpg.add_button(label="Ref", callback=cb_refresh, width=28)

                        # ── Camera Parameters ───────────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Camera Parameters  (applied at connect)")

                        with dpg.group(horizontal=True):
                            dpg.add_text("Main Res ")
                            dpg.add_combo(
                                tag="main_res_combo",
                                items=MAIN_RES_OPTIONS,
                                default_value=state['main_res'],
                                callback=cb_main_res, width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Main Fmt ")
                            dpg.add_combo(
                                tag="main_pixfmt_combo",
                                items=PIXFMT_OPTIONS,
                                default_value=state['main_pixfmt'],
                                callback=cb_main_pixfmt, width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Lepton   ")
                            dpg.add_combo(
                                tag="lepton_res_combo",
                                items=LEPTON_RES_OPTIONS,
                                default_value=state['lepton_res'],
                                callback=cb_lepton_res, width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Lep Fmt  ")
                            dpg.add_combo(
                                tag="lepton_pixfmt_combo",
                                items=PIXFMT_OPTIONS,
                                default_value=state['lepton_pixfmt'],
                                callback=cb_lepton_pixfmt, width=-1)

                        with dpg.group(horizontal=True, tag="lepton_palette_group",
                                       show=True):
                            dpg.add_text("Lep Pal  ")
                            dpg.add_combo(
                                tag="lepton_palette_combo",
                                items=PALETTE_OPTIONS,
                                default_value=state['lepton_palette'],
                                callback=cb_lepton_palette, width=-1)

                        dpg.add_separator()
                        dpg.add_button(label="Connect", tag="connect_btn",
                                       callback=cb_connect, width=-1)

                        # ── Overlay Alpha ───────────────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Overlay Alpha")
                        dpg.add_slider_int(
                            tag="alpha_slider",
                            default_value=int(overlay_alpha[0] * 100),
                            min_value=0, max_value=100,
                            format="%d%%", width=-1,
                            callback=lambda s, v, u=None: overlay_alpha.__setitem__(0, v / 100.0))

                        # ── Overlay Alignment ───────────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Overlay Alignment")

                        with dpg.group(horizontal=True):
                            dpg.add_text("Mode     ")
                            dpg.add_combo(
                                items=["Manual", "Automatic"],
                                default_value="Manual",
                                tag="align_mode_combo",
                                callback=cb_align_mode, width=-1)

                        # Manual mode
                        with dpg.group(tag="manual_group", show=True):
                            dpg.add_text(
                                "Click 4 matching points on each image to "
                                "compute a homography that aligns the Lepton "
                                "onto the main camera frame. Without a "
                                "homography the Lepton is stretched to fill "
                                "the composite.",
                                wrap=CTRL_WIDTH - 10)
                            dpg.add_button(label="Pick Main Points",
                                           callback=cb_pick_main, width=-1)
                            dpg.add_button(label="Pick Lepton Points",
                                           callback=cb_pick_lepton, width=-1)

                        # Automatic mode
                        with dpg.group(tag="auto_group", show=False):
                            dpg.add_text(
                                "Place a heated checkerboard in view of both "
                                "cameras, then click Detect. Inner corners "
                                "(cols × rows) must match the board.",
                                wrap=CTRL_WIDTH - 10)
                            with dpg.group(horizontal=True):
                                dpg.add_text("Cols ")
                                dpg.add_input_int(tag="board_cols",
                                                  default_value=7,
                                                  min_value=2, max_value=20,
                                                  width=-1)
                            with dpg.group(horizontal=True):
                                dpg.add_text("Rows ")
                                dpg.add_input_int(tag="board_rows",
                                                  default_value=6,
                                                  min_value=2, max_value=20,
                                                  width=-1)
                            dpg.add_button(label="Auto Detect",
                                           callback=cb_auto_detect, width=-1)

                        dpg.add_button(label="Reset Homography",
                                       callback=cb_reset_homography, width=-1)

                        dpg.add_text("", tag="pick_status", wrap=CTRL_WIDTH - 10)
                        dpg.add_input_text(
                            tag="homography_text",
                            default_value="",
                            multiline=True, readonly=True,
                            width=-1, height=90)

                        # ── Save ────────────────────────────────────────────
                        dpg.add_separator()
                        dpg.add_button(label="Save Images", tag="save_btn",
                                       callback=cb_save, width=-1)

                        # ── Statistics ──────────────────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Statistics")

                        stat_defs = [
                            ("FPS",           "stat_fps"),
                            ("Bandwidth",     "stat_mbps"),
                            ("Total frames",  "stat_frames"),
                            ("Uptime",        "stat_uptime"),
                        ]
                        for lbl, tag in stat_defs:
                            with dpg.group(horizontal=True):
                                dpg.add_text(f"{lbl:<14}")
                                dpg.add_text("—", tag=tag)

    # Mouse handler for point picking
    with dpg.handler_registry():
        dpg.add_mouse_click_handler(callback=cb_mouse_click)

    dpg.create_viewport(
        title="Thermal Overlay Calibration",
        width=1280, height=800,
        resizable=True,
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main_win", True)
    dpg.add_viewport_drawlist(tag="vp_overlay", front=True)

    if args.port:
        _do_connect(args.port)

    # -----------------------------------------------------------------------
    # Render loop
    # -----------------------------------------------------------------------
    last_stat_time  = time.perf_counter()
    pending_stats   = None

    while dpg.is_dearpygui_running():
        # Drain frame queue
        while True:
            try:
                main_frame, lepton_frame, stats = frame_q.get_nowait()
            except queue.Empty:
                break

            pending_stats = stats

            # Decode and upload main frame
            if main_frame is not None:
                data, w, h = main_frame
                if w != main_wh[0] or h != main_wh[1]:
                    main_wh[0], main_wh[1] = w, h
                    for t in (MAIN_TEX_TAG, COMP_TEX_TAG):
                        dpg.delete_item(t)
                        if dpg.does_alias_exist(t):
                            dpg.remove_alias(t)
                    dpg.add_dynamic_texture(w, h, _make_placeholder(w, h),
                                            tag=MAIN_TEX_TAG, parent=TEX_REG_TAG)
                    dpg.add_dynamic_texture(w, h, _make_placeholder(w, h),
                                            tag=COMP_TEX_TAG, parent=TEX_REG_TAG)
                    dpg.configure_item("main_img", texture_tag=MAIN_TEX_TAG)
                    dpg.configure_item("comp_img", texture_tag=COMP_TEX_TAG)
                expected_rgb565 = w * h * 2
                expected_gray   = w * h
                if len(data) == expected_rgb565:
                    rgb = rgb565_to_rgb888(data, w, h)
                elif len(data) == expected_gray:
                    rgb = gray_to_rgb888(data, w, h)
                else:
                    rgb = None
                if rgb is not None:
                    last_main_rgb[0] = rgb
                    dpg.set_value(MAIN_TEX_TAG, to_dpg_rgba(rgb))

            # Decode and upload lepton frame
            if lepton_frame is not None:
                data, w, h = lepton_frame
                if w != lepton_wh[0] or h != lepton_wh[1]:
                    lepton_wh[0], lepton_wh[1] = w, h
                    dpg.delete_item(LEPTON_TEX_TAG)
                    if dpg.does_alias_exist(LEPTON_TEX_TAG):
                        dpg.remove_alias(LEPTON_TEX_TAG)
                    dpg.add_dynamic_texture(w, h, _make_placeholder(w, h),
                                            tag=LEPTON_TEX_TAG, parent=TEX_REG_TAG)
                    dpg.configure_item("lepton_img", texture_tag=LEPTON_TEX_TAG)
                expected_rgb565 = w * h * 2
                expected_gray   = w * h
                if len(data) == expected_rgb565:
                    rgb = rgb565_to_rgb888(data, w, h)
                elif len(data) == expected_gray:
                    rgb = gray_to_rgb888(data, w, h)
                else:
                    rgb = None
                if rgb is not None:
                    last_lepton_rgb[0] = rgb
                    dpg.set_value(LEPTON_TEX_TAG, to_dpg_rgba(rgb))

            # Update composite
            comp = _make_composite()
            if comp is not None:
                dpg.set_value(COMP_TEX_TAG, to_dpg_rgba(comp))

        # Stats update at ~5 Hz
        now = time.perf_counter()
        if pending_stats and (now - last_stat_time) >= 0.2:
            s = pending_stats
            dpg.set_value("stat_fps",    f"{s['fps']:.1f} fps")
            dpg.set_value("stat_mbps",   f"{s['mbps']:.2f} MB/s")
            dpg.set_value("stat_frames", f"{s['total_frames']:,}")
            dpg.set_value("stat_uptime", f"{s['elapsed']:.1f} s")
            last_stat_time = now

        # Reset UI if the camera thread died unexpectedly (e.g. connection error)
        if conn['thread'] and not conn['thread'].is_alive():
            _do_disconnect()

        _fit_images()

        # Draw point overlays on top of the image widgets
        _PT_COLORS = [
            (0, 255,   0, 255),
            (255, 255,  0, 255),
            (255, 165,  0, 255),
            (255,   0,  0, 255),
        ]
        dpg.delete_item("vp_overlay", children_only=True)
        try:
            for img_tag, pts, wh in [
                ("main_img",   main_pts,   main_wh),
                ("lepton_img", lepton_pts, lepton_wh),
            ]:
                if not pts:
                    continue
                imin = dpg.get_item_rect_min(img_tag)
                imax = dpg.get_item_rect_max(img_tag)
                fw, fh = wh
                dw = imax[0] - imin[0]
                dh = imax[1] - imin[1]
                for i, (px, py) in enumerate(pts):
                    sx = imin[0] + px / max(fw, 1) * dw
                    sy = imin[1] + py / max(fh, 1) * dh
                    col = _PT_COLORS[i % len(_PT_COLORS)]
                    dpg.draw_circle([sx, sy], 8, color=col,
                                    thickness=2, parent="vp_overlay")
                    dpg.draw_text([sx + 10, sy - 8], str(i + 1), size=14,
                                  color=col, parent="vp_overlay")
        except Exception:
            pass

        dpg.render_dearpygui_frame()

    dpg.destroy_context()

    if conn['stop_evt']:
        conn['stop_evt'].set()

    print("\nDone.")


if __name__ == '__main__':
    _args = parse_args()
    if _args.benchmark:
        run_benchmark(_args)
    else:
        main(_args)
