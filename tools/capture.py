#!/usr/bin/env python3
"""Capture raw frames from an EgisTec 1c7a:0570 sensor via libfprint's public
debug-capture API and save them as PGM, for later calibration/signal analysis.

Run this on the 152 laptop AFTER setup/152-setup.sh has been run (for USB
permissions) and AFTER building libfprint/ in this repo (meson setup+ninja).

Usage:
    GI_TYPELIB_PATH=<builddir>/libfprint LD_LIBRARY_PATH=<builddir>/libfprint \
        python3 scripts/capture.py -o captures/ -n 20

This uses `FPrint.Device.capture()`, the same debug-capture entry point
libfprint itself ships (used by its own test suite for image devices) — it
returns the device's own `FpImage` *before* any minutiae extraction, so the
bytes written here are exactly what the driver produced, not something this
script invents. It intentionally does NOT reimplement the EGIS USB protocol:
that logic lives in libfprint/drivers/egis0570.c, where it can be reviewed,
tested, and changed in one place.

Requires: PyGObject (`python3-gi`) and a libfprint build with introspection
enabled (meson `-Dintrospection=enabled`, the libfprint default). If your
distro's libfprint wasn't built with introspection, point GI_TYPELIB_PATH at
a local build that was (see libfprint/README.build in this repo).
"""
import argparse
import sys
import time
from pathlib import Path


def write_pgm(path: Path, width: int, height: int, data: bytes) -> None:
    """Write a raw 8-bit grayscale buffer as a binary PGM (P5) file.

    PGM is a generic, uncompressed image format (header + raw bytes) — this
    is NOT part of the sensor protocol, just a convenient dump format for
    later analysis (std-dev checks, calibration, matcher experiments).
    """
    expected = width * height
    if len(data) < expected:
        raise ValueError(f"frame has {len(data)} bytes, expected {expected} for {width}x{height}")
    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    with open(path, "wb") as f:
        f.write(header)
        f.write(data[:expected])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("captures"), help="directory to write frame-NNNN.pgm into")
    ap.add_argument("-n", "--count", type=int, default=10, help="number of frames to capture")
    ap.add_argument("--device-index", type=int, default=0, help="which enumerated fingerprint device to use, if more than one is present")
    ap.add_argument("--vendor-id", default="1c7a", help="expected USB vendor id (hex, no 0x), for a sanity check / clearer error if the wrong device is picked")
    ap.add_argument("--product-id", default="0570", help="expected USB product id (hex, no 0x)")
    args = ap.parse_args()

    try:
        import gi
        gi.require_version("FPrint", "2.0")
        from gi.repository import FPrint, GLib
    except (ImportError, ValueError) as exc:
        print(f"error: PyGObject + FPrint-2.0 typelib not available: {exc}", file=sys.stderr)
        print("Set GI_TYPELIB_PATH / LD_LIBRARY_PATH to your meson build's libfprint/ dir, or install python3-gi.", file=sys.stderr)
        return 1

    ctx = FPrint.Context()
    ctx.enumerate()
    devices = ctx.get_devices()
    if not devices:
        print("error: no fingerprint devices enumerated. Check the udev rule from setup/152-setup.sh is installed", file=sys.stderr)
        print("and that you are in the 'plugdev' group (re-login after usermod -aG plugdev).", file=sys.stderr)
        return 1

    if args.device_index >= len(devices):
        print(f"error: --device-index {args.device_index} out of range, only {len(devices)} device(s) enumerated", file=sys.stderr)
        return 1

    dev = devices[args.device_index]
    print(f"Using device: {dev.get_name()} (driver={dev.get_driver()})", file=sys.stderr)

    if not dev.has_feature(FPrint.DeviceFeature.CAPTURE):
        print(f"error: driver '{dev.get_driver()}' does not report FPrint.DeviceFeature.CAPTURE support.", file=sys.stderr)
        print("This means libfprint's debug-capture API isn't wired up for this driver build; check libfprint/drivers/egis0570.c img_capture setup.", file=sys.stderr)
        return 1

    args.outdir.mkdir(parents=True, exist_ok=True)

    loop = GLib.MainLoop()
    state = {"captured": 0, "error": None}

    def on_capture_done(device, task):
        try:
            image = device.capture_finish(task)
        except GLib.Error as exc:
            state["error"] = str(exc)
            loop.quit()
            return
        width, height = image.get_width(), image.get_height()
        data = bytes(image.get_data())
        out_path = args.outdir / f"frame-{state['captured']:04d}.pgm"
        write_pgm(out_path, width, height, data)
        print(f"wrote {out_path} ({width}x{height}, {len(data)} bytes)", file=sys.stderr)
        state["captured"] += 1
        if state["captured"] >= args.count:
            loop.quit()
        else:
            # wait_for_finger=True blocks the next capture until a finger is (re)placed,
            # matching how the sensor is actually used; pass False to grab back-to-back
            # frames of whatever is currently on the sensor (e.g. for an empty-frame baseline).
            device.capture(wait_for_finger=True, callback=on_capture_done)

    print(f"Capturing {args.count} frame(s) into {args.outdir}/ ... place/lift your finger as prompted.", file=sys.stderr)
    dev.capture(wait_for_finger=True, callback=on_capture_done)

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    if state["error"]:
        print(f"error during capture: {state['error']}", file=sys.stderr)
        return 1

    print(f"done: {state['captured']} frame(s) written to {args.outdir}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
