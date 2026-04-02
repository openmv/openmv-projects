#!/usr/bin/env python3
#
# This work is licensed under the MIT license.
# Copyright (c) 2013-2026 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# GenX320 event camera visualization GUI for PC.
# Requires: pip install dearpygui numpy numba Pillow pyserial
#
# Two threads: camera_worker (receives events) and render loop (draws).
# Canvas initialized to 128; events add contrast*polarity until clamping at 0/255.
# Color modes: Grayscale, Evt Dark LUT, Evt Light LUT (RGB565 → RGB888).
#

import sys
import os
import argparse
import time
import logging
import signal
import threading
import queue
from collections import deque
import numpy as np
import numba
try:
    from PIL import Image, ImageDraw
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
import serial.tools.list_ports
import dearpygui.dearpygui as dpg
from openmv.camera import Camera


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


def patch_script(script, csi_fifo_depth, evt_fifo_depth, evt_res):
    """Patch the on-camera script with GUI-controlled parameters before exec.

    Substitutions made:
      CSI_FIFO_DEPTH  = <value>
      EVENT_FIFO_DEPTH = <value>
      np.zeros((EVT_RES, 6), ...)     — the array shape (EVT_RES constant)
      def read / def readp            — use readp on Mac/Linux, read on Windows
    """
    import re

    script = re.sub(r'CSI_FIFO_DEPTH\s*=\s*\d+',
                    f'CSI_FIFO_DEPTH = {csi_fifo_depth}', script)
    script = re.sub(r'EVENT_FIFO_DEPTH\s*=\s*\d+',
                    f'EVENT_FIFO_DEPTH = {evt_fifo_depth}', script)
    script = re.sub(r'np\.zeros\(\((?:\d+|EVT_RES),\s*6\)',
                    f'np.zeros(({evt_res}, 6)', script)

    if sys.platform != 'win32':
        script = script.replace('def read(self, offset, size):',
                                'def readp(self, offset, size):')

    return script


def camera_worker(args, state_lock, state, event_q, stop_evt):
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
                csi_fifo  = state['csi_fifo_depth']
                evt_fifo  = state['evt_fifo_depth']
                evt_res   = state['evt_res']
            script = patch_script(script, csi_fifo, evt_fifo, evt_res)
            logging.debug(f"Patched script: CSI_FIFO={csi_fifo} EVT_FIFO={evt_fifo} "
                          f"EVT_RES={evt_res} readp={'yes' if sys.platform != 'win32' else 'no'}")
            camera.exec(script)
            logging.info("Script running, streaming events...")

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

                if not camera.has_channel('events'):
                    time.sleep(0.01)
                    continue

                if not status or not status.get('events'):
                    time.sleep(0.01)
                    continue

                size = camera.channel_size('events')
                if size <= 0:
                    time.sleep(0.01)
                    continue

                now       = time.perf_counter()
                dt        = now - last_time
                last_time = now
                if dt <= 0.0:
                    continue

                data = camera.channel_read('events', size)

                if (len(data) % 12) != 0:
                    logging.warning(f"Misaligned packet: {len(data)} bytes (not multiple of 12)")
                    continue

                # Each event row: 6 × uint16 little-endian
                # [0] polarity (0=neg, 1=pos)  [1] sec  [2] ms  [3] us  [4] x  [5] y
                events      = np.frombuffer(data, dtype='<u2').reshape(-1, 6)
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

        batch_delta = None
        if xs.size > 0:
            signs    = pols * 2 - 1
            flat_idx = ys * SENSOR_W + xs
            pos = np.bincount(flat_idx[signs > 0], minlength=SENSOR_H * SENSOR_W)
            neg = np.bincount(flat_idx[signs < 0], minlength=SENSOR_H * SENSOR_W)
            batch_delta = (pos.astype(np.int32) - neg.astype(np.int32)).reshape(SENSOR_H, SENSOR_W)

            with state_lock:
                fc_enabled = state['fc_enabled']
                fc_min  = state['fc_min_freq']
                fc_max  = state['fc_max_freq']
                fc_n_to = state['fc_n_timeout']

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
    return p.parse_args()


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

    if args.script is None:
        args.script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'genx320_event_mode_streaming_on_cam.py',
        )

    state_lock = threading.Lock()
    state = {
        'csi_fifo_depth': 8,
        'evt_fifo_depth': 8,
        'evt_res':        32768,
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
        'csi_fifo_depth': 8,
        'evt_fifo_depth': 8,
        'evt_res':        32768,
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
        last_freq_rgba[0] = None
        reset_evt.set()   # processing_worker will reset filter/canvas on startup
        stop_evt         = threading.Event()
        conn['stop_evt'] = stop_evt

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
        cam_t.start()
        proc_t.start()
        conn['cam_thread']  = cam_t
        conn['proc_thread'] = proc_t
        dpg.configure_item("connect_btn", label="Disconnect")
        _set_cam_settings_enabled(False)
        logging.info(f"Connecting to {port}...")

    def do_disconnect():
        if conn['stop_evt']:
            conn['stop_evt'].set()
        conn['cam_thread']  = None
        conn['proc_thread'] = None
        conn['stop_evt']    = None
        dpg.configure_item("connect_btn", label="Connect")
        _set_cam_settings_enabled(True)

    CAM_SETTING_TAGS = ["csi_fifo_input", "evt_fifo_input"]

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
                header='polarity,sec,ms,us,x,y', comments='',
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
                            dpg.add_text("CSI FIFO ")
                            dpg.add_input_int(
                                tag="csi_fifo_input", label="##csi_fifo",
                                default_value=state['csi_fifo_depth'],
                                min_value=4, min_clamped=True,
                                step=1, step_fast=4,
                                callback=cb_csi_fifo, width=-1)

                        with dpg.group(horizontal=True):
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
                        width=1280, height=800, resizable=True)
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

        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == '__main__':
    _args = parse_args()
    if _args.benchmark:
        run_benchmark(_args)
    else:
        main(_args)
