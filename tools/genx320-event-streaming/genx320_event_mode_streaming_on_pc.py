#!/usr/bin/env python3
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# GenX320 event camera visualization GUI for PC.
# Requires: Python 3.12+ and `pip install dearpygui numpy numba Pillow pyserial openmv`
#
# Two threads: camera_worker (receives events) and render loop (draws).
# Canvas initialized to 128; events add contrast*polarity until clamping at 0/255.
# Color modes: Grayscale, Evt Dark LUT, Evt Light LUT (RGB565 → RGB888).
#

import sys

# The openmv library uses `int in EnumType` membership tests that only work on
# Python 3.12+. Fail fast with a clear message instead of a cryptic EnumMeta
# TypeError at connect time.
if sys.version_info < (3, 12):
    sys.exit(
        f"Error: Python 3.12 or newer is required "
        f"(detected Python {sys.version_info.major}.{sys.version_info.minor}).\n"
        f"The openmv library uses enum features only available in Python 3.12+.\n"
        f"Install Python 3.12+ (via pyenv, deadsnakes PPA, or python.org) and "
        f"re-run with that interpreter."
    )

import os
import argparse
import time
import logging
import signal
import threading
import queue
from collections import deque

# Wrap third-party imports so missing dependencies produce one clear
# `pip install ...` message instead of a single ModuleNotFoundError.
_MISSING = []
try:
    import numpy as np
except ImportError:
    _MISSING.append('numpy')
try:
    import numba
except ImportError:
    _MISSING.append('numba')
try:
    import serial.tools.list_ports
except ImportError:
    _MISSING.append('pyserial')
try:
    import dearpygui.dearpygui as dpg
except ImportError:
    _MISSING.append('dearpygui')
try:
    from openmv.camera import Camera
except ImportError:
    _MISSING.append('openmv')
if _MISSING:
    sys.exit(
        f"Error: Missing required Python packages: {', '.join(_MISSING)}\n"
        f"Install them with:\n"
        f"    pip install {' '.join(_MISSING)}"
    )

# Pillow is optional (used for legend rendering); fall back gracefully.
try:
    from PIL import Image, ImageDraw
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


COLOR_CAMERA = "\033[32m"
COLOR_RESET  = "\033[0m"

# GENX320 sensor resolution
SENSOR_W = 320
SENSOR_H = 320

CTRL_WIDTH  = 300
LEGEND_DW   = 80     # legend display width in pixels
TEXTURE_TAG = "evt_tex"
TEX_REG_TAG = "tex_reg"

# ---------------------------------------------------------------------------
# Color lookup tables (RGB565, 256 entries each)
# Source: https://github.com/openmv/openmv/blob/master/lib/imlib/rainbow_tab.c
# evt_dark_table  @ L104
# evt_light_table @ L138
# Conversion: https://github.com/openmv/openmv/blob/master/lib/imlib/draw.c#L713
# ---------------------------------------------------------------------------

_EVT_DARK_565 = np.array([
    0xD6FD, 0xD6FC, 0xD6DC, 0xD6DC, 0xD6DC, 0xCEBC, 0xCEBC, 0xCE9B,
    0xCE9B, 0xCE9B, 0xC67B, 0xC67B, 0xC67B, 0xC65A, 0xC65A, 0xC65A,
    0xBE3A, 0xBE3A, 0xBE1A, 0xBE19, 0xBE19, 0xB5F9, 0xB5F9, 0xB5F9,
    0xB5D8, 0xB5D8, 0xB5D8, 0xADB8, 0xADB8, 0xAD98, 0xAD97, 0xAD97,
    0xAD77, 0xA577, 0xA577, 0xA556, 0xA556, 0xA556, 0x9D36, 0x9D36,
    0x9D36, 0x9D16, 0x9D15, 0x9D15, 0x94F5, 0x94F5, 0x94F5, 0x94D4,
    0x94D4, 0x94B4, 0x8CB4, 0x8CB4, 0x8C94, 0x8C93, 0x8C93, 0x8C73,
    0x8473, 0x8473, 0x8452, 0x8452, 0x8432, 0x7C32, 0x7C32, 0x7C12,
    0x7C12, 0x7C11, 0x7BF1, 0x73F1, 0x73F1, 0x73D1, 0x73D0, 0x73B0,
    0x6BB0, 0x6BB0, 0x6B90, 0x6B90, 0x6B8F, 0x6B6F, 0x636F, 0x636F,
    0x634F, 0x634E, 0x632E, 0x632E, 0x5B2E, 0x5B0E, 0x5B0E, 0x5B0D,
    0x5AED, 0x52ED, 0x52ED, 0x52CD, 0x52CD, 0x52AC, 0x52AC, 0x4AAC,
    0x4AAC, 0x4A8C, 0x4A8C, 0x4A8B, 0x4A6B, 0x426B, 0x424B, 0x424B,
    0x424A, 0x422A, 0x3A2A, 0x3A2A, 0x3A0A, 0x3A0A, 0x3A09, 0x39E9,
    0x31E9, 0x31C9, 0x31C9, 0x31C9, 0x31A8, 0x29A8, 0x29A8, 0x2988,
    0x2988, 0x2988, 0x2967, 0x2167, 0x2147, 0x2147, 0x2147, 0x2126,
    0x2126, 0x2126, 0x2127, 0x2147, 0x2147, 0x2147, 0x2147, 0x2147,
    0x2147, 0x2168, 0x2168, 0x2168, 0x2168, 0x2168, 0x2168, 0x2188,
    0x2189, 0x2189, 0x2189, 0x2189, 0x2189, 0x21A9, 0x21A9, 0x21A9,
    0x21AA, 0x21AA, 0x21CA, 0x21CA, 0x21CA, 0x21CA, 0x21CA, 0x29CB,
    0x29EB, 0x29EB, 0x29EB, 0x29EB, 0x29EB, 0x29EC, 0x2A0C, 0x2A0C,
    0x2A0C, 0x2A0C, 0x2A0C, 0x2A0C, 0x2A2D, 0x2A2D, 0x2A2D, 0x2A2D,
    0x2A2D, 0x2A4D, 0x2A4D, 0x2A4D, 0x2A4E, 0x2A4E, 0x2A4E, 0x2A6E,
    0x2A6E, 0x2A6E, 0x2A6E, 0x2A6F, 0x2A6F, 0x328F, 0x328F, 0x328F,
    0x328F, 0x328F, 0x3290, 0x32B0, 0x32B0, 0x32B0, 0x32B0, 0x32B0,
    0x32B0, 0x32B1, 0x32D1, 0x32D1, 0x32D1, 0x32D1, 0x32D1, 0x32D1,
    0x32F2, 0x32F2, 0x32F2, 0x32F2, 0x32F2, 0x3312, 0x3312, 0x3313,
    0x3313, 0x3313, 0x3313, 0x3B33, 0x3B33, 0x3B33, 0x3B34, 0x3B34,
    0x3B34, 0x3B54, 0x3B54, 0x3B54, 0x3B54, 0x3B55, 0x3B55, 0x3B75,
    0x3B75, 0x3B75, 0x3B75, 0x3B75, 0x3B96, 0x3B96, 0x3B96, 0x3B96,
    0x3B96, 0x3B96, 0x3BB6, 0x3BB6, 0x3BB7, 0x3BB7, 0x3BB7, 0x3BB7,
    0x3BD7, 0x43D7, 0x43D8, 0x43D8, 0x43D8, 0x43D8, 0x43F8, 0x43F8,
], dtype=np.uint16)

_EVT_LIGHT_565 = np.array([
    0x43F8, 0x43F8, 0x43F8, 0x4418, 0x4419, 0x4419, 0x4C19, 0x4C19,
    0x4C39, 0x4C39, 0x4C39, 0x4C39, 0x4C39, 0x5439, 0x5459, 0x5459,
    0x5459, 0x5459, 0x5459, 0x5479, 0x5C79, 0x5C79, 0x5C79, 0x5C79,
    0x5C99, 0x5C99, 0x5C99, 0x6499, 0x6499, 0x6499, 0x64B9, 0x64B9,
    0x64B9, 0x6CBA, 0x6CBA, 0x6CDA, 0x6CDA, 0x6CDA, 0x6CDA, 0x6CDA,
    0x6CFA, 0x74FA, 0x74FA, 0x74FA, 0x74FA, 0x751A, 0x751A, 0x751A,
    0x7D1A, 0x7D1A, 0x7D1A, 0x7D3A, 0x7D3A, 0x7D3A, 0x853A, 0x853A,
    0x855A, 0x855A, 0x855A, 0x855A, 0x855A, 0x8D5A, 0x8D5A, 0x8D7B,
    0x8D7B, 0x8D7B, 0x8D7B, 0x8D7B, 0x959B, 0x959B, 0x959B, 0x959B,
    0x959B, 0x95BB, 0x95BB, 0x9DBB, 0x9DBB, 0x9DBB, 0x9DDB, 0x9DDB,
    0x9DDB, 0x9DDB, 0xA5DB, 0xA5DB, 0xA5FB, 0xA5FB, 0xA5FB, 0xA5FB,
    0xA5FB, 0xAE1B, 0xAE1B, 0xAE1B, 0xAE1B, 0xAE1B, 0xAE3B, 0xAE3B,
    0xB63C, 0xB63C, 0xB63C, 0xB65C, 0xB65C, 0xB65C, 0xB65C, 0xBE5C,
    0xBE5C, 0xBE7C, 0xBE7C, 0xBE7C, 0xBE7C, 0xBE7C, 0xC69C, 0xC69C,
    0xC69C, 0xC69C, 0xC69C, 0xC6BC, 0xC6BC, 0xCEBC, 0xCEBC, 0xCEBC,
    0xCEBC, 0xCEDC, 0xCEDC, 0xD6DC, 0xD6DC, 0xD6DD, 0xD6FD, 0xD6FD,
    0xD6FD, 0xD6FC, 0xD6DC, 0xD6DC, 0xD6DC, 0xCEBC, 0xCEBC, 0xCE9B,
    0xCE9B, 0xCE9B, 0xC67B, 0xC67B, 0xC67B, 0xC65A, 0xC65A, 0xC65A,
    0xBE3A, 0xBE3A, 0xBE1A, 0xBE19, 0xBE19, 0xB5F9, 0xB5F9, 0xB5F9,
    0xB5D8, 0xB5D8, 0xB5D8, 0xADB8, 0xADB8, 0xAD98, 0xAD97, 0xAD97,
    0xAD77, 0xA577, 0xA577, 0xA556, 0xA556, 0xA556, 0x9D36, 0x9D36,
    0x9D36, 0x9D16, 0x9D15, 0x9D15, 0x94F5, 0x94F5, 0x94F5, 0x94D4,
    0x94D4, 0x94B4, 0x8CB4, 0x8CB4, 0x8C94, 0x8C93, 0x8C93, 0x8C73,
    0x8473, 0x8473, 0x8452, 0x8452, 0x8432, 0x7C32, 0x7C32, 0x7C12,
    0x7C12, 0x7C11, 0x7BF1, 0x73F1, 0x73F1, 0x73D1, 0x73D0, 0x73B0,
    0x6BB0, 0x6BB0, 0x6B90, 0x6B90, 0x6B8F, 0x6B6F, 0x636F, 0x636F,
    0x634F, 0x634E, 0x632E, 0x632E, 0x5B2E, 0x5B0E, 0x5B0E, 0x5B0D,
    0x5AED, 0x52ED, 0x52ED, 0x52CD, 0x52CD, 0x52AC, 0x52AC, 0x4AAC,
    0x4AAC, 0x4A8C, 0x4A8C, 0x4A8B, 0x4A6B, 0x426B, 0x424B, 0x424B,
    0x424A, 0x422A, 0x3A2A, 0x3A2A, 0x3A0A, 0x3A0A, 0x3A09, 0x39E9,
    0x31E9, 0x31C9, 0x31C9, 0x31C9, 0x31A8, 0x29A8, 0x29A8, 0x2988,
    0x2988, 0x2988, 0x2967, 0x2167, 0x2147, 0x2147, 0x2147, 0x2126,
], dtype=np.uint16)


def _rgb565_to_rgb888(table565):
    """Convert a 256-entry RGB565 LUT to a (256, 3) uint8 RGB888 array.

    Bit-replication matches the COLOR_RGB565_TO_R8/G8/B8 macros in draw.c:
      R8 = (R5 << 3) | (R5 >> 2)
      G8 = (G6 << 2) | (G6 >> 4)
      B8 = (B5 << 3) | (B5 >> 2)
    """
    v  = table565.astype(np.uint32)
    r5 = (v >> 11) & 0x1F
    g6 = (v >>  5) & 0x3F
    b5 =  v        & 0x1F
    r8 = ((r5 << 3) | (r5 >> 2)).astype(np.uint8)
    g8 = ((g6 << 2) | (g6 >> 4)).astype(np.uint8)
    b8 = ((b5 << 3) | (b5 >> 2)).astype(np.uint8)
    return np.stack([r8, g8, b8], axis=1)   # (256, 3) uint8


EVT_DARK_RGB  = _rgb565_to_rgb888(_EVT_DARK_565)
EVT_LIGHT_RGB = _rgb565_to_rgb888(_EVT_LIGHT_565)

COLOR_MODES = ["Grayscale", "Evt Dark", "Evt Light"]


def _canvas_to_texture(canvas_u8, color_mode):
    """Convert a uint8 canvas (H×W) to a flat float32 RGBA array for DearPyGui."""
    if color_mode == "Grayscale":
        rgb = np.stack([canvas_u8, canvas_u8, canvas_u8], axis=-1)
    elif color_mode == "Evt Dark":
        rgb = EVT_DARK_RGB[canvas_u8]
    else:  # Evt Light
        rgb = EVT_LIGHT_RGB[canvas_u8]
    rgba = np.ones((SENSOR_H, SENSOR_W, 4), dtype=np.float32)
    rgba[:, :, :3] = rgb * (1.0 / 255.0)
    return rgba.ravel()


def _draw_freq_legend(tag, dh, min_freq, max_freq, use_log, n_bins):
    """Redraw a DPG drawlist with a frequency colorbar legend (high freq at top)."""
    import dearpygui.dearpygui as _dpg
    _dpg.delete_item(tag, children_only=True)
    if n_bins < 2 or dh <= 0:
        return
    # Dark background
    _dpg.draw_rectangle(pmin=(0, 0), pmax=(LEGEND_DW, dh),
                        color=(30, 30, 30, 255), fill=(30, 30, 30, 255), parent=tag)
    color_w = 16        # width of the colored band
    text_x  = color_w + 4
    bin_h   = dh / n_bins

    if use_log:
        lo = np.log10(max(min_freq, 1e-9))
        hi = np.log10(max(max_freq, min_freq * 1.001 + 1e-9))
        vals_tf = np.linspace(hi, lo, n_bins)   # high freq at top → low at bottom
        freq_labels = 10.0 ** vals_tf
        idx_vals = np.clip(((vals_tf - lo) / (hi - lo + 1e-12)) * 255, 0, 255).astype(np.uint8)
    else:
        freq_labels = np.linspace(max_freq, min_freq, n_bins)
        rng = max(max_freq - min_freq, 1e-9)
        idx_vals = np.clip((freq_labels - min_freq) / rng * 255, 0, 255).astype(np.uint8)

    for i in range(n_bins):
        y0 = int(i * bin_h)
        y1 = max(int((i + 1) * bin_h), y0 + 1)
        rgb = FREQ_LUT[idx_vals[i]]
        col = (int(rgb[0]), int(rgb[1]), int(rgb[2]), 255)
        _dpg.draw_rectangle(pmin=(0, y0), pmax=(color_w, y1),
                            color=col, fill=col, parent=tag)
        f = float(freq_labels[i])
        if f >= 10000:
            label = f"{f / 1000:.0f}k"
        elif f >= 1000:
            label = f"{f / 1000:.1f}k"
        elif f >= 100:
            label = f"{f:.0f}"
        elif f >= 10:
            label = f"{f:.1f}"
        else:
            label = f"{f:.2f}"
        text_y = y0 + max(int(bin_h) // 2 - 6, 0)
        _dpg.draw_text(pos=(text_x, text_y), text=label,
                       color=(210, 210, 210, 255), size=12, parent=tag)


def _make_freq_legend_pil(height, min_freq, max_freq, use_log, n_bins):
    """Render the frequency colorbar legend as a PIL Image (height × LEGEND_DW)."""
    img  = Image.new('RGB', (LEGEND_DW, height), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    color_w = 16
    bin_h   = height / max(n_bins, 1)

    if use_log:
        lo = np.log10(max(min_freq, 1e-9))
        hi = np.log10(max(max_freq, min_freq * 1.001 + 1e-9))
        vals_tf    = np.linspace(hi, lo, n_bins)
        freq_labels = 10.0 ** vals_tf
        idx_vals    = np.clip(((vals_tf - lo) / (hi - lo + 1e-12)) * 255, 0, 255).astype(np.uint8)
    else:
        freq_labels = np.linspace(max_freq, min_freq, n_bins)
        rng      = max(max_freq - min_freq, 1e-9)
        idx_vals = np.clip((freq_labels - min_freq) / rng * 255, 0, 255).astype(np.uint8)

    for i in range(n_bins):
        y0  = int(i * bin_h)
        y1  = max(int((i + 1) * bin_h), y0 + 1)
        rgb = FREQ_LUT[idx_vals[i]]
        draw.rectangle([(0, y0), (color_w - 1, y1 - 1)],
                       fill=(int(rgb[0]), int(rgb[1]), int(rgb[2])))
        f = float(freq_labels[i])
        if   f >= 10000: label = f"{f / 1000:.0f}k"
        elif f >= 1000:  label = f"{f / 1000:.1f}k"
        elif f >= 100:   label = f"{f:.0f}"
        elif f >= 10:    label = f"{f:.1f}"
        else:            label = f"{f:.2f}"
        draw.text((color_w + 3, y0 + max(int(bin_h) // 2 - 6, 0)),
                  label, fill=(210, 210, 210))
    return img


def list_com_ports():
    return sorted(p.device for p in serial.tools.list_ports.comports())


# ---------------------------------------------------------------------------
# Frequency camera helpers
# Reference: https://github.com/ros-event-camera/frequency_cam
# ---------------------------------------------------------------------------

FREQ_TEX_TAG = "freq_tex"


def _make_freq_lut():
    """HSV colormap: index 0 → blue (low freq), 255 → red (high freq)."""
    import colorsys
    lut = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        hue = (1.0 - i / 255.0) * (240.0 / 360.0)
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        lut[i] = [int(r * 255), int(g * 255), int(b * 255)]
    return lut


FREQ_LUT = _make_freq_lut()


def _freq_filter_coeffs(cutoff_period):
    """Compute second-order IIR bandpass coefficients (c1, c2, c3).

    Matches the reference implementation exactly:
      omega = 2π/T,  phi = 2 - cos(omega)
      alpha = (1 - sin(omega)) / cos(omega)
      beta  = phi - sqrt(phi² - 1)
      c1 = alpha + beta,  c2 = -alpha·beta,  c3 = 0.5·(1 + beta)
    Filter: L_k = c1·L_{k-1} + c2·L_{k-2} + c3·(p - p_prev)
    """
    T     = max(cutoff_period, 1.0)
    omega = 2.0 * np.pi / T
    phi   = 2.0 - np.cos(omega)
    alpha = (1.0 - np.sin(omega)) / np.cos(omega)
    beta  = phi - np.sqrt(max(phi * phi - 1.0, 0.0))
    c1 =  alpha + beta
    c2 = -alpha * beta   # negative — used as L_k = c1·L1 + c2·L2 + c3·dp
    c3 =  0.5 * (1.0 + beta)
    return c1, c2, c3


@numba.njit(nogil=True, cache=True)
def _update_freq_cam(xs, ys, pols, ts_f,
                     fc_L2, fc_L1, fc_p1,
                     fc_t_ud, fc_t_du, fc_per,
                     c1, c2, c3,
                     fc_dt_min, fc_dt_max,
                     fc_dt_min_half, fc_dt_max_half,
                     fc_n_to):
    """Per-event sequential IIR frequency camera update.

    Compiled with nogil=True so the camera reader thread runs concurrently.
    Returns the timestamp of the last processed event (or -1.0 if empty).
    """
    n = xs.shape[0]
    if n == 0:
        return -1.0
    for i in range(n):
        px = xs[i];  py = ys[i]
        p  = pols[i] * 2.0 - 1.0
        t  = ts_f[i]
        l2 = fc_L2[py, px]
        l1 = fc_L1[py, px]
        dp = p - fc_p1[py, px]
        l_new = c1 * l1 + c2 * l2 + c3 * dp
        if not (abs(l_new) < 1e4):
            l_new = 0.0
            l1    = 0.0
        fc_L2[py, px] = l1
        fc_L1[py, px] = l_new
        fc_p1[py, px] = p

        if l1 > 0.0 and l_new < 0.0:
            dt_ud = t - fc_t_ud[py, px]
            dt_du = t - fc_t_du[py, px]
            if fc_dt_min <= dt_ud <= fc_dt_max:
                fc_per[py, px] = dt_ud
            else:
                cur = fc_per[py, px]
                if cur > 0.0:
                    if dt_ud > cur * fc_n_to and dt_du > 0.5 * cur * fc_n_to:
                        fc_per[py, px] = 0.0
                else:
                    if fc_dt_min_half <= dt_du <= fc_dt_max_half:
                        fc_per[py, px] = 2.0 * dt_du
            fc_t_ud[py, px] = t

        elif l1 < 0.0 and l_new > 0.0:
            dt_du = t - fc_t_du[py, px]
            dt_ud = t - fc_t_ud[py, px]
            cur   = fc_per[py, px]
            if fc_dt_min <= dt_du <= fc_dt_max and cur <= 0.0:
                fc_per[py, px] = dt_du
            else:
                if cur > 0.0:
                    if dt_du > cur * fc_n_to and dt_ud > 0.5 * cur * fc_n_to:
                        fc_per[py, px] = 0.0
                else:
                    if fc_dt_min_half <= dt_ud <= fc_dt_max_half:
                        fc_per[py, px] = 2.0 * dt_ud
            fc_t_du[py, px] = t

    return ts_f[n - 1]


def _freq_to_texture(fc_per, fc_t_ud, fc_t_du, t_now, n_timeout, min_freq, max_freq,
                     use_log=True, overlay_events=False):
    """Convert per-pixel frequency state to a flat float32 RGBA for DearPyGui.

    Timeout: pixel is inactive when t_now - max(t_ud, t_du) exceeds n_timeout periods.
    Two-condition check matches reference: dt < dtMax·n_timeout² AND dt·freq < n_timeout.
    use_log:        log10 frequency color scale (True) vs linear (False).
    overlay_events: grey pixels that have had crossings but no active frequency.
    """
    last_cross = np.maximum(fc_t_ud, fc_t_du)
    dt         = t_now - last_cross                          # seconds since last crossing
    dt_max     = 1.0 / max(min_freq, 1e-9)

    safe_per = np.where(fc_per > 0.0, fc_per, 1.0)
    freq     = np.where(fc_per > 0.0, 1.0 / safe_per, 0.0).astype(np.float32)

    active = (fc_per > 0.0) & (dt < dt_max * n_timeout * n_timeout) & (
              dt.astype(np.float32) * freq < n_timeout)

    in_range = active & (freq >= min_freq) & (freq <= max_freq)

    idx = np.zeros((SENSOR_H, SENSOR_W), dtype=np.uint8)
    if in_range.any():
        clipped = np.where(in_range, np.clip(freq, min_freq, max_freq), min_freq)
        if use_log:
            lo = np.log10(max(min_freq, 1e-9))
            hi = np.log10(max(max_freq, min_freq * 1.001 + 1e-9))
            vals = (np.log10(clipped) - lo) / (hi - lo) * 255.0
        else:
            rng = max(max_freq - min_freq, 1e-9)
            vals = (clipped - min_freq) / rng * 255.0
        idx[in_range] = np.clip(vals[in_range], 0, 255).astype(np.uint8)

    rgba = np.zeros((SENSOR_H, SENSOR_W, 4), dtype=np.float32)
    rgba[:, :, 3] = 1.0
    rgba[:, :, :3] = FREQ_LUT[idx].astype(np.float32) * (1.0 / 255.0)
    rgba[~active, :3] = 0.0

    if overlay_events:
        # Grey out pixels with crossing history but no active frequency
        has_crossed = (fc_t_ud > 0.0) | (fc_t_du > 0.0)
        rgba[has_crossed & ~active, :3] = 0.5

    return rgba.ravel()


# ---------------------------------------------------------------------------
# Camera background thread  (receives data, puts onto queue)
# ---------------------------------------------------------------------------

EMA_ALPHA = 0.2

EVT_RES_OPTIONS = [1024, 2048, 4096, 8192, 16384, 32768, 65536]

# Event stream formats (raw mode only). The GUI shows all four; EVT3.0 and AER
# are decode-pending, so they appear greyed ("soon") and revert to the previous
# selection if chosen. Codes match EVT_FORMAT in the on-camera script.
EVT_FORMATS = [
    # (combo label, format code, decoder implemented)
    ("EVT2.0", "EVT20", True),
    ("EVT2.1", "EVT21", True),
    ("EVT3.0",       "EVT30", True),
    ("AER (legacy)", "AER",   True),
]
EVT_FORMAT_LABELS = [f[0] for f in EVT_FORMATS]
EVT_LABEL_TO_CODE = {f[0]: f[1] for f in EVT_FORMATS}
EVT_CODE_TO_LABEL = {f[1]: f[0] for f in EVT_FORMATS}
EVT_LABEL_READY   = {f[0]: f[2] for f in EVT_FORMATS}
# Metavision RAW header fields per format code (used when recording). `fmt` is
# the modern `% format` token; `evt` is the legacy `% evt` version string. AER is
# absent — it has no Metavision RAW representation and records verbatim instead.
EVT_METAVISION = {
    "EVT20": {"fmt": "EVT2",  "evt": "2.0"},
    "EVT21": {"fmt": "EVT21", "evt": "2.1"},
    "EVT30": {"fmt": "EVT3",  "evt": "3.0"},
}


def patch_script(script, csi_fifo_depth, evt_fifo_depth, evt_res, raw_mode=False,
                 evt_format='EVT20'):
    """Patch the on-camera script with GUI-controlled parameters before exec.

    Substitutions made (processed mode):
      CSI_FIFO_DEPTH   = <value>
      EVENT_FIFO_DEPTH = <value>
      np.zeros((EVT_RES, 6), ...)  — the array shape (EVT_RES constant)
      def read / def readp         — use readp on Mac/Linux, read on Windows

    Substitutions made (raw mode):
      CSI_FIFO_DEPTH = <value>
      EVT_RES        = <value>     — only the constant assignment
      EVT_FORMAT     = "<value>"   — sensor output event format
      def read / def readp
    """
    import re

    script = re.sub(r'CSI_FIFO_DEPTH\s*=\s*\d+',
                    f'CSI_FIFO_DEPTH = {csi_fifo_depth}', script)

    if raw_mode:
        script = re.sub(r'EVT_RES\s*=\s*\d+',
                        f'EVT_RES = {evt_res}', script)
        script = re.sub(r'EVT_FORMAT\s*=\s*["\']\w+["\']',
                        f'EVT_FORMAT = "{evt_format}"', script)
    else:
        script = re.sub(r'EVENT_FIFO_DEPTH\s*=\s*\d+',
                        f'EVENT_FIFO_DEPTH = {evt_fifo_depth}', script)
        script = re.sub(r'np\.zeros\(\((?:\d+|EVT_RES),\s*6\)',
                        f'np.zeros(({evt_res}, 6)', script)

    if sys.platform != 'win32':
        script = script.replace('def read(self, offset, size):',
                                'def readp(self, offset, size):')

    return script


def decode_raw_events(buf, time_high_ref):
    """Vectorized EVT 2.0 decoder.

    Decodes a buffer of raw 32-bit little-endian EVT 2.0 words into an (N, 6)
    uint16 array matching the ec_event_t layout from the processed cam script:
      [0] type   — EC_PIX_OFF_EVENT(0), EC_PIX_ON_EVENT(1),
                   EC_EXT_TRIGGER_FALLING(2), EC_EXT_TRIGGER_RISING(3),
                   EC_RST_TRIGGER_FALLING(4), EC_RST_TRIGGER_RISING(5)
      [1] ts_s   — whole seconds of timestamp
      [2] ts_ms  — milliseconds within the second (0-999)
      [3] ts_us  — microseconds within the millisecond (0-999)
      [4] x      — pixel column (0 for trigger events)
      [5] y      — pixel row    (0 for trigger events)

    Handles TD pixel events (0x0/0x1) and EXT_TRIGGER events (0xA).
    EV_TIME_HIGH (0x8) words update the running timestamp accumulator.

    time_high_ref is a one-element list carrying the running EV_TIME_HIGH
    value across consecutive calls (updated in-place).
    """
    n_words = len(buf) // 4
    if n_words == 0:
        return np.zeros((0, 6), dtype=np.uint16)

    words = np.frombuffer(buf, dtype=np.uint32)
    types = (words >> 28) & 0xF

    # --- EV_TIME_HIGH (0x8): update running timestamp accumulator ---
    th_mask = types == 0x8
    th_idx  = np.where(th_mask)[0]
    th_vals = ((words[th_mask] & 0x0FFFFFFF).astype(np.uint64)) << 6

    # --- all output events: TD pixel (0x0, 0x1) + EXT_TRIGGER (0xA) ---
    evt_mask = (types <= 0x1) | (types == 0xA)
    evt_idx  = np.where(evt_mask)[0]

    if evt_idx.size == 0:
        if th_vals.size > 0:
            time_high_ref[0] = int(th_vals[-1])
        return np.zeros((0, 6), dtype=np.uint16)

    # --- assign the correct time_high to every event (vectorized) ---
    # The applicable time_high for event at position i is the last EV_TIME_HIGH
    # whose stream position is strictly before i.
    if th_idx.size > 0:
        ins = np.searchsorted(th_idx, evt_idx, side='right') - 1
        th_for_evt = np.empty(evt_idx.size, dtype=np.uint64)
        before_first = ins < 0
        th_for_evt[before_first]  = time_high_ref[0]
        th_for_evt[~before_first] = th_vals[ins[~before_first]]
        time_high_ref[0] = int(th_vals[-1])
    else:
        th_for_evt = np.full(evt_idx.size, time_high_ref[0], dtype=np.uint64)

    # --- reconstruct full microsecond timestamp ---
    evt_words = words[evt_idx]
    evt_types = types[evt_idx]
    ts_low = ((evt_words >> 22) & 0x3F).astype(np.uint64)
    t_us   = th_for_evt | ts_low

    ts_s  = (t_us // 1_000_000).astype(np.uint16)
    ts_ms = ((t_us // 1_000) % 1_000).astype(np.uint16)
    ts_us = (t_us % 1_000).astype(np.uint16)

    # --- pixel events: type is 0 (off) or 1 (on), x/y from bit fields ---
    out_type = evt_types.astype(np.uint16)   # 0 or 1 for TD events
    x = ((evt_words >> 11) & 0x7FF).astype(np.uint16)
    y = (evt_words & 0x7FF).astype(np.uint16)

    # --- trigger events: remap type to EC_TRIGGER_EVENT(id, polarity) ---
    # EC_TRIGGER_EVENT = EC_EXT_TRIGGER_FALLING(2) + ((id & 1) << 1) + polarity
    # x and y are 0 for trigger events (no pixel coordinate).
    is_trig = evt_types == 0xA
    if is_trig.any():
        tw       = evt_words[is_trig]
        trig_id  = ((tw >> 8) & 0x1F).astype(np.uint16)
        trig_pol = (tw & 0x1).astype(np.uint16)
        out_type[is_trig] = 2 + ((trig_id & 1) << 1) + trig_pol
        x[is_trig] = 0
        y[is_trig] = 0

    return np.stack([out_type, ts_s, ts_ms, ts_us, x, y], axis=1)


def decode_raw_events_evt21(buf, time_high_ref):
    """Vectorized EVT 2.1 decoder.

    EVT 2.1 packs events into 64-bit little-endian word pairs. The high 32-bit
    word has the same bit layout as an EVT 2.0 word (type/ts/x/y), and the low
    32-bit word is a 32-bit `valid` bitmask. For CD events the x coordinate is
    aligned on 32 and bit n of the mask marks a valid event at (x+n, y), so a
    single pair expands to up to 32 pixel events.

    Returns the same (N, 6) uint16 layout as decode_raw_events:
      [type, ts_s, ts_ms, ts_us, x, y]

    time_high_ref is a one-element list carrying the running EV_TIME_HIGH value
    across consecutive calls (updated in-place).
    """
    words = np.frombuffer(buf, dtype=np.uint32)
    n_words = words.shape[0] & ~1   # drop a trailing half-pair, if any
    if n_words == 0:
        return np.zeros((0, 6), dtype=np.uint16)
    words = words[:n_words]
    lo = words[0::2]                 # valid bitmask (CD) / unused (others)
    hi = words[1::2]                 # type/ts/x/y — EVT 2.0 word layout
    types = (hi >> 28) & 0xF

    # --- EV_TIME_HIGH (0x8): update running timestamp accumulator ---
    th_mask = types == 0x8
    th_idx  = np.where(th_mask)[0]
    th_vals = ((hi[th_mask] & 0x0FFFFFFF).astype(np.uint64)) << 6

    # --- output events: CD pixel (0x0, 0x1) + EXT_TRIGGER (0xA) ---
    evt_mask = (types <= 0x1) | (types == 0xA)
    evt_idx  = np.where(evt_mask)[0]

    if evt_idx.size == 0:
        if th_vals.size > 0:
            time_high_ref[0] = int(th_vals[-1])
        return np.zeros((0, 6), dtype=np.uint16)

    # --- assign the applicable time_high to every event (vectorized) ---
    if th_idx.size > 0:
        ins = np.searchsorted(th_idx, evt_idx, side='right') - 1
        th_for_evt = np.empty(evt_idx.size, dtype=np.uint64)
        before_first = ins < 0
        th_for_evt[before_first]  = time_high_ref[0]
        th_for_evt[~before_first] = th_vals[ins[~before_first]]
        time_high_ref[0] = int(th_vals[-1])
    else:
        th_for_evt = np.full(evt_idx.size, time_high_ref[0], dtype=np.uint64)

    evt_hi    = hi[evt_idx]
    evt_types = types[evt_idx]
    ts_low    = ((evt_hi >> 22) & 0x3F).astype(np.uint64)
    t_us      = th_for_evt | ts_low

    is_cd   = evt_types <= 0x1
    is_trig = evt_types == 0xA

    out_chunks = []

    # --- CD events: expand the valid bitmask into individual pixel events ---
    if is_cd.any():
        cd_hi   = evt_hi[is_cd]
        cd_pol  = evt_types[is_cd].astype(np.uint16)        # 0=off, 1=on
        cd_xbase = ((cd_hi >> 11) & 0x7FF).astype(np.uint32)
        cd_y     = (cd_hi & 0x7FF).astype(np.uint16)
        cd_t     = t_us[is_cd]
        cd_valid = lo[evt_idx][is_cd]                       # 32-bit mask per word

        # (M, 32) bool: bit k set -> event at (xbase+k, y)
        offsets = np.arange(32, dtype=np.uint32)
        bits = ((cd_valid[:, None] >> offsets) & 1).astype(bool)
        rows, cols = np.nonzero(bits)                       # row-major: parent order, then x

        if rows.size:
            ev_t  = cd_t[rows]
            cd_out = np.empty((rows.size, 6), dtype=np.uint16)
            cd_out[:, 0] = cd_pol[rows]
            cd_out[:, 1] = (ev_t // 1_000_000).astype(np.uint16)
            cd_out[:, 2] = ((ev_t // 1_000) % 1_000).astype(np.uint16)
            cd_out[:, 3] = (ev_t % 1_000).astype(np.uint16)
            cd_out[:, 4] = (cd_xbase[rows] + cols).astype(np.uint16)
            cd_out[:, 5] = cd_y[rows]
            out_chunks.append(cd_out)

    # --- trigger events: remap type to EC_TRIGGER_EVENT(id, polarity) ---
    # EC_TRIGGER_EVENT = EC_EXT_TRIGGER_FALLING(2) + ((id & 1) << 1) + polarity
    if is_trig.any():
        tw       = evt_hi[is_trig]
        trig_t   = t_us[is_trig]
        trig_id  = ((tw >> 8) & 0x1F).astype(np.uint16)
        trig_pol = (tw & 0x1).astype(np.uint16)
        trig_out = np.zeros((tw.size, 6), dtype=np.uint16)
        trig_out[:, 0] = 2 + ((trig_id & 1) << 1) + trig_pol
        trig_out[:, 1] = (trig_t // 1_000_000).astype(np.uint16)
        trig_out[:, 2] = ((trig_t // 1_000) % 1_000).astype(np.uint16)
        trig_out[:, 3] = (trig_t % 1_000).astype(np.uint16)
        out_chunks.append(trig_out)

    if not out_chunks:
        return np.zeros((0, 6), dtype=np.uint16)
    if len(out_chunks) == 1:
        return out_chunks[0]
    return np.concatenate(out_chunks, axis=0)


@numba.njit(nogil=True, cache=True)
def _decode_evt3_core(words, state, out):
    """Sequential EVT 3.0 state-machine decode (compiled, nogil).

    EVT 3.0 is a 16-bit compressed format: y, x, polarity, timestamp and type
    are only re-sent when they change, so the decoder must carry state. `state`
    is a 6-element int64 array preserved across calls:
        [0] th        — current time_high, already shifted (<<12)
        [1] tl        — current time_low (12 bits)
        [2] y         — current y coordinate
        [3] bx        — current vector base x
        [4] bp        — current vector base polarity
        [5] wrapbase  — accumulated 2^24 us offsets (time_high is only 24-bit)

    `out` is a preallocated (M, 6) int32 buffer; the function writes
    [type, ts_s, ts_ms, ts_us, x, y] rows and returns the number written.
    """
    th = state[0]; tl = state[1]; y = state[2]
    bx = state[3]; bp = state[4]; wrapbase = state[5]
    n = 0
    for i in range(words.shape[0]):
        w = words[i]
        t = (w >> 12) & 0xF
        p = w & 0xFFF
        if t == 0x0:            # EVT_ADDR_Y
            y = p & 0x7FF
        elif t == 0x2:          # EVT_ADDR_X — single valid event
            pol = (p >> 11) & 1
            x   = p & 0x7FF
            bx  = (x >> 5) << 5             # VECT_BASE_X.x = x & ~0x1F (align 32)
            bp  = pol
            t_us = wrapbase + th + tl
            out[n, 0] = pol
            out[n, 1] = t_us // 1_000_000
            out[n, 2] = (t_us // 1_000) % 1_000
            out[n, 3] = t_us % 1_000
            out[n, 4] = x
            out[n, 5] = y
            n += 1
        elif t == 0x3:          # VECT_BASE_X — sets base for following vectors
            bp = (p >> 11) & 1
            bx = p & 0x7FF
        elif t == 0x4:          # VECT_12 — 12 validity bits from bx
            t_us = wrapbase + th + tl
            for k in range(12):
                if (p >> k) & 1:
                    out[n, 0] = bp
                    out[n, 1] = t_us // 1_000_000
                    out[n, 2] = (t_us // 1_000) % 1_000
                    out[n, 3] = t_us % 1_000
                    out[n, 4] = bx + k
                    out[n, 5] = y
                    n += 1
            bx += 12
        elif t == 0x5:          # VECT_8 — 8 validity bits from bx
            valid = p & 0xFF
            t_us = wrapbase + th + tl
            for k in range(8):
                if (valid >> k) & 1:
                    out[n, 0] = bp
                    out[n, 1] = t_us // 1_000_000
                    out[n, 2] = (t_us // 1_000) % 1_000
                    out[n, 3] = t_us % 1_000
                    out[n, 4] = bx + k
                    out[n, 5] = y
                    n += 1
            bx += 8
        elif t == 0x6:          # EVT_TIME_LOW
            tl = p & 0xFFF
        elif t == 0x8:          # EVT_TIME_HIGH (24-bit timer; wraps ~every 16.7s)
            new_th = (p & 0xFFF) << 12
            if new_th < th:
                wrapbase += (1 << 24)
            th = new_th
        elif t == 0xA:          # EXT_TRIGGER
            tid = (p >> 8) & 0xF
            val = p & 1
            t_us = wrapbase + th + tl
            out[n, 0] = 2 + ((tid & 1) << 1) + val
            out[n, 1] = t_us // 1_000_000
            out[n, 2] = (t_us // 1_000) % 1_000
            out[n, 3] = t_us % 1_000
            out[n, 4] = 0
            out[n, 5] = 0
            n += 1
        # OTHERS (0xE) / CONTINUED (0x7, 0xF) carry no CD data — ignored.
    state[0] = th; state[1] = tl; state[2] = y
    state[3] = bx; state[4] = bp; state[5] = wrapbase
    return n


def decode_raw_events_evt3(buf, state):
    """EVT 3.0 decoder. Returns the (N, 6) uint16 layout of decode_raw_events.

    state is a 6-element int64 numpy array carrying the decoder's running state
    across consecutive calls (see _decode_evt3_core).
    """
    words = np.frombuffer(buf, dtype=np.uint16)
    if words.size == 0:
        return np.zeros((0, 6), dtype=np.uint16)
    # Exact upper bound on emitted events: ADDR_X / TRIGGER are 1 each, VECT_12
    # up to 12, VECT_8 up to 8. Cheap to compute and keeps the buffer tight.
    types = (words >> 12) & 0xF
    n_max = int(np.count_nonzero((types == 0x2) | (types == 0xA))
                + 12 * np.count_nonzero(types == 0x4)
                + 8 * np.count_nonzero(types == 0x5))
    out = np.empty((n_max, 6), dtype=np.int32)
    n = _decode_evt3_core(words, state, out)   # updates state even when n == 0
    if n == 0:
        return np.zeros((0, 6), dtype=np.uint16)
    return out[:n].astype(np.uint16)


# Bytes per AER event in the capture buffer. AER encodes one CD event in 19
# bits (pol[18] | x[17:9] | y[8:0]) packed into 3 little-endian bytes (the high
# byte holds only bits 16..18, so it is always 0..7). Confirmed on hardware by
# decoding a capture: at this stride the upper bits are zero and y stays within
# 0..319; at 4 bytes the stream byte-misaligns and produces marching lines.
#
# The capture frame size (EVT_RES * 4 bytes, e.g. 32768) is not a multiple of 3,
# so each frame carries a few padding bytes at the end. Frames do not straddle —
# each channel read is one frame decoded from its start, dropping the remainder.
AER_EVENT_BYTES = 3


def decode_raw_events_aer(buf, state):
    """Vectorized AER (legacy SNN) decoder.

    AER carries CD events only — one event per word, no timestamps, no type or
    trigger events. Each 19-bit value is (pol << 18) | (x << 9) | y, matching
    the firmware's aer.h macros:
        y   = val & 0x1FF          (bits 8..0)
        x   = (val >> 9) & 0x1FF   (bits 17..9)
        pol = (val >> 18) & 1      (bit 18; 0 = CD OFF, 1 = CD ON)

    Returns the (N, 6) uint16 layout of decode_raw_events. Timestamp columns are
    left at 0 — AER transmits no time, so frequency visualization is not
    meaningful for this format (the event canvas still works).

    `state` is accepted for dispatch uniformity but unused (AER is stateless).
    """
    stride = AER_EVENT_BYTES
    n = len(buf) // stride
    if n == 0:
        return np.zeros((0, 6), dtype=np.uint16)
    raw = np.frombuffer(buf, dtype=np.uint8, count=n * stride).reshape(n, stride)
    word = raw[:, 0].astype(np.uint32)
    for i in range(1, stride):
        word |= raw[:, i].astype(np.uint32) << (8 * i)
    val = word & 0x7FFFF                                 # 19 valid bits (pol|x|y)

    out = np.zeros((n, 6), dtype=np.uint16)
    out[:, 0] = ((val >> 18) & 0x1).astype(np.uint16)   # polarity (0=off, 1=on)
    out[:, 4] = ((val >> 9) & 0x1FF).astype(np.uint16)  # x
    out[:, 5] = (val & 0x1FF).astype(np.uint16)         # y
    return out


def _wait_for_script_stopped(camera, timeout, drain_stdout=False):
    """Wait for the camera-side script to actually report Script Stopped on the
    stdin channel. camera.stop() is fire-and-forget — it only sends STDIN_STOP
    and does not wait for the script's main loop to unwind. If we proceed to
    camera.exec() while the previous script is still holding peripherals
    (e.g. the CSI/GenX320 sensor), exec triggers a soft reboot that fires
    before the script has released hardware, and the new script crashes
    during sensor init.

    drain_stdout=True drains the camera's stdout buffer while waiting — useful
    on initial connect when a previous run left output queued, since a full
    stdout buffer can backpressure the script. Do NOT enable during shutdown
    paths: read_stdout's CHANNEL_SIZE/CHANNEL_READ round-trips can interfere
    with cleanup. Returns True if the stop was confirmed, False on timeout.
    """
    stopped_evt = threading.Event()
    orig_handle = camera._handle_event

    def wrapped_handle(channel_id, event):
        orig_handle(channel_id, event)
        ch = camera.channels_by_id.get(channel_id, {})
        if ch.get('name') == 'stdin' and event == 0:
            stopped_evt.set()

    camera._handle_event = wrapped_handle
    try:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if stopped_evt.is_set():
                return True
            try:
                camera.poll_events()
                if drain_stdout:
                    while camera.read_stdout():
                        pass
            except Exception:
                pass
            time.sleep(0.02)
        return False
    finally:
        camera._handle_event = orig_handle


def camera_worker(args, state_lock, state, event_q, stop_evt,
                  record=None, record_lock=None):
    try:
        with Camera(
            args.port, baudrate=args.baudrate, crc=args.crc, seq=args.seq,
            ack=args.ack, events=args.events, timeout=args.timeout,
            max_retry=args.max_retry, max_payload=args.max_payload,
            drop_rate=args.drop_rate,
        ) as camera:
            logging.info(f"Connected to OpenMV on {args.port}")
            camera.stop()
            if not _wait_for_script_stopped(camera, timeout=1.0, drain_stdout=True):
                logging.warning("No Script Stopped event within 1s; previous "
                                "script may still be holding hardware")

            with open(args.script) as f:
                script = f.read()
            with state_lock:
                csi_fifo    = state['csi_fifo_depth']
                evt_fifo    = state['evt_fifo_depth']
                evt_res     = state['evt_res']
                raw_mode    = state['stream_mode'] == 'Raw (fastest)'
                evt_format  = state['evt_format']
            script = patch_script(script, csi_fifo, evt_fifo, evt_res, raw_mode,
                                  evt_format)
            logging.debug(f"Patched script: CSI_FIFO={csi_fifo} EVT_FIFO={evt_fifo} "
                          f"EVT_RES={evt_res} raw={raw_mode} format={evt_format} "
                          f"readp={'yes' if sys.platform != 'win32' else 'no'}")
            camera.exec(script)
            logging.info(f"Script running, streaming events "
                         f"({('raw ' + evt_format) if raw_mode else 'processed'})...")

            channel        = 'raw_events' if raw_mode else 'events'
            # Raw word size, decoder, and carried decode state for the format.
            # EVT2.0/2.1 carry only a running EV_TIME_HIGH ([0]); EVT3.0 carries
            # a 6-element state machine array (see _decode_evt3_core).
            if evt_format == 'EVT21':
                raw_word_bytes, raw_decoder = 8, decode_raw_events_evt21
                raw_state = [0]
            elif evt_format == 'EVT30':
                raw_word_bytes, raw_decoder = 2, decode_raw_events_evt3
                raw_state = np.zeros(6, dtype=np.int64)
            elif evt_format == 'AER':
                raw_word_bytes, raw_decoder = AER_EVENT_BYTES, decode_raw_events_aer
                raw_state = None
            else:
                raw_word_bytes, raw_decoder = 4, decode_raw_events
                raw_state = [0]
            # AER frames carry trailing padding (frame size isn't a multiple of
            # 3), so a non-multiple length is expected — don't drop those frames.
            raw_allow_remainder = evt_format == 'AER'

            start_time     = time.perf_counter()
            last_time      = start_time
            total_events   = 0
            total_bytes    = 0
            event_rate_ema = 0.0
            mbps_ema       = 0.0

            while not stop_evt.is_set():
                status = camera.read_status()

                if not args.quiet and status and status.get('stdout'):
                    if text := camera.read_stdout():
                        print(f"{COLOR_CAMERA}{text}{COLOR_RESET}", end='')

                if not camera.has_channel(channel):
                    time.sleep(0.01)
                    continue

                if not status or not status.get(channel):
                    time.sleep(0.01)
                    continue

                size = camera.channel_size(channel)
                if size <= 0:
                    time.sleep(0.01)
                    continue

                now       = time.perf_counter()
                dt        = now - last_time
                last_time = now
                if dt <= 0.0:
                    continue

                data = camera.channel_read(channel, size)

                if raw_mode:
                    if (len(data) % raw_word_bytes) != 0 and not raw_allow_remainder:
                        logging.warning(f"Misaligned raw packet: {len(data)} bytes "
                                        f"(not multiple of {raw_word_bytes})")
                        continue
                    # If recording is active, append the raw byte stream before
                    # decoding. We trim each frame to a whole number of event
                    # words: for EVT2.0/2.1/3.0 the frames are exact multiples so
                    # this is a no-op, but AER frames carry a few padding bytes
                    # (frame size isn't a multiple of 3). Dropping that padding
                    # makes the recorded AER stream a clean, continuous sequence
                    # of 3-byte events that decodes without needing the frame
                    # size (see --decode).
                    if record is not None:
                        with record_lock:
                            rec_file = record['file']
                        if rec_file is not None:
                            usable   = len(data) - (len(data) % raw_word_bytes)
                            rec_bytes = data[:usable] if usable != len(data) else data
                            try:
                                rec_file.write(rec_bytes)
                                with record_lock:
                                    record['bytes'] += len(rec_bytes)
                            except Exception as e:
                                logging.error(f"Recording write failed: {e}")
                                with record_lock:
                                    try:
                                        record['file'].close()
                                    except Exception:
                                        pass
                                    record['file'] = None
                    events = raw_decoder(data, raw_state)
                else:
                    if (len(data) % 12) != 0:
                        logging.warning(f"Misaligned packet: {len(data)} bytes (not multiple of 12)")
                        continue
                    # Each event row: 6 × uint16 little-endian
                    # [0] polarity (0=neg, 1=pos)  [1] sec  [2] ms  [3] us  [4] x  [5] y
                    events = np.frombuffer(data, dtype='<u2').reshape(-1, 6)

                event_count = events.shape[0]

                events_per_sec = event_count / dt
                mb_per_sec     = len(data) / 1048576.0 / dt

                if event_rate_ema == 0.0:
                    event_rate_ema = events_per_sec
                else:
                    event_rate_ema = event_rate_ema * (1.0 - EMA_ALPHA) + events_per_sec * EMA_ALPHA

                if mbps_ema == 0.0:
                    mbps_ema = mb_per_sec
                else:
                    mbps_ema = mbps_ema * (1.0 - EMA_ALPHA) + mb_per_sec * EMA_ALPHA

                total_events += event_count
                total_bytes  += len(data)
                elapsed       = now - start_time

                stats = {
                    'event_count':  event_count,
                    'event_rate':   event_rate_ema,
                    'mbps':         mbps_ema,
                    'total_events': total_events,
                    'elapsed':      elapsed,
                }

                # Drop oldest if render loop is falling behind
                if event_q.full():
                    try:
                        event_q.get_nowait()
                    except queue.Empty:
                        pass
                event_q.put((events, stats))

            # Stop the camera-side script on clean shutdown so the next connect
            # finds the camera idle. Fire-and-forget — don't wait, since the
            # next connect's _wait_for_script_stopped handles leftover state
            # and waiting here just makes Disconnect feel sluggish (the button
            # can't flip to "Connect" until this returns).
            try:
                camera.stop()
            except Exception:
                pass

    except Exception as e:
        logging.error(f"Camera error: {e}")
        if args.debug:
            import traceback
            logging.error(traceback.format_exc())


# ---------------------------------------------------------------------------
# Processing thread  (IIR freq-cam + canvas accumulation; GIL-free hot path)
# ---------------------------------------------------------------------------

def processing_worker(state_lock, state, raw_q, result_q, stop_evt,
                      fc_L2, fc_L1, fc_p1, fc_t_ud, fc_t_du, fc_per,
                      fc_coeffs_ref, fc_t_now, reset_evt):
    """Pulls raw event batches, runs IIR filter (nogil) and canvas update, pushes results."""

    canvas    = np.full((SENSOR_H, SENSOR_W), 128, dtype=np.int32)
    slide_buf = deque()
    event_buf = deque()
    batch_counter = 0

    while not stop_evt.is_set():
        # Check for reset request from render thread
        if reset_evt.is_set():
            reset_evt.clear()
            canvas[:] = 128
            batch_counter = 0
            slide_buf.clear()
            event_buf.clear()
            fc_L2[:] = 0.0;  fc_L1[:] = 0.0;  fc_p1[:] = -1.0
            fc_t_ud[:] = 0.0; fc_t_du[:] = 0.0
            fc_per[:] = -1.0
            fc_t_now[0] = 0.0

        try:
            events, stats = raw_q.get(timeout=0.02)
        except queue.Empty:
            continue

        xs   = events[:, 4].astype(np.int32)
        ys   = events[:, 5].astype(np.int32)
        pols = events[:, 0].astype(np.int32)

        valid = (xs >= 0) & (xs < SENSOR_W) & (ys >= 0) & (ys < SENSOR_H)
        xs, ys, pols = xs[valid], ys[valid], pols[valid]

        with state_lock:
            fc_enabled = state['fc_enabled']
            fc_min  = state['fc_min_freq']
            fc_max  = state['fc_max_freq']
            fc_n_to = state['fc_n_timeout']

        batch_delta = None
        if xs.size > 0:
            signs    = pols * 2 - 1
            flat_idx = ys * SENSOR_W + xs
            pos = np.bincount(flat_idx[signs > 0], minlength=SENSOR_H * SENSOR_W)
            neg = np.bincount(flat_idx[signs < 0], minlength=SENSOR_H * SENSOR_W)
            batch_delta = (pos.astype(np.int32) - neg.astype(np.int32)).reshape(SENSOR_H, SENSOR_W)

            if fc_enabled:
                ts_f = (events[valid, 1].astype(np.float64)
                        + events[valid, 2].astype(np.float64) * 1e-3
                        + events[valid, 3].astype(np.float64) * 1e-6)
                c1, c2, c3 = fc_coeffs_ref[0], fc_coeffs_ref[1], fc_coeffs_ref[2]
                fc_dt_min      = 1.0 / max(fc_max, 1e-9)
                fc_dt_max      = 1.0 / max(fc_min, 1e-9)
                fc_dt_min_half = 0.5 * fc_dt_min
                fc_dt_max_half = 0.5 * fc_dt_max

                # GIL-free compiled IIR update
                t_last = _update_freq_cam(
                    xs.astype(np.int32), ys.astype(np.int32),
                    pols.astype(np.float64), ts_f,
                    fc_L2, fc_L1, fc_p1,
                    fc_t_ud, fc_t_du, fc_per,
                    c1, c2, c3,
                    fc_dt_min, fc_dt_max,
                    fc_dt_min_half, fc_dt_max_half,
                    float(fc_n_to),
                )
                if t_last >= 0.0:
                    fc_t_now[0] = t_last

        with state_lock:
            contrast = state['contrast']
            mode     = state['mode']
            window   = state['window']
            do_clear = state['clear']
            if do_clear:
                state['clear'] = False

        if do_clear:
            canvas[:] = 128
            batch_counter = 0
            slide_buf.clear()
            event_buf.clear()

        if mode == 'Canvas':
            if window > 0 and batch_counter >= window:
                canvas[:] = 128
                batch_counter = 0
                event_buf.clear()
            batch_counter += 1
            if batch_delta is not None:
                canvas += batch_delta * contrast
                np.clip(canvas, 0, 255, out=canvas)
                event_buf.append(events)
        else:  # Sliding Window
            w = max(1, window)
            if batch_delta is not None:
                slide_buf.append(batch_delta)
                event_buf.append(events)
            while len(slide_buf) > w:
                slide_buf.popleft()
                event_buf.popleft()
            canvas[:] = 128
            for d in slide_buf:
                canvas += d * contrast
                np.clip(canvas, 0, 255, out=canvas)

        # Only snapshot and enqueue a result if the render loop has room.
        # This avoids three expensive 320×320 array copies on every batch
        # when the render thread is already backed up.
        if not result_q.full():
            canvas_u8 = canvas.astype(np.uint8)
            result = {
                'canvas_u8':  canvas_u8,
                'fc_enabled': fc_enabled,
                'fc_per':     fc_per.copy() if fc_enabled else None,
                'fc_t_ud':    fc_t_ud.copy() if fc_enabled else None,
                'fc_t_du':    fc_t_du.copy() if fc_enabled else None,
                'fc_t_now':   fc_t_now[0],
                'event_buf':  list(event_buf),
                'stats':      stats,
            }
            result_q.put(result)


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
        description='GenX320 event camera visualization GUI')

    p.add_argument('--port',        default=None,
                   help='Serial port (auto-selected in GUI if omitted)')
    p.add_argument('--script',      default=None,
                   help='MicroPython script to run on the camera '
                        '(defaults to genx320_event_mode_streaming_on_cam.py next to this file)')
    p.add_argument('--baudrate',    type=int,   default=921600)
    p.add_argument('--timeout',     type=float, default=1.0)
    p.add_argument('--crc',         type=str2bool, nargs='?', const=True,
                   default=(sys.platform == 'win32'))
    p.add_argument('--seq',         type=str2bool, nargs='?', const=True, default=True)
    p.add_argument('--ack',         type=str2bool, nargs='?', const=True, default=False)
    p.add_argument('--events',      type=str2bool, nargs='?', const=True, default=True)
    p.add_argument('--max-retry',   type=int,   default=3)
    p.add_argument('--max-payload', type=int,   default=4096)
    p.add_argument('--drop-rate',   type=float, default=0.0)
    p.add_argument('--quiet',       action='store_true',
                   help='Suppress camera stdout')
    p.add_argument('--debug',       action='store_true')
    p.add_argument('--benchmark',   action='store_true',
                   help='Headless mode: print throughput stats, no GUI')
    p.add_argument('--raw',         type=str2bool, nargs='?', const=True, default=True,
                   help='Use raw event streaming (default: true)')
    p.add_argument('--evt-res',     type=int,   default=8192,
                   help='Event buffer resolution (default: 8192)')
    p.add_argument('--evt-format',  default='EVT30',
                   choices=[c for _, c, _ in EVT_FORMATS],
                   help='Raw event stream format (default: EVT30). Also selects '
                        'the decoder for --decode on header-less .bin files.')
    p.add_argument('--decode',      default=None, metavar='FILE',
                   help='Offline mode: decode a recorded raw file (.raw or .bin) '
                        'to events and exit (no camera/GUI). Output is CSV by '
                        'default; use --npy for a NumPy array.')
    p.add_argument('--npy',         action='store_true',
                   help='With --decode, write a .npy array instead of CSV.')
    p.add_argument('--out',         default=None, metavar='FILE',
                   help='With --decode, output path (default: input name with '
                        '.csv/.npy extension).')
    return p.parse_args()


# ---------------------------------------------------------------------------
# Offline decode  (recorded raw file -> events, no camera/GUI)
# ---------------------------------------------------------------------------

# Per-format byte stride and decoder, plus a fresh carried-state factory.
_DECODERS = {
    'EVT20': (4, decode_raw_events,       lambda: [0]),
    'EVT21': (8, decode_raw_events_evt21, lambda: [0]),
    'EVT30': (2, decode_raw_events_evt3,  lambda: np.zeros(6, dtype=np.int64)),
    'AER':   (AER_EVENT_BYTES, decode_raw_events_aer, lambda: None),
}

# Metavision header token (`% format` / `% evt`) -> internal format code.
_MV_TOKEN_TO_CODE = {}
for _code, _info in EVT_METAVISION.items():
    _MV_TOKEN_TO_CODE[_info['fmt'].upper()] = _code            # EVT3   -> EVT30
    _MV_TOKEN_TO_CODE['EVT' + _info['evt'].replace('.', '')] = _code  # 3.0 -> EVT30


def _decode_buffer(evt_format, data):
    """Decode a raw byte buffer to the (N, 6) uint16 event array.

    Processed in word-aligned chunks so vector-format expansion (EVT2.1/3.0)
    can't balloon peak memory on a whole-file decode; the decoders carry state
    across chunks, so the result is identical to a single call.
    """
    stride, dec, make_state = _DECODERS[evt_format]
    state = make_state()
    n = len(data) - (len(data) % stride)
    chunk = (1 << 18) * stride
    parts = []
    for off in range(0, n, chunk):
        out = dec(data[off:min(off + chunk, n)], state)
        if out.shape[0]:
            parts.append(out)
    if not parts:
        return np.zeros((0, 6), dtype=np.uint16)
    return parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)


def run_decode(args):
    """Decode a recorded raw file to CSV (default) or .npy, then exit."""
    path = args.decode
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError as e:
        sys.exit(f"Cannot read {path}: {e}")

    evt_format = args.evt_format
    # Metavision RAW files begin with an ASCII '% ...' header; skip it and read
    # the format from it. Header-less .bin files fall back to --evt-format.
    if data[:1] == b'%':
        end = data.find(b'% end')
        if end == -1:
            sys.exit(f"{path}: looks like Metavision RAW but has no '% end' marker.")
        nl   = data.find(b'\n', end)
        head = data[:nl].decode('ascii', 'replace')
        data = data[nl + 1:]
        detected = None
        for line in head.splitlines():
            if line.startswith('% format'):
                detected = _MV_TOKEN_TO_CODE.get(line.split()[2].split(';')[0].upper())
            elif line.startswith('% evt') and detected is None:
                detected = _MV_TOKEN_TO_CODE.get('EVT' + line.split()[2].replace('.', ''))
        if detected:
            evt_format = detected
            logging.info(f"Detected {evt_format} from Metavision header")
        else:
            logging.warning(f"No format in header; using --evt-format {evt_format}")

    events = _decode_buffer(evt_format, data)

    out = args.out
    if out is None:
        out = os.path.splitext(path)[0] + ('.npy' if args.npy else '.csv')
    if args.npy:
        np.save(out, events)
    else:
        np.savetxt(out, events, fmt='%d', delimiter=',',
                   header='type,sec,ms,us,x,y', comments='')
    print(f"Decoded {len(events):,} events ({evt_format}) from {path} -> {out}")


# ---------------------------------------------------------------------------
# main  (render / GUI thread)
# ---------------------------------------------------------------------------

def run_benchmark(args):
    """Headless benchmark: camera + processing threads, stats printed to terminal."""
    if not args.port:
        ports = list_com_ports()
        if not ports:
            print("No serial ports found. Use --port to specify one.")
            sys.exit(1)
        args.port = ports[0]
        print(f"Auto-selected port: {args.port}")

    state_lock = threading.Lock()
    state = {
        'stream_mode':    'Raw (fastest)' if args.raw else 'Processed',
        'csi_fifo_depth': 8,
        'evt_fifo_depth': 8,
        'evt_res':        args.evt_res,
        'evt_format':     args.evt_format,
        'contrast':       16,
        'color_mode':     'Grayscale',
        'mode':           'Sliding Window',
        'window':         4,
        'clear':          False,
        'fc_cutoff_period': 5.0,
        'fc_enabled':       True,
        'fc_min_freq':      10.0,
        'fc_max_freq':      1000.0,
        'fc_n_timeout':     2,
        'fc_log_freq':      True,
        'fc_overlay':       False,
        'fc_legend_show':   False,
        'fc_legend_bins':   11,
    }

    if args.script is None:
        raw_mode = state['stream_mode'] == 'Raw (fastest)'
        args.script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'genx320_raw_event_mode_streaming_on_cam.py' if raw_mode
            else 'genx320_event_mode_streaming_on_cam.py',
        )

    fc_L2        = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float32)
    fc_L1        = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float32)
    fc_p1        = np.full((SENSOR_H, SENSOR_W), -1.0, dtype=np.float32)
    fc_t_ud      = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float64)
    fc_t_du      = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float64)
    fc_per       = np.full((SENSOR_H, SENSOR_W), -1.0, dtype=np.float64)
    fc_coeffs = list(_freq_filter_coeffs(state['fc_cutoff_period']))
    fc_t_now  = [0.0]

    raw_q    = queue.Queue(maxsize=8)
    result_q = queue.Queue(maxsize=4)
    reset_evt = threading.Event()
    stop_evt  = threading.Event()

    def handle_exit(signum, frame):
        stop_evt.set()

    signal.signal(signal.SIGINT,  handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    cam_t = threading.Thread(
        target=camera_worker,
        args=(args, state_lock, state, raw_q, stop_evt),
        daemon=True,
    )
    proc_t = threading.Thread(
        target=processing_worker,
        args=(state_lock, state, raw_q, result_q, stop_evt,
              fc_L2, fc_L1, fc_p1, fc_t_ud, fc_t_du, fc_per,
              fc_coeffs, fc_t_now, reset_evt),
        daemon=True,
    )

    print(f"Connecting to {args.port} ...")

    cam_t.start()
    proc_t.start()

    last_print = time.perf_counter()
    while not stop_evt.is_set():
        try:
            result = result_q.get(timeout=0.05)
        except queue.Empty:
            if not cam_t.is_alive():
                if not stop_evt.is_set():
                    print("Camera thread died unexpectedly.")
                break
            continue

        now = time.perf_counter()
        if now - last_print >= 0.1:
            last_print = now
            s = result['stats']
            print(f"elapsed={s['elapsed']:.1f}s\t"
                  f"rate={s['event_rate']:,.0f} ev/s\t"
                  f"bw={s['mbps']:.2f} MB/s\t"
                  f"total={s['total_events']:,}")

    stop_evt.set()
    print("\nDone.")


def main(args=None):
    if args is None:
        args = parse_args()

    if args.script is None:
        args.script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'genx320_event_mode_streaming_on_cam.py',
        )

    logging.basicConfig(
        format="%(relativeCreated)010.3f - %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
    )

    # Shared state accessed by GUI callbacks and camera thread
    state_lock = threading.Lock()
    state = {
        # Camera script parameters (locked while connected)
        'stream_mode':    'Raw (fastest)' if args.raw else 'Processed',
        'csi_fifo_depth': 8,
        'evt_fifo_depth': 8,
        'evt_res':        args.evt_res,
        'evt_format':     args.evt_format,   # raw mode only: EVT20/EVT21/...
        # Visualization
        'contrast':   16,
        'color_mode': 'Grayscale',
        'mode':       'Sliding Window',   # 'Canvas' or 'Sliding Window'
        'window':     4,                  # Canvas: batches before auto-clear (0=manual); Sliding Window: batches to keep (min 1)
        'clear':      False,
        # Frequency visualization
        'fc_enabled':       True,
        'fc_cutoff_period': 5.0,
        'fc_min_freq':      10.0,
        'fc_max_freq':      1000.0,
        'fc_n_timeout':     2,
        'fc_log_freq':      True,
        'fc_overlay':       False,
        'fc_legend_show':   True,
        'fc_legend_bins':   11,
    }

    last_canvas_u8  = [None]   # latest rendered uint8 canvas, for saving
    last_freq_rgba  = [None]   # latest freq texture (H×W×4 float32), for saving
    event_buf      = deque()  # raw event arrays from last result, for saving

    # Frequency camera per-pixel IIR filter state (owned by processing_worker).
    # Allocated here so they can be passed to the thread at connect time.
    # fc_p1  : previous raw polarity (0 or 1); dp = p - p1 drives the filter
    # fc_t_ud: time of last L+ → L− zero crossing ("up-down")
    # fc_t_du: time of last L− → L+ zero crossing ("down-up")
    # fc_per : estimated period; -1 = uninitialized, 0 = stale, >0 = valid
    fc_L2        = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float32)
    fc_L1        = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float32)
    fc_p1        = np.full((SENSOR_H, SENSOR_W), -1.0, dtype=np.float32)  # ±1 convention, init -1
    fc_t_ud      = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float64)
    fc_t_du      = np.zeros((SENSOR_H, SENSOR_W), dtype=np.float64)
    fc_per       = np.full((SENSOR_H, SENSOR_W), -1.0, dtype=np.float64)
    fc_coeffs = list(_freq_filter_coeffs(state['fc_cutoff_period']))
    fc_t_now  = [0.0]   # last camera timestamp processed

    # Lock-free mirrors of state, readable by fit_image() without taking the lock
    fc_enabled_ref      = [state['fc_enabled']]
    fc_legend_show_ref  = [state['fc_legend_show']]
    legend_redraw_needed = [True]

    raw_q    = queue.Queue(maxsize=8)   # camera → processing (larger: absorb bursts)
    result_q = queue.Queue(maxsize=4)   # processing → render
    reset_evt = threading.Event()       # render → processing: reset filter/canvas state
    conn     = {'cam_thread': None, 'proc_thread': None, 'stop_evt': None}

    # Raw recording state (only used in raw stream mode). camera_worker writes
    # the EVT 2.0 byte stream verbatim into record['file'] when set.
    record      = {'file': None, 'path': None, 'bytes': 0, 'start': 0.0}
    record_lock = threading.Lock()

    # -----------------------------------------------------------------------
    # Dear PyGui setup
    # -----------------------------------------------------------------------
    dpg.create_context()

    def cb_file_selected(sender, app_data):
        path = app_data.get('file_path_name', '')
        if path:
            args.script = path
            dpg.set_value("script_path", path)

    with dpg.file_dialog(
            directory_selector=False, show=False,
            callback=cb_file_selected, tag="file_dialog",
            width=700, height=450,
            default_path=os.path.dirname(args.script) if args.script else os.getcwd()):
        dpg.add_file_extension(".py", color=(100, 255, 100, 255))
        dpg.add_file_extension(".*",  color=(255, 255, 255, 255))

    # Placeholder texture (mid-gray, matching canvas init value)
    _ph = np.full(SENSOR_W * SENSOR_H * 4, 0.5, dtype=np.float32)
    _ph[3::4] = 1.0
    with dpg.texture_registry(tag=TEX_REG_TAG):
        dpg.add_dynamic_texture(SENSOR_W, SENSOR_H, _ph, tag=TEXTURE_TAG)
        _ph_freq = np.zeros(SENSOR_W * SENSOR_H * 4, dtype=np.float32)
        _ph_freq[3::4] = 1.0
        dpg.add_dynamic_texture(SENSOR_W, SENSOR_H, _ph_freq, tag=FREQ_TEX_TAG)
    tex_wh = [SENSOR_W, SENSOR_H]

    # ---- Connection callbacks ----------------------------------------------

    def do_connect(port):
        args.port = port
        # Select cam script based on stream mode
        script_dir = os.path.dirname(os.path.abspath(__file__))
        with state_lock:
            raw_mode = state['stream_mode'] == 'Raw (fastest)'
        cam_script = os.path.join(
            script_dir,
            'genx320_raw_event_mode_streaming_on_cam.py' if raw_mode
            else 'genx320_event_mode_streaming_on_cam.py',
        )
        args.script = cam_script
        dpg.set_value("script_path", cam_script)
        last_freq_rgba[0] = None
        reset_evt.set()   # processing_worker will reset filter/canvas on startup
        stop_evt         = threading.Event()
        conn['stop_evt'] = stop_evt

        cam_t = threading.Thread(
            target=camera_worker,
            args=(args, state_lock, state, raw_q, stop_evt, record, record_lock),
            daemon=True,
        )
        proc_t = threading.Thread(
            target=processing_worker,
            args=(state_lock, state, raw_q, result_q, stop_evt,
                  fc_L2, fc_L1, fc_p1, fc_t_ud, fc_t_du, fc_per,
                  fc_coeffs, fc_t_now, reset_evt),
            daemon=True,
        )
        cam_t.start()
        proc_t.start()
        conn['cam_thread']  = cam_t
        conn['proc_thread'] = proc_t
        dpg.configure_item("connect_btn", label="Disconnect")
        _set_cam_settings_enabled(False)
        # The Record Raw Events button is only meaningful in raw stream mode.
        dpg.configure_item("record_btn", enabled=raw_mode,
                           label="Record Raw Events")
        logging.info(f"Connecting to {port}...")

    def do_disconnect():
        if conn['stop_evt']:
            conn['stop_evt'].set()
        # Wait for the worker threads to release the serial port and finish
        # before the user can click Connect again — otherwise the new
        # connection races the old one for /dev/ttyACM*.
        for key in ('cam_thread', 'proc_thread'):
            t = conn[key]
            if t is not None and t.is_alive():
                t.join(timeout=3.0)
                if t.is_alive():
                    logging.warning(f"{key} did not exit cleanly within 3s")
        conn['cam_thread']  = None
        conn['proc_thread'] = None
        conn['stop_evt']    = None
        # Close any active recording so we don't leak a half-written file.
        _stop_recording()
        dpg.configure_item("record_btn", enabled=False,
                           label="Record Raw Events")
        dpg.configure_item("record_format_combo", enabled=True)
        dpg.configure_item("connect_btn", label="Connect")
        _set_cam_settings_enabled(True)

    CAM_SETTING_TAGS = ["stream_mode_combo", "evt_format_combo",
                        "csi_fifo_input", "evt_fifo_input"]

    def _set_cam_settings_enabled(enabled):
        for tag in CAM_SETTING_TAGS:
            dpg.configure_item(tag, enabled=enabled)
        # Swap combo ↔ readonly text — DearPyGui clears combo preview on disable
        if enabled:
            dpg.show_item("evt_res_combo")
            dpg.hide_item("evt_res_display")
        else:
            with state_lock:
                val = str(state['evt_res'])
            dpg.set_value("evt_res_display", val)
            dpg.hide_item("evt_res_combo")
            dpg.show_item("evt_res_display")

    def cb_refresh(s, v, u=None):
        items = list_com_ports()
        dpg.configure_item("port_combo", items=items)
        if items and not dpg.get_value("port_combo"):
            dpg.set_value("port_combo", items[0])

    def cb_connect(s, v, u=None):
        if conn['cam_thread'] and conn['cam_thread'].is_alive():
            do_disconnect()
        else:
            if not args.script:
                return
            port = dpg.get_value("port_combo")
            if not port:
                return
            do_connect(port)

    # ---- Camera settings callbacks (applied at connect time) ---------------

    STREAM_MODES = ['Raw (fastest)', 'Processed']

    RECORD_FMT_METAVISION = 'Metavision RAW (.raw)'
    RECORD_FMT_VERBATIM   = 'Verbatim (.bin)'
    RECORD_FORMATS        = [RECORD_FMT_METAVISION, RECORD_FMT_VERBATIM]

    def cb_stream_mode(s, v, u=None):
        with state_lock:
            state['stream_mode'] = v
        raw = v == 'Raw (fastest)'
        # EVT FIFO only applies to the processed cam script; the event format
        # selector only applies to the raw cam script.
        (dpg.hide_item if raw else dpg.show_item)("evt_fifo_row")
        (dpg.show_item if raw else dpg.hide_item)("evt_format_row")

    def cb_evt_format(s, v, u=None):
        # Any format flagged not-ready in EVT_FORMATS reverts to the previous
        # selection (kept for future decode-pending formats). All current
        # formats are decodable, so this guard is a no-op today.
        if not EVT_LABEL_READY.get(v, False):
            with state_lock:
                prev = EVT_CODE_TO_LABEL[state['evt_format']]
            dpg.set_value("evt_format_combo", prev)
            logging.info(f"{v} decoding is not implemented yet — "
                         f"keeping {prev}.")
            return
        with state_lock:
            state['evt_format'] = EVT_LABEL_TO_CODE[v]

    def cb_csi_fifo(s, v, u=None):
        with state_lock:
            state['csi_fifo_depth'] = max(4, v)

    def cb_evt_fifo(s, v, u=None):
        with state_lock:
            state['evt_fifo_depth'] = max(4, v)

    def cb_evt_res(s, v, u=None):
        with state_lock:
            state['evt_res'] = int(v)

    # ---- Visualization callbacks -------------------------------------------

    # Per-mode window memory: remembered independently so switching back restores last value
    window_by_mode = {'Sliding Window': 4, 'Canvas': 0}

    def _sync_window_ui(window_val, mode):
        """Update window input value/min and show Clear button only for Canvas+0."""
        dpg.configure_item("window_input", min_value=(0 if mode == 'Canvas' else 1))
        dpg.set_value("window_input", window_val)
        show_clear = (mode == 'Canvas' and window_val == 0)
        (dpg.show_item if show_clear else dpg.hide_item)("clear_btn")

    def cb_clear(s=None, v=None, u=None):
        with state_lock:
            state['clear'] = True

    def cb_contrast(s, v, u=None):
        with state_lock:
            state['contrast'] = v

    def cb_color_mode(s, v, u=None):
        with state_lock:
            state['color_mode'] = v

    def cb_mode(s, v, u=None):
        # Save current window value for the old mode, restore for the new mode
        with state_lock:
            old_mode = state['mode']
            window_by_mode[old_mode] = state['window']
            w = window_by_mode[v]
            state['mode']   = v
            state['window'] = w
            state['clear']  = True
        _sync_window_ui(w, v)

    def cb_window(s, v, u=None):
        with state_lock:
            state['window'] = v
            mode = state['mode']
            window_by_mode[mode] = v
        _sync_window_ui(v, mode)

    def _stop_recording():
        """Close the active raw-events recording file, if any. Idempotent."""
        with record_lock:
            f       = record['file']
            path    = record['path']
            written = record['bytes']
            elapsed = time.perf_counter() - record['start'] if f else 0.0
            record['file']  = None
            record['path']  = None
            record['bytes'] = 0
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
            logging.info(f"Recording stopped: {path} "
                         f"({written:,} bytes, {elapsed:.1f}s)")

    def cb_record(s=None, v=None, u=None):
        # Toggle recording. Button only fires when enabled, which is only true
        # while connected in Raw stream mode.
        with record_lock:
            recording = record['file'] is not None
        if recording:
            _stop_recording()
            dpg.configure_item("record_btn", label="Record Raw Events")
            dpg.configure_item("record_format_combo", enabled=True)
            return
        # Start a new recording. Format is selected via the combo:
        #   Metavision RAW (.raw) — ASCII header + raw event stream, opens in
        #                           Prophesee's metavision_viewer / OpenEB. The
        #                           `% format` line tracks the selected format.
        #   Verbatim (.bin)       — header-less byte-for-byte sensor stream.
        fmt          = dpg.get_value("record_format_combo")
        is_metavision = fmt == RECORD_FMT_METAVISION
        with state_lock:
            evt_format = state['evt_format']
        mv = EVT_METAVISION.get(evt_format)
        # AER is not a Metavision RAW format; fall back to a header-less verbatim
        # dump rather than writing a file with a misleading header.
        if is_metavision and mv is None:
            logging.warning(f"{evt_format} has no Metavision RAW format — "
                            f"recording a verbatim .bin instead.")
            is_metavision = False
        ts           = time.strftime("%Y%m%d_%H%M%S")
        path         = f"events_{ts}.raw" if is_metavision else f"events_{ts}_raw.bin"
        try:
            f = open(path, "wb")
        except Exception as e:
            logging.error(f"Failed to open {path} for recording: {e}")
            return
        if is_metavision:
            # Metavision RAW header (ASCII, terminated by `% end`). The body that
            # follows is the verbatim sensor stream. OpenEB / metavision_viewer
            # decode it from `% format` (modern) or `% evt` (legacy); both are
            # written for compatibility, along with the sensor geometry.
            date_str = time.strftime("%Y-%m-%d %H:%M:%S")
            header = (
                f"% camera_integrator_name OpenMV\n"
                f"% date {date_str}\n"
                f"% evt {mv['evt']}\n"
                f"% format {mv['fmt']};height={SENSOR_H};width={SENSOR_W}\n"
                f"% geometry {SENSOR_W}x{SENSOR_H}\n"
                f"% integrator_name OpenMV\n"
                f"% plugin_integrator_name OpenMV\n"
                f"% end\n"
            )
            f.write(header.encode('ascii'))
        with record_lock:
            record['file']  = f
            record['path']  = path
            record['bytes'] = 0
            record['start'] = time.perf_counter()
        dpg.configure_item("record_btn", label="Stop Recording")
        # Lock format selection while a recording is in progress.
        dpg.configure_item("record_format_combo", enabled=False)
        logging.info(f"Recording raw events to {path}")

    def cb_save(s=None, v=None, u=None):
        img      = last_canvas_u8[0]
        freq_img = last_freq_rgba[0]
        if img is None:
            return
        with state_lock:
            color_mode   = state['color_mode']
            legend_show  = state['fc_legend_show']
            legend_bins  = state['fc_legend_bins']
            fc_min       = state['fc_min_freq']
            fc_max       = state['fc_max_freq']
            fc_log_freq  = state['fc_log_freq']
        ts   = int(time.time())
        base = f"events_{ts}"

        if not _PIL_AVAILABLE:
            logging.warning("pip install Pillow to enable image saving")
            return

        try:
            # Save event canvas image
            if color_mode == "Grayscale":
                pil_evt = Image.fromarray(img, 'L')
            else:
                rgb = (EVT_DARK_RGB if color_mode == "Evt Dark" else EVT_LIGHT_RGB)[img]
                pil_evt = Image.fromarray(rgb, 'RGB')
            pil_evt.save(f"{base}_evt.png")
            logging.info(f"Saved {base}_evt.png")

            # Save frequency image, compositing legend onto the right if enabled
            if freq_img is not None:
                freq_u8  = (np.clip(freq_img[:, :, :3], 0.0, 1.0) * 255).astype(np.uint8)
                pil_freq = Image.fromarray(freq_u8, 'RGB')
                if legend_show:
                    legend_pil = _make_freq_legend_pil(
                        SENSOR_H, fc_min, fc_max, fc_log_freq, legend_bins)
                    combined = Image.new('RGB', (SENSOR_W + LEGEND_DW, SENSOR_H))
                    combined.paste(pil_freq,   (0,        0))
                    combined.paste(legend_pil, (SENSOR_W, 0))
                    combined.save(f"{base}_freq.png")
                else:
                    pil_freq.save(f"{base}_freq.png")
                logging.info(f"Saved {base}_freq.png")

        except Exception as e:
            logging.warning(f"Failed to save images: {e}")

        # Save raw events as CSV
        batches = list(event_buf)
        if batches:
            all_events = np.concatenate(batches, axis=0)
            csv_path   = f"{base}.csv"
            np.savetxt(
                csv_path, all_events,
                delimiter=',', fmt='%d',
                header='type,sec,ms,us,x,y', comments='',
            )
            logging.info(f"Saved {csv_path}  ({len(all_events):,} events)")

    # ---- Frequency camera callbacks ----------------------------------------

    def cb_fc_enabled(s, v, u=None):
        with state_lock:
            state['fc_enabled'] = v
        fc_enabled_ref[0] = v
        dpg.configure_item("fc_controls", show=v)
        for tag in ("freq_img_h", "freq_img_v", "freq_legend_h", "freq_legend_v"):
            (dpg.show_item if v else dpg.hide_item)(tag)
        if not v:
            last_freq_rgba[0] = None
        dpg.configure_item("save_btn",
                           label="Save Images and Events" if v else "Save Image and Events")
        fit_image()

    def cb_fc_cutoff(s, v, u=None):
        with state_lock:
            state['fc_cutoff_period'] = v
        fc_coeffs[:] = list(_freq_filter_coeffs(v))

    def cb_fc_min_freq(s, v, u=None):
        with state_lock:
            state['fc_min_freq'] = max(v, 0.01)
        legend_redraw_needed[0] = True

    def cb_fc_max_freq(s, v, u=None):
        with state_lock:
            state['fc_max_freq'] = max(v, 1.0)
        legend_redraw_needed[0] = True

    def cb_fc_n_timeout(s, v, u=None):
        with state_lock:
            state['fc_n_timeout'] = max(v, 1)


    def cb_fc_log_freq(s, v, u=None):
        with state_lock:
            state['fc_log_freq'] = v
        legend_redraw_needed[0] = True

    def cb_fc_overlay(s, v, u=None):
        with state_lock:
            state['fc_overlay'] = v

    def cb_fc_legend_bins(s, v, u=None):
        with state_lock:
            state['fc_legend_bins'] = max(v, 2)
        legend_redraw_needed[0] = True

    def cb_fc_legend_show(s, v, u=None):
        with state_lock:
            state['fc_legend_show'] = v
        fc_legend_show_ref[0] = v
        dpg.configure_item("freq_legend_h", show=v)
        dpg.configure_item("freq_legend_v", show=v)
        legend_redraw_needed[0] = True
        fit_image()

    def cb_fc_reset(s=None, v=None, u=None):
        reset_evt.set()   # processing_worker handles the actual reset safely

    # ---- UI layout ---------------------------------------------------------

    with dpg.window(tag="main_win", no_scrollbar=True, no_title_bar=True):
        with dpg.table(
            header_row=False, resizable=True,
            borders_innerV=True, tag="layout_table",
            scrollX=False, scrollY=False,
        ):
            dpg.add_table_column(init_width_or_weight=1.0)
            dpg.add_table_column(init_width_or_weight=CTRL_WIDTH, width_fixed=True)

            with dpg.table_row():

                # ── Left: event canvas ─────────────────────────────────────
                with dpg.table_cell():
                    # Horizontal layout (side by side)
                    with dpg.group(horizontal=True, tag="images_horiz"):
                        dpg.add_image(TEXTURE_TAG,  tag="evt_img_h",
                                      width=SENSOR_W, height=SENSOR_H)
                        dpg.add_image(FREQ_TEX_TAG, tag="freq_img_h",
                                      width=SENSOR_W, height=SENSOR_H)
                        dpg.add_drawlist(tag="freq_legend_h",
                                         width=LEGEND_DW, height=SENSOR_H)
                    # Vertical layout (stacked), hidden initially
                    with dpg.group(tag="images_vert", show=False):
                        dpg.add_image(TEXTURE_TAG,  tag="evt_img_v",
                                      width=SENSOR_W, height=SENSOR_H)
                        with dpg.group(horizontal=True):
                            dpg.add_image(FREQ_TEX_TAG, tag="freq_img_v",
                                          width=SENSOR_W, height=SENSOR_H)
                            dpg.add_drawlist(tag="freq_legend_v",
                                             width=LEGEND_DW, height=SENSOR_H)

                # ── Right: controls ─────────────────────────────────────────
                with dpg.table_cell():
                    with dpg.child_window(width=CTRL_WIDTH, border=False):

                        # ── Windows performance warning ──────────────────────
                        if sys.platform == 'win32':
                            dpg.add_text(
                                "Warning: Windows reduces transfer speed.\n"
                                "Use macOS or Linux for best performance.",
                                color=(255, 200, 0, 255))
                            dpg.add_separator()

                        # ── Connection ──────────────────────────────────────
                        with dpg.group():
                            with dpg.group(horizontal=True):
                                dpg.add_text("Script")
                                dpg.add_input_text(
                                    tag="script_path",
                                    default_value=args.script or "",
                                    hint="select a .py script...",
                                    width=CTRL_WIDTH - 112, readonly=True)
                                dpg.add_button(
                                    label="...", width=28,
                                    callback=lambda: dpg.show_item("file_dialog"))

                            init_ports = list_com_ports()
                            init_port  = args.port or (init_ports[0] if init_ports else "")
                            with dpg.group(horizontal=True):
                                dpg.add_text("Port  ")
                                dpg.add_combo(
                                    items=init_ports, default_value=init_port,
                                    tag="port_combo", width=CTRL_WIDTH - 112)
                                dpg.add_button(label="Ref", callback=cb_refresh, width=28)

                        # ── Camera script parameters ────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Camera Parameters  (applied at connect)")

                        with dpg.group(horizontal=True):
                            dpg.add_text("Stream   ")
                            dpg.add_combo(
                                tag="stream_mode_combo",
                                items=STREAM_MODES,
                                default_value=state['stream_mode'],
                                callback=cb_stream_mode, width=-1)

                        with dpg.group(horizontal=True, tag="evt_format_row",
                                       show=state['stream_mode'] == 'Raw (fastest)'):
                            dpg.add_text("Format   ")
                            dpg.add_combo(
                                tag="evt_format_combo",
                                items=EVT_FORMAT_LABELS,
                                default_value=EVT_CODE_TO_LABEL[state['evt_format']],
                                callback=cb_evt_format, width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("CSI FIFO ")
                            dpg.add_input_int(
                                tag="csi_fifo_input", label="##csi_fifo",
                                default_value=state['csi_fifo_depth'],
                                min_value=4, min_clamped=True,
                                step=1, step_fast=4,
                                callback=cb_csi_fifo, width=-1)

                        with dpg.group(horizontal=True, tag="evt_fifo_row", show=False):
                            dpg.add_text("EVT FIFO ")
                            dpg.add_input_int(
                                tag="evt_fifo_input", label="##evt_fifo",
                                default_value=state['evt_fifo_depth'],
                                min_value=4, min_clamped=True,
                                step=1, step_fast=4,
                                callback=cb_evt_fifo, width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("EVT Buffer")
                            dpg.add_combo(
                                tag="evt_res_combo",
                                items=[str(v) for v in EVT_RES_OPTIONS],
                                default_value=str(state['evt_res']),
                                callback=cb_evt_res, width=-1)
                            dpg.add_input_text(
                                tag="evt_res_display",
                                default_value=str(state['evt_res']),
                                readonly=True, show=False, width=-1)

                        dpg.add_separator()
                        dpg.add_button(label="Connect", tag="connect_btn",
                                       callback=cb_connect, width=-1)

                        # ── Event Visualization ─────────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Event Visualization")

                        with dpg.group(horizontal=True):
                            dpg.add_text("Contrast ")
                            dpg.add_input_int(
                                label="##contrast",
                                default_value=state['contrast'],
                                min_value=1, max_value=128,
                                min_clamped=True, max_clamped=True,
                                step=1, step_fast=8,
                                callback=cb_contrast, width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Color    ")
                            dpg.add_combo(
                                items=COLOR_MODES,
                                default_value=state['color_mode'],
                                tag="color_mode_combo",
                                callback=cb_color_mode,
                                width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Mode     ")
                            dpg.add_combo(
                                items=["Sliding Window", "Canvas"],
                                default_value=state['mode'],
                                tag="mode_combo",
                                callback=cb_mode,
                                width=-1)

                        with dpg.group(horizontal=True):
                            dpg.add_text("Window   ")
                            dpg.add_input_int(
                                tag="window_input",
                                label="##window",
                                default_value=state['window'],
                                min_value=1,
                                min_clamped=True,
                                step=1, step_fast=10,
                                callback=cb_window, width=-60)
                            dpg.add_button(label="Clear", tag="clear_btn",
                                           callback=cb_clear, width=50, show=False)

                        # ── Frequency Visualization ─────────────────────────
                        with dpg.group(horizontal=True):
                            dpg.add_checkbox(tag="fc_enabled_check",
                                             default_value=state['fc_enabled'],
                                             callback=cb_fc_enabled)
                            dpg.add_text("Frequency Visualization")

                        with dpg.group(tag="fc_controls", show=state['fc_enabled']):
                            with dpg.group(horizontal=True):
                                dpg.add_text("Cutoff T ")
                                dpg.add_input_float(
                                    tag="fc_cutoff_input", label="##fc_cutoff",
                                    default_value=state['fc_cutoff_period'],
                                    min_value=1.0, min_clamped=True,
                                    step=0.5, step_fast=5.0,
                                    callback=cb_fc_cutoff, width=-1)

                            with dpg.group(horizontal=True):
                                dpg.add_text("Min Hz   ")
                                dpg.add_input_float(
                                    tag="fc_min_input", label="##fc_min",
                                    default_value=state['fc_min_freq'],
                                    min_value=0.01, min_clamped=True,
                                    step=1.0, step_fast=10.0,
                                    callback=cb_fc_min_freq, width=-1)

                            with dpg.group(horizontal=True):
                                dpg.add_text("Max Hz   ")
                                dpg.add_input_float(
                                    tag="fc_max_input", label="##fc_max",
                                    default_value=state['fc_max_freq'],
                                    min_value=1.0, min_clamped=True,
                                    step=10.0, step_fast=100.0,
                                    callback=cb_fc_max_freq, width=-1)

                            with dpg.group(horizontal=True):
                                dpg.add_text("Timeout  ")
                                dpg.add_input_int(
                                    tag="fc_timeout_input", label="##fc_timeout",
                                    default_value=state['fc_n_timeout'],
                                    min_value=1, min_clamped=True,
                                    step=1,
                                    callback=cb_fc_n_timeout, width=-60)
                                dpg.add_button(label="Reset", tag="fc_reset_btn",
                                               callback=cb_fc_reset, width=50)

                            with dpg.group(horizontal=True):
                                dpg.add_checkbox(tag="fc_log_check",
                                                 default_value=state['fc_log_freq'],
                                                 callback=cb_fc_log_freq)
                                dpg.add_text("Log frequency scale")

                            with dpg.group(horizontal=True):
                                dpg.add_checkbox(tag="fc_overlay_check",
                                                 default_value=state['fc_overlay'],
                                                 callback=cb_fc_overlay)
                                dpg.add_text("Overlay active pixels")

                            with dpg.group(horizontal=True):
                                dpg.add_checkbox(tag="fc_legend_check",
                                                 default_value=state['fc_legend_show'],
                                                 callback=cb_fc_legend_show)
                                dpg.add_text("Show legend")

                            with dpg.group(horizontal=True):
                                dpg.add_text("Bins     ")
                                dpg.add_input_int(
                                    tag="fc_legend_bins_input", label="##fc_legend_bins",
                                    default_value=state['fc_legend_bins'],
                                    min_value=2, min_clamped=True,
                                    step=1, step_fast=5,
                                    callback=cb_fc_legend_bins, width=-1)

                        # ── Save ────────────────────────────────────────────
                        dpg.add_separator()
                        dpg.add_button(label="Save Images and Events",
                                       tag="save_btn", callback=cb_save, width=-1)
                        with dpg.group(horizontal=True):
                            dpg.add_text("File  ")
                            dpg.add_combo(RECORD_FORMATS,
                                          tag="record_format_combo",
                                          default_value=RECORD_FMT_METAVISION,
                                          width=-1)
                        dpg.add_button(label="Record Raw Events",
                                       tag="record_btn", callback=cb_record,
                                       width=-1, enabled=False)

                        # ── Stats ───────────────────────────────────────────
                        dpg.add_separator()
                        dpg.add_text("Statistics")
                        with dpg.table(header_row=False, borders_innerV=False,
                                       policy=dpg.mvTable_SizingFixedFit):
                            dpg.add_table_column(init_width_or_weight=95,  width_fixed=True)
                            dpg.add_table_column(init_width_or_weight=150, width_fixed=True)
                            for lbl, tag in [
                                ("Events/batch", "stat_ev_batch"),
                                ("Rate",         "stat_rate"),
                                ("Bandwidth",    "stat_bw"),
                                ("Total events", "stat_total"),
                                ("Uptime",       "stat_uptime"),
                            ]:
                                with dpg.table_row():
                                    dpg.add_text(lbl)
                                    dpg.add_text("—", tag=tag)


    dpg.create_viewport(title="GenX320 Event Viewer",
                        width=1440, height=900, resizable=True)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main_win", True)

    def handle_exit(signum, frame):
        if conn['stop_evt']:
            conn['stop_evt'].set()
        dpg.stop_dearpygui()

    signal.signal(signal.SIGINT,  handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    if args.port and args.script:
        do_connect(args.port)

    # Apply initial UI state (default mode is Sliding Window, so C button stays hidden)
    _sync_window_ui(state['window'], state['mode'])

    disp_wh = [0, 0, None]   # [dw, dh, layout ('h' or 'v')]

    def fit_image():
        fw, fh = tex_wh
        if fw <= 0 or fh <= 0:
            return
        fc_en     = fc_enabled_ref[0]
        legend_dw = (LEGEND_DW if fc_legend_show_ref[0] else 0) if fc_en else 0
        n_images  = 2 if fc_en else 1
        avail_w = max(dpg.get_viewport_width()  - CTRL_WIDTH - 30 - legend_dw, 1)
        avail_h = max(dpg.get_viewport_height() - 60, 1)

        # Scale for each arrangement; pick whichever makes images larger
        scale_h = min(avail_w / (n_images * fw), avail_h / fh)           # side by side
        scale_v = min(avail_w / fw,               avail_h / (n_images * fh))  # stacked

        if scale_h >= scale_v:
            layout = 'h'
            scale  = scale_h
        else:
            layout = 'v'
            scale  = scale_v

        dw, dh = max(int(fw * scale), 1), max(int(fh * scale), 1)
        if [dw, dh, layout] != disp_wh:
            disp_wh[0], disp_wh[1], disp_wh[2] = dw, dh, layout
            if layout == 'h':
                dpg.show_item("images_horiz")
                dpg.hide_item("images_vert")
                dpg.configure_item("evt_img_h",  width=dw, height=dh)
                dpg.configure_item("freq_img_h", width=dw, height=dh)
            else:
                dpg.hide_item("images_horiz")
                dpg.show_item("images_vert")
                dpg.configure_item("evt_img_v",  width=dw, height=dh)
                dpg.configure_item("freq_img_v", width=dw, height=dh)
            # Resize both drawlists so the active one is correct on next redraw
            dpg.configure_item("freq_legend_h", height=dh)
            dpg.configure_item("freq_legend_v", height=dh)
            legend_redraw_needed[0] = True

    dpg.set_viewport_resize_callback(lambda: fit_image())
    fit_image()

    # -----------------------------------------------------------------------
    # Render loop  (drawing thread — texture uploads and GUI only)
    # -----------------------------------------------------------------------
    last_stat_update = 0.0

    while dpg.is_dearpygui_running():

        # Detect camera thread death (e.g. unplugged)
        t = conn['cam_thread']
        if t is not None and not t.is_alive():
            conn['cam_thread']  = None
            conn['proc_thread'] = None
            conn['stop_evt']    = None
            dpg.configure_item("connect_btn", label="Connect")
            _set_cam_settings_enabled(True)

        # Snapshot visualization parameters (needed for texture conversion + legend)
        with state_lock:
            color_mode       = state['color_mode']
            fc_enabled       = state['fc_enabled']
            fc_min           = state['fc_min_freq']
            fc_max           = state['fc_max_freq']
            fc_n_to          = state['fc_n_timeout']
            fc_log_freq      = state['fc_log_freq']
            fc_overlay       = state['fc_overlay']
            fc_legend_show   = state['fc_legend_show']
            fc_legend_bins   = state['fc_legend_bins']

        # Drain all available processed results; keep the latest
        got_result   = False
        result_latest = None
        try:
            while True:
                result_latest = result_q.get_nowait()
                got_result = True
        except queue.Empty:
            pass

        if got_result and result_latest is not None:
            r = result_latest
            canvas_u8 = r['canvas_u8']
            last_canvas_u8[0] = canvas_u8
            event_buf.clear()
            event_buf.extend(r['event_buf'])

            tex_data = _canvas_to_texture(canvas_u8, color_mode)
            dpg.set_value(TEXTURE_TAG, tex_data)

            if fc_enabled and r['fc_enabled']:
                freq_tex = _freq_to_texture(
                    r['fc_per'], r['fc_t_ud'], r['fc_t_du'], r['fc_t_now'],
                    fc_n_to, fc_min, fc_max,
                    use_log=fc_log_freq, overlay_events=fc_overlay)
                last_freq_rgba[0] = freq_tex.reshape(SENSOR_H, SENSOR_W, 4)
                dpg.set_value(FREQ_TEX_TAG, freq_tex)

            now = time.perf_counter()
            if now - last_stat_update >= 0.2:
                last_stat_update = now
                s = r['stats']
                dpg.set_value("stat_ev_batch", f"{s['event_count']:,}")
                dpg.set_value("stat_rate",     f"{s['event_rate']:,.0f} ev/s")
                dpg.set_value("stat_bw",       f"{s['mbps']:.2f} MB/s")
                dpg.set_value("stat_total",    f"{s['total_events']:,}")
                dpg.set_value("stat_uptime",   f"{s['elapsed']:.1f} s")

        # Redraw legend only when parameters changed, not every frame
        if legend_redraw_needed[0]:
            if fc_legend_show:
                legend_dh = max(disp_wh[1], 1)
                _draw_freq_legend("freq_legend_h", legend_dh,
                                  fc_min, fc_max, fc_log_freq, fc_legend_bins)
                _draw_freq_legend("freq_legend_v", legend_dh,
                                  fc_min, fc_max, fc_log_freq, fc_legend_bins)
            legend_redraw_needed[0] = False

        # Reset UI if the camera thread died unexpectedly (e.g. connection error)
        if conn['cam_thread'] and not conn['cam_thread'].is_alive():
            do_disconnect()

        dpg.render_dearpygui_frame()

    # Render loop exited (window closed / Ctrl+C). Make sure the worker
    # thread tears down the Camera() cleanly so the on-camera script is
    # stopped and the serial port is released before the process exits.
    if conn['stop_evt']:
        conn['stop_evt'].set()
    for key in ('cam_thread', 'proc_thread'):
        t = conn[key]
        if t is not None and t.is_alive():
            t.join(timeout=3.0)
    _stop_recording()

    dpg.destroy_context()


if __name__ == '__main__':
    _args = parse_args()
    if _args.decode:
        logging.basicConfig(format="%(message)s",
                            level=logging.DEBUG if _args.debug else logging.INFO)
        run_decode(_args)
    elif _args.benchmark:
        run_benchmark(_args)
    else:
        main(_args)
