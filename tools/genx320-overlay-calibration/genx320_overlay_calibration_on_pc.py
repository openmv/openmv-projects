#!/usr/bin/env python3
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# GenX320 overlay calibration GUI for OpenMV cameras on PC.
# Requires: pip install dearpygui numpy pyserial Pillow openmv
#
# Streams RGB565/Grayscale frames from the main camera and 320x320 grayscale
# histogram frames from the GenX320 event camera simultaneously, displays them
# side by side, and composites them into a third image below. A homography
# computed from point correspondences aligns the GenX320 onto the main camera
# frame for a pixel-accurate overlay.

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

EMA_ALPHA  = 0.2
CTRL_WIDTH = 320

# Main camera resolution options (GenX320 is always 320x320 grayscale).
MAIN_RES_OPTIONS = ['QVGA (320×240)', 'VGA (640×480)', 'HD (1280×720)']
PIXFMT_OPTIONS   = ['RGB565', 'GRAYSCALE']

MAIN_RES_MAP = {
    'QVGA (320×240)': 'csi.QVGA',
    'VGA (640×480)':  'csi.VGA',
    'HD (1280×720)':  'csi.HD',
}
PIXFMT_MAP = {
    'RGB565':    'csi.RGB565',
    'GRAYSCALE': 'csi.GRAYSCALE',
}

# Tags
MAIN_TEX_TAG   = "main_tex"
GENX320_TEX_TAG = "genx320_tex"
COMP_TEX_TAG   = "comp_tex"
TEX_REG_TAG    = "tex_reg"


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

def patch_script(script, main_res, main_pixfmt):
    """Patch cam script constants before exec.

    Replaces MAIN_FRAME_SIZE and MAIN_PIXFORMAT constant assignments.
    On macOS/Linux also renames 'def read' → 'def readp'.
    """
    import re
    main_csi = MAIN_RES_MAP[main_res]
    main_fmt = PIXFMT_MAP[main_pixfmt]

    script = re.sub(r'MAIN_FRAME_SIZE\s*=\s*\S+',
                    f'MAIN_FRAME_SIZE = {main_csi}', script)
    script = re.sub(r'MAIN_PIXFORMAT\s*=\s*\S+',
                    f'MAIN_PIXFORMAT = {main_fmt}', script)

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
                main_res    = state['main_res']
                main_pixfmt = state['main_pixfmt']
            script = patch_script(script, main_res, main_pixfmt)
            logging.debug(f"Patched script: main={main_res}/{main_pixfmt} "
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
                has_genx320 = camera.has_channel('genx320') and status and status.get('genx320')

                if not has_main and not has_genx320:
                    time.sleep(0.005)
                    continue

                main_frame   = None  # (data, w, h)
                genx320_frame = None

                if has_main:
                    sz = camera.channel_size('main')
                    if sz > 0:
                        shape = camera._channel_shape(camera.get_channel(name='main'))
                        if shape and len(shape) >= 2:
                            h, w = shape[0], shape[1]
                            data = camera.channel_read('main', sz)
                            if data:
                                main_frame = (data, w, h)

                if has_genx320:
                    sz = camera.channel_size('genx320')
                    if sz > 0:
                        shape = camera._channel_shape(camera.get_channel(name='genx320'))
                        if shape and len(shape) >= 2:
                            h, w = shape[0], shape[1]
                            data = camera.channel_read('genx320', sz)
                            if data:
                                genx320_frame = (data, w, h)

                if main_frame is None and genx320_frame is None:
                    time.sleep(0.005)
                    continue

                now       = time.perf_counter()
                dt        = max(now - last_time, 1e-6)
                last_time = now

                batch_bytes = ((len(main_frame[0])    if main_frame    else 0) +
                               (len(genx320_frame[0]) if genx320_frame else 0))
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
                frame_q.put((main_frame, genx320_frame, stats))

    except Exception as e:
        logging.error(f"Camera error: {e}")
        if args.debug:
            import traceback
            logging.error(traceback.format_exc())


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description='OpenMV GenX320 overlay calibration GUI')
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
            'genx320_overlay_calibration_on_cam.py',
        )

    state_lock = threading.Lock()
    state = {
        'main_res':    'VGA (640×480)',
        'main_pixfmt': 'RGB565',
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
            'genx320_overlay_calibration_on_cam.py',
        )

    logging.basicConfig(
        format="%(relativeCreated)010.3f - %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    state_lock = threading.Lock()
    state = {
        'main_res':    'VGA (640×480)',
        'main_pixfmt': 'RGB565',
    }

    # Current pixel dimensions — start at 1×1, updated on first received frame
    main_wh    = [1, 1]
    genx320_wh = [1, 1]

    # Overlay alpha: fraction of GenX320 blended onto main (0.0–1.0)
    overlay_alpha = [0.5]

    # Homography matrix (3×3 float64), None = no warp
    homography = [None]

    # Point correspondences for homography computation
    main_pts    = []
    genx320_pts = []
    pick_state  = [None]

    # Latest decoded frames (H,W,3 uint8)
    last_main_rgb    = [None]
    last_genx320_rgb = [None]

    # Flickering calibration pattern window
    pattern_stop_evt = [None]
    pattern_thread   = [None]
    pattern_root     = [None]

    conn    = {'thread': None, 'stop_evt': None}
    frame_q = queue.Queue(maxsize=4)

    signal.signal(signal.SIGINT, lambda *_: dpg.stop_dearpygui())

    # -----------------------------------------------------------------------
    # DPG setup
    # -----------------------------------------------------------------------
    dpg.create_context()

    def _make_placeholder(w, h):
        buf = np.full(w * h * 4, 0.05, dtype=np.float32)
        buf[3::4] = 1.0
        return buf

    with dpg.texture_registry(tag=TEX_REG_TAG):
        dpg.add_dynamic_texture(1, 1, _make_placeholder(1, 1), tag=MAIN_TEX_TAG)
        dpg.add_dynamic_texture(1, 1, _make_placeholder(1, 1), tag=GENX320_TEX_TAG)
        dpg.add_dynamic_texture(1, 1, _make_placeholder(1, 1), tag=COMP_TEX_TAG)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _reset_textures(mw, mh, gw, gh):
        # split_frame() blocks until the renderer finishes its current frame,
        # so deleting in-use textures here cannot race render_dearpygui_frame.
        dpg.split_frame()
        for old_tag in (MAIN_TEX_TAG, GENX320_TEX_TAG, COMP_TEX_TAG):
            dpg.delete_item(old_tag)
            if dpg.does_alias_exist(old_tag):
                dpg.remove_alias(old_tag)
        dpg.add_dynamic_texture(mw, mh, _make_placeholder(mw, mh),
                                tag=MAIN_TEX_TAG,    parent=TEX_REG_TAG)
        dpg.add_dynamic_texture(gw, gh, _make_placeholder(gw, gh),
                                tag=GENX320_TEX_TAG, parent=TEX_REG_TAG)
        dpg.add_dynamic_texture(mw, mh, _make_placeholder(mw, mh),
                                tag=COMP_TEX_TAG,    parent=TEX_REG_TAG)
        if dpg.does_item_exist("main_img"):
            dpg.configure_item("main_img",    texture_tag=MAIN_TEX_TAG)
            dpg.configure_item("genx320_img", texture_tag=GENX320_TEX_TAG)
            dpg.configure_item("comp_img",    texture_tag=COMP_TEX_TAG)

    def _do_connect(port):
        args.port = port
        main_wh[0], main_wh[1]       = 1, 1
        genx320_wh[0], genx320_wh[1] = 1, 1
        _reset_textures(1, 1, 1, 1)
        homography[0] = None
        main_pts.clear()
        genx320_pts.clear()
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

    CAM_SETTING_TAGS = ["main_res_combo", "main_pixfmt_combo"]

    def _set_cam_settings_enabled(enabled):
        for tag in CAM_SETTING_TAGS:
            dpg.configure_item(tag, enabled=enabled)

    def _fmt_homography(H):
        rows = []
        for row in H:
            rows.append("  [ " + ",  ".join(f"{v:12.6f}" for v in row) + " ]")
        return "transform =\n[\n" + ",\n".join(rows) + "\n]"

    def _recompute_homography():
        if len(main_pts) == 4 and len(genx320_pts) == 4:
            try:
                import cv2
                src = np.float32(genx320_pts)
                dst = np.float32(main_pts)
                H, _ = cv2.findHomography(src, dst)
                homography[0] = H
                dpg.set_value("pick_status", "Homography computed.")
            except ImportError:
                A = []
                for (sx, sy), (dx, dy) in zip(genx320_pts, main_pts):
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
        main_rgb    = last_main_rgb[0]
        genx320_rgb = last_genx320_rgb[0]
        if main_rgb is None:
            return None
        mw, mh = main_wh
        alpha  = overlay_alpha[0]
        comp   = main_rgb.copy().astype(np.float32)
        if genx320_rgb is not None:
            gh, gw = genx320_rgb.shape[:2]
            H = homography[0]
            if H is not None:
                try:
                    import cv2
                    warped = cv2.warpPerspective(genx320_rgb, H, (mw, mh))
                    coverage = cv2.warpPerspective(
                        np.ones((gh, gw), dtype=np.float32), H, (mw, mh),
                        flags=cv2.INTER_NEAREST)
                except ImportError:
                    warped = np.array(Image.fromarray(genx320_rgb).resize(
                        (mw, mh), Image.BILINEAR))
                    coverage = np.ones((mh, mw), dtype=np.float32)
                mask = (coverage > 0).reshape(mh, mw, 1).astype(np.float32)
                comp = comp * (1 - mask * alpha) + warped.astype(np.float32) * alpha
            else:
                try:
                    import cv2
                    warped = cv2.resize(genx320_rgb, (mw, mh))
                except ImportError:
                    warped = np.array(Image.fromarray(genx320_rgb).resize(
                        (mw, mh), Image.BILINEAR))
                comp = comp * (1 - alpha) + warped.astype(np.float32) * alpha
        return np.clip(comp, 0, 255).astype(np.uint8)

    def _fit_images():
        vp_w = max(dpg.get_viewport_width()  - CTRL_WIDTH - 30, 1)
        vp_h = max(dpg.get_viewport_height() - 60, 1)
        mw, mh = main_wh
        gw, gh = genx320_wh

        slot_w   = vp_w / 2
        slot_h   = vp_h * 0.55
        main_s   = min(slot_w / max(mw, 1), slot_h / max(mh, 1))
        genx320_s = min(slot_w / max(gw, 1), slot_h / max(gh, 1))
        target_h  = min(mh * main_s, gh * genx320_s)
        main_s    = target_h / max(mh, 1)
        genx320_s = target_h / max(gh, 1)

        comp_scale = min(vp_w / max(mw, 1), (vp_h * 0.4) / max(mh, 1))

        for tag, w, h, s in [
            ("main_img",    mw, mh, main_s),
            ("genx320_img", gw, gh, genx320_s),
            ("comp_img",    mw, mh, comp_scale),
        ]:
            dpg.configure_item(tag,
                               width=max(1, int(w * s)),
                               height=max(1, int(h * s)))

        comp_w = max(1, int(mw * comp_scale))
        indent = max(0, (vp_w - comp_w) // 2)
        dpg.configure_item("comp_row", indent=indent)

    # -----------------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------------

    def cb_main_res(s, v, u=None):
        with state_lock:
            state['main_res'] = v

    def cb_main_pixfmt(s, v, u=None):
        with state_lock:
            state['main_pixfmt'] = v

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
                name = f"genx320_overlay_main_{ts}.png"
                Image.fromarray(last_main_rgb[0]).save(name)
                print(f"Saved: {name}")
            if last_genx320_rgb[0] is not None:
                name = f"genx320_overlay_genx320_{ts}.png"
                Image.fromarray(last_genx320_rgb[0]).save(name)
                print(f"Saved: {name}")
            comp = _make_composite()
            if comp is not None:
                name = f"genx320_overlay_composite_{ts}.png"
                Image.fromarray(comp).save(name)
                print(f"Saved: {name}")
        else:
            print("pip install Pillow  to enable image saving.")
        H = homography[0]
        if H is not None:
            name = f"genx320_overlay_transform_{ts}.txt"
            with open(name, 'w') as f:
                f.write(_fmt_homography(H) + "\n")
            print(f"Saved: {name}")

    def cb_align_mode(s, v, u=None):
        is_auto = (v == 'Automatic')
        dpg.configure_item("manual_group", show=not is_auto)
        dpg.configure_item("auto_group",   show=is_auto)

    def _find_board_blobs(img_rgb):
        """Blob-grid detection for event camera images.

        Returns (True, corners, grid_shape) or (False, None, None).
        corners is an Nx1x2 array of inner corner points (like findChessboardCorners).
        grid_shape is (inner_cols, inner_rows) for the detected grid.
        """
        import cv2
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

        # Heavy median to denoise event speckle, then Otsu binarize
        med = cv2.medianBlur(gray, 21)
        _, binary = cv2.threshold(med, 0, 255,
                                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find contours of the dark squares (now foreground after INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)

        raw_centers = []
        raw_areas   = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 100:
                continue
            M = cv2.moments(cnt)
            if M['m00'] == 0:
                continue
            raw_centers.append([M['m10'] / M['m00'], M['m01'] / M['m00']])
            raw_areas.append(area)

        if len(raw_areas) < 6:
            return False, None, None

        raw_areas   = np.array(raw_areas)
        raw_centers = np.array(raw_centers, dtype=np.float32)

        # Keep contours whose area is within 3x of the median
        median_area = np.median(raw_areas)
        mask    = (raw_areas > median_area / 3) & (raw_areas < median_area * 3)
        centers = raw_centers[mask]

        if len(centers) < 6:
            return False, None, None

        # Cluster into rows by Y coordinate
        sorted_by_y = centers[centers[:, 1].argsort()]
        y_gaps      = np.diff(sorted_by_y[:, 1])
        sorted_gaps = np.sort(y_gaps)
        gap_diffs   = np.diff(sorted_gaps)

        # Find threshold at the first significant jump in sorted gaps
        threshold = sorted_gaps[-1]
        for i, gd in enumerate(gap_diffs):
            prev_median = np.median(gap_diffs[:max(1, i)])
            if gd > max(prev_median * 5, 10):
                threshold = (sorted_gaps[i] + sorted_gaps[i + 1]) / 2
                break

        rows = []
        current_row = [sorted_by_y[0]]
        for i in range(1, len(sorted_by_y)):
            if sorted_by_y[i, 1] - current_row[-1][1] < threshold:
                current_row.append(sorted_by_y[i])
            else:
                rows.append(np.array(current_row))
                current_row = [sorted_by_y[i]]
        rows.append(np.array(current_row))

        # Sort each row by X
        for i in range(len(rows)):
            rows[i] = rows[i][rows[i][:, 0].argsort()]

        # Keep rows with the most common column count
        col_counts  = [len(r) for r in rows]
        most_common = max(set(col_counts), key=col_counts.count)
        grid_rows   = [r for r in rows if len(r) == most_common]

        if len(grid_rows) < 2 or most_common < 2:
            return False, None, None

        # Inner corners: centroid of each 2x2 block of adjacent blob centers
        inner_corners = []
        for r in range(len(grid_rows) - 1):
            row_corners = []
            for c in range(most_common - 1):
                tl = grid_rows[r][c]
                tr = grid_rows[r][c + 1]
                bl = grid_rows[r + 1][c]
                br = grid_rows[r + 1][c + 1]
                row_corners.append((tl + tr + bl + br) / 4.0)
            inner_corners.append(row_corners)

        n_rows = len(inner_corners)
        n_cols = len(inner_corners[0])
        pts    = np.array([pt for row in inner_corners for pt in row],
                          dtype=np.float32).reshape(-1, 1, 2)

        logging.debug(f"Blob grid: {len(grid_rows)}x{most_common} blobs -> "
                      f"{n_rows}x{n_cols} inner corners")

        return True, pts, (n_cols, n_rows)

    def _run_pattern_window(cols, rows, hz, stop_evt):
        import tkinter as tk

        squares_x = cols + 1
        squares_y = rows + 1
        PHASE_MS  = max(33, int(500 / hz))  # half-period in ms

        root = tk.Tk()
        pattern_root[0] = root
        root.title("Calibration Pattern")
        root.geometry("800x600")
        root.resizable(True, True)
        root.configure(bg='black')

        canvas = tk.Canvas(root, bg='black', highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        phase = [0]

        def draw():
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            canvas.delete('all')
            if phase[0] == 0:
                return  # blank — black canvas bg covers it
            sq_w = w / squares_x
            sq_h = h / squares_y
            for row in range(squares_y):
                for col in range(squares_x):
                    if (row + col) % 2 == 0:
                        x0 = col * sq_w
                        y0 = row * sq_h
                        canvas.create_rectangle(x0, y0, x0 + sq_w, y0 + sq_h,
                                                fill='white', outline='')

        def flip():
            phase[0] ^= 1
            draw()
            root.after(PHASE_MS, flip)

        def check_stop():
            if stop_evt.is_set():
                root.quit()
                return
            root.after(100, check_stop)

        def on_close():
            stop_evt.set()

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.bind('<Escape>', lambda e: on_close())

        root.after(PHASE_MS, flip)
        root.after(100, check_stop)
        root.mainloop()
        root.destroy()

        pattern_root[0] = None
        stop_evt.set()
        if dpg.does_item_exist("pattern_btn"):
            dpg.configure_item("pattern_btn", label="Show Calibration Pattern")

    def cb_show_hide_pattern(s=None, v=None, u=None):
        if pattern_thread[0] is not None and pattern_thread[0].is_alive():
            pattern_stop_evt[0].set()   # signals flip_thread to call root.destroy
            pattern_thread[0]   = None
            pattern_stop_evt[0] = None
            dpg.configure_item("pattern_btn", label="Show Calibration Pattern")
        else:
            cols = dpg.get_value("board_cols")
            rows = dpg.get_value("board_rows")
            hz   = dpg.get_value("pattern_hz")
            stop_evt = threading.Event()
            pattern_stop_evt[0] = stop_evt
            t = threading.Thread(
                target=_run_pattern_window,
                args=(cols, rows, hz, stop_evt),
                daemon=True,
            )
            pattern_thread[0] = t
            t.start()
            dpg.configure_item("pattern_btn", label="Hide Calibration Pattern")

    def cb_auto_detect(s=None, v=None, u=None):
        try:
            import cv2
        except ImportError:
            dpg.set_value("pick_status", "Auto mode requires opencv-python.")
            return
        main_rgb    = last_main_rgb[0]
        genx320_rgb = last_genx320_rgb[0]
        if main_rgb is None or genx320_rgb is None:
            dpg.set_value("pick_status", "No frames available yet.")
            return
        cols = dpg.get_value("board_cols")
        rows = dpg.get_value("board_rows")
        board_size  = (cols, rows)
        gw, gh      = genx320_wh
        SCALE       = 4
        genx320_up  = cv2.resize(genx320_rgb, (gw * SCALE, gh * SCALE),
                                 interpolation=cv2.INTER_CUBIC)

        # Freeze copies for the background thread
        main_snap    = main_rgb.copy()
        genx320_snap = genx320_up.copy()

        dpg.set_value("pick_status", "Running detection pipeline...")

        MAX_ATTEMPTS = 10
        RETRY_SEC    = 0.1

        def _detect():
            import cv2

            for attempt in range(1, MAX_ATTEMPTS + 1):
                # Grab fresh frames each attempt
                if attempt > 1:
                    time.sleep(RETRY_SEC)
                m_rgb = last_main_rgb[0]
                g_rgb = last_genx320_rgb[0]
                if m_rgb is None or g_rgb is None:
                    continue
                m_snap = m_rgb.copy()
                g_snap = cv2.resize(g_rgb, (gw * SCALE, gh * SCALE),
                                    interpolation=cv2.INTER_CUBIC)

                dpg.set_value("pick_status",
                              f"Detecting... attempt {attempt}/{MAX_ATTEMPTS}")

                ret_g, corners_g, grid_g = _find_board_blobs(g_snap)
                if not ret_g:
                    continue

                ret_m, corners_m, grid_m = _find_board_blobs(m_snap)
                if not ret_m:
                    continue

                if grid_g != grid_m:
                    continue

                corners_g_scaled = corners_g / SCALE
                src = corners_g_scaled.reshape(-1, 2).astype(np.float32)
                dst = corners_m.reshape(-1, 2).astype(np.float32)

                H, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
                if H is None:
                    continue

                n = len(src)
                inliers = int(inlier_mask.sum()) if inlier_mask is not None else n
                homography[0] = H
                dpg.set_value("homography_text", _fmt_homography(H))
                dpg.configure_item("save_btn", label="Save Images + Transform")
                dpg.set_value("pick_status",
                              f"Auto: {grid_g[0]}x{grid_g[1]} grid, "
                              f"{inliers}/{n} inliers "
                              f"(attempt {attempt}/{MAX_ATTEMPTS}).")
                return

            dpg.set_value("pick_status",
                          f"Board not found after {MAX_ATTEMPTS} attempts.\n"
                          f"Ensure the pattern is visible to both cameras.")

        threading.Thread(target=_detect, daemon=True).start()

    def cb_pick_main(s=None, v=None, u=None):
        main_pts.clear()
        genx320_pts.clear()
        homography[0] = None
        pick_state[0] = 'main'
        dpg.set_value("pick_status", "Click 4 points on the main image.")

    def cb_pick_genx320(s=None, v=None, u=None):
        genx320_pts.clear()
        pick_state[0] = 'genx320'
        dpg.set_value("pick_status",
                      f"Click 4 matching points on the GenX320 image "
                      f"({len(main_pts)}/4 main points set).")

    def cb_reset_homography(s=None, v=None, u=None):
        homography[0] = None
        main_pts.clear()
        genx320_pts.clear()
        pick_state[0] = None
        dpg.set_value("pick_status", "Homography reset.")
        dpg.set_value("homography_text", "")
        dpg.configure_item("save_btn", label="Save Images")

    def _handle_image_click(tag, img_wh, pts_list, other_list, this_label, other_label):
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
            dpg.set_value("pick_status", f"{n}/4 {this_label} points. Keep clicking.")
        else:
            if len(other_list) == 4:
                _recompute_homography()
            else:
                dpg.set_value("pick_status",
                              f"4 {this_label} points set. Now click 4 {other_label} points.")

    def cb_mouse_click(s=None, v=None, u=None):
        if pick_state[0] == 'main':
            if len(main_pts) < 4:
                _handle_image_click("main_img", main_wh,
                                    main_pts, genx320_pts, 'main', 'GenX320')
        elif pick_state[0] == 'genx320':
            if len(genx320_pts) < 4:
                _handle_image_click("genx320_img", genx320_wh,
                                    genx320_pts, main_pts, 'GenX320', 'main')

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
                    with dpg.group(horizontal=True, tag="top_images"):
                        dpg.add_image(MAIN_TEX_TAG,    tag="main_img",
                                      width=1, height=1)
                        dpg.add_image(GENX320_TEX_TAG, tag="genx320_img",
                                      width=1, height=1)
                    dpg.add_separator()
                    with dpg.group(tag="comp_row"):
                        dpg.add_image(COMP_TEX_TAG, tag="comp_img",
                                      width=1, height=1)
                # ── Right: controls ─────────────────────────────────────────
                with dpg.table_cell():
                    with dpg.child_window(width=CTRL_WIDTH, border=False):

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
                        dpg.add_text("GenX320 is always 320×320 grayscale.",
                                     color=(150, 150, 150, 255))

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

                        # ── Calibration Pattern ─────────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Calibration Pattern")
                        with dpg.group(horizontal=True):
                            dpg.add_text("Cols ")
                            dpg.add_input_int(tag="board_cols",
                                              default_value=7,
                                              min_value=2, max_value=20,
                                              width=-1)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Rows ")
                            dpg.add_input_int(tag="board_rows",
                                              default_value=7,
                                              min_value=2, max_value=20,
                                              width=-1)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Hz   ")
                            dpg.add_input_int(tag="pattern_hz",
                                              default_value=2,
                                              min_value=1, max_value=30,
                                              width=-1)
                        dpg.add_button(label="Show Calibration Pattern",
                                       tag="pattern_btn",
                                       callback=cb_show_hide_pattern, width=-1)

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

                        with dpg.group(tag="manual_group", show=True):
                            dpg.add_text(
                                "Click 4 matching points on each image to "
                                "compute a homography that aligns the GenX320 "
                                "onto the main camera frame.",
                                wrap=CTRL_WIDTH - 10)
                            dpg.add_button(label="Pick Main Points",
                                           callback=cb_pick_main, width=-1)
                            dpg.add_button(label="Pick GenX320 Points",
                                           callback=cb_pick_genx320, width=-1)

                        with dpg.group(tag="auto_group", show=False):
                            dpg.add_text(
                                "Click Auto Detect to find the checkerboard "
                                "in both images. The grid is detected "
                                "automatically.",
                                wrap=CTRL_WIDTH - 10)
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
                                dpg.add_text("-", tag=tag)

    with dpg.handler_registry():
        dpg.add_mouse_click_handler(callback=cb_mouse_click)

    dpg.create_viewport(
        title="GenX320 Overlay Calibration",
        width=1400, height=900,
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
    last_stat_time = time.perf_counter()
    pending_stats  = None

    _PT_COLORS = [
        (0, 255,   0, 255),
        (255, 255,  0, 255),
        (255, 165,  0, 255),
        (255,   0,  0, 255),
    ]

    while dpg.is_dearpygui_running():
        while True:
            try:
                main_frame, genx320_frame, stats = frame_q.get_nowait()
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

            # Decode and upload GenX320 frame (always grayscale)
            if genx320_frame is not None:
                data, w, h = genx320_frame
                if w != genx320_wh[0] or h != genx320_wh[1]:
                    genx320_wh[0], genx320_wh[1] = w, h
                    dpg.delete_item(GENX320_TEX_TAG)
                    if dpg.does_alias_exist(GENX320_TEX_TAG):
                        dpg.remove_alias(GENX320_TEX_TAG)
                    dpg.add_dynamic_texture(w, h, _make_placeholder(w, h),
                                            tag=GENX320_TEX_TAG, parent=TEX_REG_TAG)
                    dpg.configure_item("genx320_img", texture_tag=GENX320_TEX_TAG)
                expected_gray = w * h
                if len(data) == expected_gray:
                    rgb = gray_to_rgb888(data, w, h)
                    last_genx320_rgb[0] = rgb
                    dpg.set_value(GENX320_TEX_TAG, to_dpg_rgba(rgb))

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

        if conn['thread'] and not conn['thread'].is_alive():
            _do_disconnect()

        _fit_images()

        # Draw point overlays
        dpg.delete_item("vp_overlay", children_only=True)
        try:
            for img_tag, pts, wh in [
                ("main_img",    main_pts,    main_wh),
                ("genx320_img", genx320_pts, genx320_wh),
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

    if pattern_stop_evt[0]:
        pattern_stop_evt[0].set()
    if conn['stop_evt']:
        conn['stop_evt'].set()

    print("\nDone.")


if __name__ == '__main__':
    _args = parse_args()
    if _args.benchmark:
        run_benchmark(_args)
    else:
        main(_args)
