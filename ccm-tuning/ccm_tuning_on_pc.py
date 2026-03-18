#!/usr/bin/env python3
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# CCM tuning GUI for OpenMV cameras on PC.
# Requires: pip install dearpygui
#
# Pipeline (mimics N6 ISP):
#   Raw Bayer stats → Debayer → Black Level → AWB → CCM → BCG LUT
#

import sys
import os
import argparse
import time
import logging
import signal
import threading
import queue
import numpy as np
import cv2
import serial.tools.list_ports
import dearpygui.dearpygui as dpg
from openmv.camera import Camera


COLOR_CAMERA = "\033[32m"
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

# For each bayer pattern ID, the (row, col) offset within the 2x2 block for R and B.
# G occupies the other two positions: (r_row, b_col) and (b_row, r_col).
#   Pattern 0 (Camera BGGR → OpenCV RGGB): B G / G R → R at [1,1], B at [0,0]
#   Pattern 1 (Camera GBRG → OpenCV GRBG): G B / R G → R at [1,0], B at [0,1]
#   Pattern 2 (Camera GRBG → OpenCV GBRG): G R / B G → R at [0,1], B at [1,0]
#   Pattern 3 (Camera RGGB → OpenCV BGGR): R G / G B → R at [0,0], B at [1,1]
BAYER_CHANNEL_POS = {
    0: ((1, 1), (0, 0)),
    1: ((1, 0), (0, 1)),
    2: ((0, 1), (1, 0)),
    3: ((0, 0), (1, 1)),
}

CTRL_WIDTH  = 340
TEXTURE_TAG = "cam_tex"
TEX_REG_TAG = "tex_reg"
INIT_W      = 1280
INIT_H      = 800

# X-Rite ColorChecker Classic reference sRGB values (D65, 2-degree observer)
# Row order top→bottom, left→right: Dark Skin … Black
COLORCHECKER_SRGB = np.array([
    [115,  82,  68], [194, 150, 130], [ 98, 122, 157],
    [ 87, 108,  67], [133, 128, 177], [103, 189, 170],
    [214, 126,  44], [ 80,  91, 166], [193,  90,  99],
    [ 94,  60, 108], [157, 188,  64], [224, 163,  46],
    [ 56,  61, 150], [ 70, 148,  73], [175,  54,  60],
    [231, 199,  31], [187,  86, 149], [  8, 133, 161],
    [243, 243, 242], [200, 200, 200], [160, 160, 160],
    [122, 122, 121], [ 85,  85,  85], [ 52,  52,  52],
], dtype=np.float32)


def list_com_ports():
    """Return sorted list of available COM port device strings."""
    return sorted(p.device for p in serial.tools.list_ports.comports())


# ---------------------------------------------------------------------------
# ISP pipeline helpers
# ---------------------------------------------------------------------------

def bayer_channel_stats(bayer_raw, bayer_pattern):
    """Return per-channel (R, G, B) mean values from raw Bayer uint8 image."""
    (r_row, r_col), (b_row, b_col) = BAYER_CHANNEL_POS[bayer_pattern]
    avg_r = float(bayer_raw[r_row::2, r_col::2].mean())
    avg_b = float(bayer_raw[b_row::2, b_col::2].mean())
    # G occupies two off-diagonal planes of equal size — average their means
    avg_g = (float(bayer_raw[r_row::2, b_col::2].mean()) +
             float(bayer_raw[b_row::2, r_col::2].mean())) * 0.5
    return avg_r, avg_g, avg_b


def compute_awb(avg_r, avg_g, avg_b):
    """
    Compute AWB gains and luminance matching the N6 ISP algorithm.
    Luminance: L = R*0.299 + G*0.587 + B*0.114
    Per-channel gain: gain_i = L / max(avg_i, 1)
    Matches stm_isp_update_awb: multi = round(L * 128 / avg), effective gain = L / avg.
    Returns: (gain_r, gain_g, gain_b), luminance
    """
    luminance = avg_r * 0.299 + avg_g * 0.587 + avg_b * 0.114
    return (
        (luminance / max(avg_r, 1.0),
         luminance / max(avg_g, 1.0),
         luminance / max(avg_b, 1.0)),
        luminance,
    )


def build_bcg_lut(brightness, contrast, gamma):
    """
    Build uint8[256] LUT for brightness/contrast/gamma correction.
    Formula (from imlib_update_gamma_table):
      out = clamp(round((pow(i/255, 1/gamma) * contrast + brightness) * 255), 0, 255)
    """
    i = np.arange(256, dtype=np.float64)
    v = (np.power(i / 255.0, 1.0 / gamma) * contrast + brightness) * 255.0
    return np.clip(np.round(v), 0, 255).astype(np.uint8)


def process_frame(bayer_raw, bayer_pattern, state, lut=None):
    """
    Run the full ISP pipeline on one raw Bayer frame.
    Returns (rgb_uint8 HxWx3, stats dict).
    lut: pre-built BCG lookup table; built from state if not provided.
    """
    # Step 1: Raw Bayer stats (before any modification, for display)
    avg_r, avg_g, avg_b = bayer_channel_stats(bayer_raw, bayer_pattern)
    # AWB gains must be computed from BL-corrected means (AWB runs after BL in the N6)
    bl = state['black_level']
    bl_avg_r = max(avg_r - bl[0], 0.0)
    bl_avg_g = max(avg_g - bl[1], 0.0)
    bl_avg_b = max(avg_b - bl[2], 0.0)
    (gain_r, gain_g, gain_b), luminance = compute_awb(bl_avg_r, bl_avg_g, bl_avg_b)

    # Step 2: Debayer
    rgb = cv2.cvtColor(bayer_raw, BAYER_PATTERNS[bayer_pattern])
    px  = rgb.astype(np.float32)

    # Step 3: Black level correction (per channel, clamped)
    if bl[0] or bl[1] or bl[2]:  # skip if all zero
        px[:, :, 0] = np.clip(px[:, :, 0] - bl[0], 0, 255)
        px[:, :, 1] = np.clip(px[:, :, 1] - bl[1], 0, 255)
        px[:, :, 2] = np.clip(px[:, :, 2] - bl[2], 0, 255)

    # Step 4: White balance (auto-computed or manual gains)
    if state['awb_auto']:
        gr, gg, gb = gain_r, gain_g, gain_b
    else:
        gr, gg, gb = state['awb_gains']
    px[:, :, 0] = np.clip(px[:, :, 0] * gr, 0, 255)
    px[:, :, 1] = np.clip(px[:, :, 1] * gg, 0, 255)
    px[:, :, 2] = np.clip(px[:, :, 2] * gb, 0, 255)

    pre_ccm = px.clip(0, 255).astype(np.uint8)

    # Step 5: Color correction matrix
    if state['ccm_enabled']:
        flat = px.reshape(-1, 3) @ state['ccm'].T
        off  = state['ccm_offsets']
        if off[0] or off[1] or off[2]:
            flat += np.array(off, dtype=np.float32)
        px = np.clip(flat, 0, 255).reshape(px.shape)

    # Step 6: Brightness / contrast / gamma LUT
    if lut is None:
        lut = build_bcg_lut(state['brightness'], state['contrast'], state['gamma'])
    out = lut[px.astype(np.uint8)]

    stats = {
        'avg_r':     avg_r,   'avg_g':     avg_g,   'avg_b':  avg_b,
        'luminance': luminance,
        'gain_r':    gain_r,  'gain_g':    gain_g,  'gain_b': gain_b,
    }
    return out, stats, pre_ccm


def compute_homography(src, dst):
    """DLT homography from 4 src points to 4 dst points (each [4,2] float)."""
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([-x, -y, -1,  0,  0,  0, u*x, u*y, u])
        A.append([ 0,  0,  0, -x, -y, -1, v*x, v*y, v])
    _, _, Vt = np.linalg.svd(np.array(A, dtype=np.float64))
    H = Vt[-1].reshape(3, 3)
    return H / H[2, 2]


# ---------------------------------------------------------------------------
# Camera background thread
# ---------------------------------------------------------------------------

def camera_worker(args, state_lock, state, frame_q, stop_evt):
    try:
        # Per-connection caches (reset on each connect)
        lut_key  = None
        lut      = None
        tex_buf  = None   # pre-allocated float32 RGBA, reused every frame
        tex_shape = (0, 0)

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
            camera.exec(script)
            logging.info("Script running, streaming frames...")

            while not stop_evt.is_set():
                status = camera.read_status()

                if not args.quiet and status and status.get('stdout'):
                    if text := camera.read_stdout():
                        print(f"{COLOR_CAMERA}{text}{COLOR_RESET}", end='')

                if not camera.has_channel('bayer') or not status.get('bayer'):
                    time.sleep(0.01)
                    continue

                size = camera.channel_size('bayer')
                if size <= 0:
                    time.sleep(0.01)
                    continue

                shape = camera._channel_shape(camera.get_channel(name="bayer"))
                if not shape or len(shape) < 3:
                    time.sleep(0.01)
                    continue

                h, w, bayer_pat = shape[0], shape[1], shape[2]
                if bayer_pat not in BAYER_PATTERNS:
                    logging.error(f"Unknown bayer pattern: {bayer_pat}")
                    time.sleep(0.01)
                    continue

                # Ensure a full frame is available before reading
                expected = h * w
                if size < expected:
                    time.sleep(0.01)
                    continue

                data = camera.channel_read('bayer', expected)
                if len(data) < expected:
                    time.sleep(0.01)
                    continue
                bayer_raw = np.frombuffer(data, dtype=np.uint8).reshape(h, w)

                # Snapshot state under lock
                with state_lock:
                    s = {
                        'awb_auto':    state['awb_auto'],
                        'awb_gains':   list(state['awb_gains']),
                        'black_level': list(state['black_level']),
                        'ccm_enabled': state['ccm_enabled'],
                        'ccm':         state['ccm'].copy(),
                        'ccm_offsets': list(state['ccm_offsets']),
                        'brightness':  state['brightness'],
                        'contrast':    state['contrast'],
                        'gamma':       state['gamma'],
                    }

                # Rebuild BCG LUT only when parameters change
                new_lut_key = (s['brightness'], s['contrast'], s['gamma'])
                if new_lut_key != lut_key:
                    lut_key = new_lut_key
                    lut = build_bcg_lut(*lut_key)

                rgb_out, stats, pre_ccm = process_frame(bayer_raw, bayer_pat, s, lut)

                # Fill pre-allocated RGBA float32 buffer (avoid per-frame allocation)
                h_out, w_out = rgb_out.shape[:2]
                if (h_out, w_out) != tex_shape:
                    tex_buf   = np.ones((h_out, w_out, 4), dtype=np.float32)
                    tex_shape = (h_out, w_out)
                tex_buf[:, :, :3] = rgb_out * (1.0 / 255.0)
                tex_data = tex_buf.ravel()  # view — no extra allocation

                # Keep only the latest frame
                if frame_q.full():
                    try:
                        frame_q.get_nowait()
                    except queue.Empty:
                        pass
                frame_q.put((w, h, tex_data, stats, rgb_out, pre_ccm))

    except Exception as e:
        logging.error(f"Camera error: {e}")
        if args.debug:
            import traceback
            logging.error(traceback.format_exc())


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    if v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    raise argparse.ArgumentTypeError('Boolean value expected.')


def parse_args():
    p = argparse.ArgumentParser(
        description='OpenMV CCM tuning GUI (mimics N6 ISP pipeline)')

    # Connection
    p.add_argument('--port',        default=None,
                   help='Serial port (auto-selected in GUI if omitted)')
    p.add_argument('--script',      default=None,
                   help='MicroPython script to run on the camera '
                        '(defaults to ccm_tuning_on_cam.py next to this file)')
    p.add_argument('--baudrate',    type=int, default=921600)
    p.add_argument('--timeout',     type=float, default=1.0)
    p.add_argument('--crc',         type=str2bool, nargs='?', const=True, default=True)
    p.add_argument('--seq',         type=str2bool, nargs='?', const=True, default=True)
    p.add_argument('--ack',         type=str2bool, nargs='?', const=True, default=False)
    p.add_argument('--events',      type=str2bool, nargs='?', const=True, default=True)
    p.add_argument('--max-retry',   type=int, default=3)
    p.add_argument('--max-payload', type=int, default=4096)
    p.add_argument('--drop-rate',   type=float, default=0.0)
    p.add_argument('--quiet',       action='store_true',
                   help='Suppress camera stdout')
    p.add_argument('--debug',       action='store_true')

    return p.parse_args()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    if args.script is None:
        args.script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'ccm_tuning_on_cam.py')

    logging.basicConfig(
        format="%(relativeCreated)010.3f - %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    # Default tuning values (all adjustable live in the GUI)
    init_ccm         = np.eye(3, dtype=np.float32)
    init_ccm_offsets = [0.0, 0.0, 0.0]
    init_black_level = [0, 0, 0]

    # Shared mutable state (accessed by both GUI callbacks and camera thread)
    state_lock = threading.Lock()
    # Latest frames for saving/CCM computation
    last_frame     = [None]   # latest post-processed HxWx3 uint8
    last_pre_ccm   = [None]   # latest pre-CCM HxWx3 uint8
    # ColorChecker corner picking state
    cc_state = {'corners': [], 'picking': False}
    state = {
        'awb_auto':    True,
        'awb_gains':   [1.0, 1.0, 1.0],  # used when awb_auto is False
        'black_level': init_black_level,
        'ccm_enabled': True,
        'ccm':         init_ccm,
        'ccm_offsets': init_ccm_offsets,
        'brightness':  0.0,
        'contrast':    1.0,
        'gamma':       2.2,
    }

    frame_q = queue.Queue(maxsize=1)

    # Connection state (mutated by GUI callbacks and checked in render loop)
    conn = {'thread': None, 'stop_evt': None}

    # -----------------------------------------------------------------------
    # Dear PyGui setup
    # -----------------------------------------------------------------------
    dpg.create_context()

    # File dialog for script selection (created before the main window)
    def cb_file_selected(sender, app_data):
        path = app_data.get('file_path_name', '')
        if path:
            args.script = path
            dpg.set_value("script_path", path)

    with dpg.file_dialog(directory_selector=False, show=False,
                         callback=cb_file_selected, tag="file_dialog",
                         width=700, height=450,
                         default_path=os.path.dirname(args.script) if args.script else os.getcwd()):
        dpg.add_file_extension(".py",  color=(100, 255, 100, 255))
        dpg.add_file_extension(".*",   color=(255, 255, 255, 255))

    # Placeholder dark-gray texture shown before camera connects
    placeholder = np.full(INIT_W * INIT_H * 4, 0.05, dtype=np.float32)
    placeholder[3::4] = 1.0
    with dpg.texture_registry(tag=TEX_REG_TAG):
        dpg.add_dynamic_texture(INIT_W, INIT_H, placeholder, tag=TEXTURE_TAG)
    tex_wh = [INIT_W, INIT_H]

    # ---- Callbacks --------------------------------------------------------
    # Generic scalar state key setter
    def cb(key):
        def _cb(s, v, u=None):
            with state_lock:
                state[key] = v
        return _cb

    # List-element setter (for black_level, ccm_offsets)
    def cb_idx(key, idx):
        def _cb(s, v, u=None):
            with state_lock:
                state[key][idx] = v
        return _cb

    # CCM matrix cell setter (user_data = (row, col))
    def cb_ccm_cell(s, v, user_data):
        r, c = user_data
        with state_lock:
            state['ccm'][r, c] = v


    # ---- Connection callbacks ---------------------------------------------
    def do_connect(port):
        args.port     = port
        stop_evt      = threading.Event()
        conn['stop_evt'] = stop_evt
        t = threading.Thread(
            target=camera_worker,
            args=(args, state_lock, state, frame_q, stop_evt),
            daemon=True,
        )
        t.start()
        conn['thread'] = t
        dpg.configure_item("connect_btn", label="Disconnect")
        logging.info(f"Connecting to {port}...")

    def do_disconnect():
        if conn['stop_evt']:
            conn['stop_evt'].set()
        conn['thread'] = None
        conn['stop_evt'] = None
        dpg.configure_item("connect_btn", label="Connect")

    def cb_refresh(s, v, u=None):
        items = list_com_ports()
        dpg.configure_item("port_combo", items=items)
        if items and not dpg.get_value("port_combo"):
            dpg.set_value("port_combo", items[0])

    def cb_connect(s, v, u=None):
        if conn['thread'] and conn['thread'].is_alive():
            do_disconnect()
        else:
            if not args.script:
                return
            port = dpg.get_value("port_combo")
            if not port:
                return
            do_connect(port)

    # ---- ColorChecker / Save callbacks ------------------------------------
    def cb_save(s=None, v=None, u=None):
        frame = last_frame[0]
        if frame is None:
            dpg.set_value("cc_status", "No image captured yet.")
            return
        ts = int(time.time())
        try:
            from PIL import Image
            bmp_name = f"ccm_frame_{ts}.bmp"
            Image.fromarray(frame, 'RGB').save(bmp_name)
            print(f"Saved BMP: {bmp_name}")
        except ImportError:
            print("pip install Pillow  to enable BMP saving.")
        txt_name = f"ccm_params_{ts}.txt"
        with open(txt_name, 'w') as f:
            f.write(dpg.get_value("stat_line") + "\n")
        print(f"Saved text: {txt_name}")

    def cb_pick_cc(s=None, v=None, u=None):
        if cc_state['picking'] or cc_state['corners']:
            # Reset mode
            cc_state['corners'] = []
            cc_state['picking'] = False
            dpg.configure_item("btn_pick_cc", label="Pick ColorChecker")
            dpg.set_value("cc_status", "")
            dpg.delete_item("vp_overlay", children_only=True)
        else:
            # Start picking
            if last_frame[0] is None:
                dpg.set_value("cc_status", "No image captured yet.")
                return
            cc_state['corners'] = []
            cc_state['picking'] = True
            dpg.configure_item("btn_pick_cc", label="Reset")
            dpg.set_value("cc_status", "Click top-left outer corner of card")

    def cb_compute_ccm(s=None, v=None, u=None):
        frame = last_pre_ccm[0]
        corners = cc_state['corners']
        if len(corners) != 4:
            dpg.set_value("cc_status", "Pick 4 corners first.")
            return
        if frame is None:
            dpg.set_value("cc_status", "No frame captured yet.")
            return
        src = np.float64(corners)
        # dst: outer corners of 6-col × 4-row grid
        dst = np.float64([(0, 0), (6, 0), (6, 4), (0, 4)])
        H_fwd = compute_homography(src, dst)
        H_inv = np.linalg.inv(H_fwd)
        fh, fw = frame.shape[:2]
        measured = []
        for row in range(4):
            for col in range(6):
                cx, cy = col + 0.5, row + 0.5
                vals = []
                for dy in np.linspace(-0.3, 0.3, 7):
                    for dx in np.linspace(-0.3, 0.3, 7):
                        pt = H_inv @ np.array([cx+dx, cy+dy, 1.0])
                        px_x = int(round(pt[0] / pt[2]))
                        px_y = int(round(pt[1] / pt[2]))
                        if 0 <= px_x < fw and 0 <= px_y < fh:
                            vals.append(frame[px_y, px_x].astype(np.float64))
                measured.append(np.mean(vals, axis=0) if vals else np.zeros(3))
        measured = np.array(measured, dtype=np.float64)          # [24,3]
        ref_lin  = np.power(COLORCHECKER_SRGB / 255.0, 2.2) * 255.0
        ccm_new, _, _, _ = np.linalg.lstsq(measured, ref_lin, rcond=None)
        ccm_new = ccm_new.T.astype(np.float32)                   # [3,3]
        # Normalize rows to sum to 1 (achromatic constraint)
        for i in range(3):
            ccm_new[i] /= ccm_new[i].sum()
        with state_lock:
            state['ccm'] = ccm_new
        for r in range(3):
            for c in range(3):
                dpg.set_value(f"ccm_{r}{c}", float(ccm_new[r, c]))
        print(f"CCM solved:\n{ccm_new}")
        dpg.set_value("cc_status", "CCM applied.")
        cc_state['picking'] = False
        dpg.configure_item("btn_pick_cc", label="Reset")

    def cb_reset_ccm(s=None, v=None, u=None):
        identity = np.eye(3, dtype=np.float32)
        with state_lock:
            state['ccm'] = identity.copy()
        for r in range(3):
            for c in range(3):
                dpg.set_value(f"ccm_{r}{c}", float(identity[r, c]))
        dpg.set_value("cc_status", "CCM reset to identity.")

    def cb_image_click(s=None, v=None, u=None):
        if not cc_state['picking']:
            return
        if last_frame[0] is None:
            return
        mx, my = dpg.get_mouse_pos(local=False)
        try:
            imin = dpg.get_item_rect_min("cam_img")
            imax = dpg.get_item_rect_max("cam_img")
        except Exception:
            return
        if not (imin[0] <= mx <= imax[0] and imin[1] <= my <= imax[1]):
            return
        fw, fh = tex_wh
        dw = imax[0] - imin[0]
        dh = imax[1] - imin[1]
        fx = int((mx - imin[0]) / dw * fw)
        fy = int((my - imin[1]) / dh * fh)
        cc_state['corners'].append((fx, fy))
        n = len(cc_state['corners'])
        labels = ["top-left", "top-right", "bottom-right", "bottom-left"]
        if n < 4:
            dpg.set_value("cc_status", f"Click {labels[n]} outer corner of card")
        else:
            cc_state['picking'] = False
            dpg.set_value("cc_status", "4 corners set - click Compute CCM")

    # ---- UI layout --------------------------------------------------------
    cell_w = (CTRL_WIDTH - 36) // 3

    with dpg.window(tag="main_win", no_scrollbar=True, no_title_bar=True):
        with dpg.table(
            header_row=False, resizable=True,
            borders_innerV=True, tag="layout_table",
            scrollX=False, scrollY=False,
        ):
            dpg.add_table_column(init_width_or_weight=1.0)          # camera panel
            dpg.add_table_column(init_width_or_weight=CTRL_WIDTH,
                                 width_fixed=True)                   # controls

            with dpg.table_row():

                # ── Left: camera preview + stats bar ──────────────────────
                with dpg.table_cell():
                    dpg.add_image(TEXTURE_TAG, tag="cam_img",
                                  width=INIT_W, height=INIT_H)
                    dpg.add_separator()
                    dpg.add_input_text(
                        tag="stat_line",
                        default_value="Waiting for camera...",
                        multiline=True, readonly=True,
                        width=-1, height=226)

                # ── Right: control panel ───────────────────────────────────
                with dpg.table_cell():
                    with dpg.child_window(width=CTRL_WIDTH, border=False):

                        # ── Connection ─────────────────────────────────────
                        with dpg.group():
                            # Script picker
                            with dpg.group(horizontal=True):
                                dpg.add_text("Script", indent=0)
                                dpg.add_input_text(
                                    tag="script_path", default_value=args.script,
                                    hint="select a .py script...",
                                    width=CTRL_WIDTH - 112, readonly=True)
                                dpg.add_button(
                                    label="...", width=28,
                                    callback=lambda: dpg.show_item("file_dialog"))

                            # Port picker
                            init_ports = list_com_ports()
                            init_port  = args.port or (init_ports[0] if init_ports else "")
                            with dpg.group(horizontal=True):
                                dpg.add_text("Port  ")
                                dpg.add_combo(
                                    items=init_ports,
                                    default_value=init_port,
                                    tag="port_combo",
                                    width=CTRL_WIDTH - 112)
                                dpg.add_button(label="Ref", callback=cb_refresh,
                                               width=28)
                            dpg.add_button(label="Connect", tag="connect_btn",
                                           callback=cb_connect, width=-1)

                        # ── White Balance ──────────────────────────────────
                        dpg.add_separator()
                        with dpg.group():
                            dpg.add_text("Black Level (per channel, 0-255)")
                            for lbl, idx, color in [
                                ("R", 0, (255,  80,  80, 255)),
                                ("G", 1, ( 80, 200,  80, 255)),
                                ("B", 2, ( 80, 130, 255, 255)),
                            ]:
                                with dpg.group(horizontal=True):
                                    dpg.add_text(lbl, color=color)
                                    dpg.add_input_int(
                                        label=f"##{lbl}bl",
                                        default_value=init_black_level[idx],
                                        min_value=0, max_value=255,
                                        min_clamped=True, max_clamped=True,
                                        step=1, step_fast=10,
                                        callback=cb_idx('black_level', idx),
                                        width=-1)

                            dpg.add_separator()
                            dpg.add_text("AWB Gains")

                            def cb_awb_auto(s, v, u=None):
                                with state_lock:
                                    state['awb_auto'] = v
                                    if not v:
                                        # Snapshot current displayed gains so they
                                        # apply immediately without needing an edit
                                        state['awb_gains'] = [
                                            dpg.get_value("wb_gain_r"),
                                            dpg.get_value("wb_gain_g"),
                                            dpg.get_value("wb_gain_b"),
                                        ]
                                ro = v  # readonly when auto
                                for tag in ('wb_gain_r', 'wb_gain_g', 'wb_gain_b'):
                                    dpg.configure_item(tag, readonly=ro)

                            dpg.add_checkbox(label="Auto", default_value=True,
                                             callback=cb_awb_auto, tag="wb_auto_cb")
                            for lbl, idx, color, tag in [
                                ("R", 0, (255,  80,  80, 255), "wb_gain_r"),
                                ("G", 1, ( 80, 200,  80, 255), "wb_gain_g"),
                                ("B", 2, ( 80, 130, 255, 255), "wb_gain_b"),
                            ]:
                                with dpg.group(horizontal=True):
                                    dpg.add_text(lbl, color=color)
                                    dpg.add_input_float(
                                        tag=tag, label=f"##{lbl}wb",
                                        default_value=1.0,
                                        min_value=0.0, max_value=16.0,
                                        min_clamped=True, max_clamped=True,
                                        step=0.001, step_fast=0.1,
                                        format="%.3f",
                                        readonly=True,   # starts in auto mode
                                        callback=cb_idx('awb_gains', idx),
                                        width=-1)

                        # ── Color Correction Matrix ────────────────────────
                        dpg.add_separator()
                        with dpg.group():
                            dpg.add_text("3x3 Matrix  (drag  |  dbl-click to type)")
                            row_colors = [
                                ("R", (255,  80,  80, 255)),
                                ("G", ( 80, 200,  80, 255)),
                                ("B", ( 80, 130, 255, 255)),
                            ]
                            for r, (lbl, color) in enumerate(row_colors):
                                with dpg.group(horizontal=True):
                                    dpg.add_text(lbl, color=color)
                                    for c in range(3):
                                        dpg.add_drag_float(
                                            tag=f"ccm_{r}{c}",
                                            default_value=float(init_ccm[r, c]),
                                            speed=0.005,
                                            min_value=-4.0, max_value=4.0,
                                            format="%.3f",
                                            width=cell_w,
                                            callback=cb_ccm_cell,
                                            user_data=(r, c))

                            dpg.add_separator()
                            dpg.add_text("3x3 Matrix Per-Channel Offsets")
                            for lbl, idx, color in [
                                ("R", 0, (255,  80,  80, 255)),
                                ("G", 1, ( 80, 200,  80, 255)),
                                ("B", 2, ( 80, 130, 255, 255)),
                            ]:
                                with dpg.group(horizontal=True):
                                    dpg.add_text(lbl, color=color)
                                    dpg.add_input_float(
                                        label=f"##{lbl}off",
                                        default_value=init_ccm_offsets[idx],
                                        min_value=-64.0, max_value=64.0,
                                        min_clamped=True, max_clamped=True,
                                        step=0.1, step_fast=1.0,
                                        format="%.2f",
                                        callback=cb_idx('ccm_offsets', idx),
                                        width=-1)

                        # ── Brightness / Contrast / Gamma ──────────────────
                        dpg.add_separator()
                        dpg.add_text("Brightness / Contrast / Gamma")
                        with dpg.group():
                            with dpg.group(horizontal=True):
                                dpg.add_text("Brightness")
                                dpg.add_input_float(
                                    label="##brightness",
                                    default_value=0.0,
                                    min_value=-1.0, max_value=1.0,
                                    min_clamped=True, max_clamped=True,
                                    step=0.01, step_fast=0.1,
                                    format="%.2f",
                                    callback=cb('brightness'), width=-1)
                            with dpg.group(horizontal=True):
                                dpg.add_text("Contrast  ")
                                dpg.add_input_float(
                                    label="##contrast",
                                    default_value=1.0,
                                    min_value=0.0, max_value=3.0,
                                    min_clamped=True, max_clamped=True,
                                    step=0.01, step_fast=0.1,
                                    format="%.2f",
                                    callback=cb('contrast'), width=-1)
                            with dpg.group(horizontal=True):
                                dpg.add_text("Gamma     ")
                                dpg.add_input_float(
                                    label="##gamma",
                                    default_value=2.2,
                                    min_value=0.1,
                                    min_clamped=True,
                                    step=0.01, step_fast=0.1,
                                    format="%.2f",
                                    callback=cb('gamma'), width=-1)

                        # ── ColorChecker / Save ────────────────────────────
                        dpg.add_separator()
                        dpg.add_button(label="Pick ColorChecker",
                                       tag="btn_pick_cc",
                                       callback=cb_pick_cc, width=-1)
                        dpg.add_button(label="Compute CCM", tag="btn_compute_ccm",
                                       callback=cb_compute_ccm, width=-1)
                        dpg.add_button(label="Reset CCM to Identity",
                                       callback=cb_reset_ccm, width=-1)
                        dpg.add_button(label="Save Image + Settings",
                                       tag="btn_save", callback=cb_save,
                                       width=-1)
                        dpg.add_text("", tag="cc_status")

    with dpg.handler_registry():
        dpg.add_mouse_click_handler(button=0, callback=cb_image_click)

    dpg.create_viewport(title="OpenMV CCM Tuner",
                        width=1280, height=900, resizable=True)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main_win", True)

    def handle_exit(signum, frame):
        if conn['stop_evt']:
            conn['stop_evt'].set()
        dpg.stop_dearpygui()

    signal.signal(signal.SIGINT,  handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # Auto-connect if --port (and --script) were supplied on the command line
    if args.port and args.script:
        do_connect(args.port)

    # Track display size to avoid redundant configure_item calls
    disp_wh = [0, 0]

    def fit_image():
        """Resize cam_img to fill the left panel while keeping aspect ratio."""
        fw, fh = tex_wh
        if fw <= 0 or fh <= 0:
            return
        avail_w = max(dpg.get_viewport_width()  - CTRL_WIDTH - 30, 1)
        avail_h = max(dpg.get_viewport_height() - 60, 1)
        scale   = min(avail_w / fw, avail_h / fh)
        dw, dh  = max(int(fw * scale), 1), max(int(fh * scale), 1)
        if [dw, dh] != disp_wh:
            disp_wh[0], disp_wh[1] = dw, dh
            dpg.configure_item("cam_img", width=dw, height=dh)

    dpg.set_viewport_resize_callback(lambda: fit_image())
    fit_image()
    dpg.add_viewport_drawlist(tag="vp_overlay", front=True)

    # -----------------------------------------------------------------------
    # Render loop
    # -----------------------------------------------------------------------
    while dpg.is_dearpygui_running():
        # Detect thread death (e.g. camera unplugged)
        t = conn['thread']
        if t is not None and not t.is_alive():
            conn['thread']   = None
            conn['stop_evt'] = None
            dpg.configure_item("connect_btn", label="Connect")
    
        try:
            w, h, tex_data, stats, rgb_out, pre_ccm = frame_q.get_nowait()
            last_frame[0]   = rgb_out
            last_pre_ccm[0] = pre_ccm

            # Recreate texture when frame dimensions change
            if w != tex_wh[0] or h != tex_wh[1]:
                tex_wh[0], tex_wh[1] = w, h
                dpg.delete_item(TEXTURE_TAG)
                dpg.remove_alias(TEXTURE_TAG)
                dpg.add_dynamic_texture(w, h, tex_data,
                                        tag=TEXTURE_TAG, parent=TEX_REG_TAG)
                dpg.configure_item("cam_img", texture_tag=TEXTURE_TAG)
                fit_image()
            else:
                dpg.set_value(TEXTURE_TAG, tex_data)
                fit_image()

            # Update live parameter display
            s = stats
            with state_lock:
                ccm  = state['ccm'].copy()
                off  = state['ccm_offsets'][:]
                bl   = state['black_level'][:]
                br   = state['brightness']
                co   = state['contrast']
                ga   = state['gamma']
                awb_auto  = state['awb_auto']
                awb_gains = state['awb_gains'][:]
            gr, gg, gb = (s['gain_r'], s['gain_g'], s['gain_b']) if awb_auto else (awb_gains[0], awb_gains[1], awb_gains[2])
            # R/G and B/G ratios use BL-corrected means (illuminant fingerprint)
            bl_r = max(s['avg_r'] - bl[0], 0.0)
            bl_g = max(s['avg_g'] - bl[1], 0.0)
            bl_b = max(s['avg_b'] - bl[2], 0.0)
            avg_g = bl_g if bl_g > 0 else 1.0
            rg = bl_r / avg_g
            bg = bl_b / avg_g
            rs = float(ccm[0].sum())
            gs = float(ccm[1].sum())
            bs = float(ccm[2].sum())
            dpg.set_value("stat_line", "\n".join([
                f"Raw    R {s['avg_r']:6.3f}   G {s['avg_g']:6.3f}   B {s['avg_b']:6.3f}",
                f"       L {s['luminance']:6.3f}  R/G {rg:6.3f}  B/G {bg:6.3f}",
                "",
                f"Black  R {bl[0]:6d}  G {bl[1]:6d}  B {bl[2]:6d}",
                "",
                f"AWB    R {gr:6.3f}  G {gg:6.3f}  B {gb:6.3f}",
                "",
                f"CCM    R: {ccm[0,0]:7.3f}  {ccm[0,1]:7.3f}  {ccm[0,2]:7.3f}",
                f"       G: {ccm[1,0]:7.3f}  {ccm[1,1]:7.3f}  {ccm[1,2]:7.3f}",
                f"       B: {ccm[2,0]:7.3f}  {ccm[2,1]:7.3f}  {ccm[2,2]:7.3f}",
                "",
                f"Sum    R {rs:6.3f}  G {gs:6.3f}  B {bs:6.3f}",
                "",
                f"Offset R {off[0]:6.2f}  G {off[1]:6.2f}  B {off[2]:6.2f}",
                "",
                f"BCG    B {br:6.3f}  C {co:6.3f}  G {ga:6.3f}",
            ]))

            # Push auto-computed gains into the gain fields
            if dpg.get_value("wb_auto_cb"):
                dpg.set_value("wb_gain_r", s['gain_r'])
                dpg.set_value("wb_gain_g", s['gain_g'])
                dpg.set_value("wb_gain_b", s['gain_b'])

        except queue.Empty:
            pass

        # Draw ColorChecker corner overlays (runs every frame, camera or not)
        dpg.delete_item("vp_overlay", children_only=True)
        if cc_state['corners']:
            try:
                imin = dpg.get_item_rect_min("cam_img")
                imax = dpg.get_item_rect_max("cam_img")
                fw, fh = tex_wh
                dw = imax[0] - imin[0]
                dh = imax[1] - imin[1]
                labels = ["TL", "TR", "BR", "BL"]
                colors = [(0,255,0,255),(255,255,0,255),(255,165,0,255),(255,0,0,255)]
                for i, (fx, fy) in enumerate(cc_state['corners']):
                    sx = imin[0] + fx / fw * dw
                    sy = imin[1] + fy / fh * dh
                    dpg.draw_circle([sx, sy], 8, color=colors[i],
                                    thickness=2, parent="vp_overlay")
                    dpg.draw_text([sx+10, sy-8], labels[i], size=14,
                                  color=colors[i], parent="vp_overlay")
                if len(cc_state['corners']) == 4:
                    # Draw the grid lines across all 4 corners
                    src = np.float64(cc_state['corners'])
                    dst = np.float64([(0,0),(6,0),(6,4),(0,4)])
                    H_inv = np.linalg.inv(compute_homography(src, dst))
                    def warp(cx, cy):
                        pt = H_inv @ np.array([cx, cy, 1.0])
                        gx = pt[0]/pt[2]; gy = pt[1]/pt[2]
                        return [imin[0]+gx/fw*dw, imin[1]+gy/fh*dh]
                    for r in range(5):  # 5 lines = 4 rows of patches
                        dpg.draw_line(warp(0, r), warp(6, r),
                                      color=(0,255,0,128), parent="vp_overlay")
                    for c in range(7):  # 7 lines = 6 columns of patches
                        dpg.draw_line(warp(c, 0), warp(c, 4),
                                      color=(0,255,0,128), parent="vp_overlay")
                    for row in range(4):
                        for col in range(6):
                            dpg.draw_circle(warp(col + 0.5, row + 0.5), 3,
                                            color=(255,255,0,255),
                                            parent="vp_overlay")
            except Exception:
                pass

        dpg.render_dearpygui_frame()

    if conn['stop_evt']:
        conn['stop_evt'].set()
    dpg.destroy_context()


if __name__ == '__main__':
    main()
