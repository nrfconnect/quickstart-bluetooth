#!/usr/bin/env python3
#
# Copyright (c) 2026 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#
# Validates the `mflt get_device_info` serial-shell command on a supported DK
# running the quickstart-bluetooth firmware.
#
# Regression coverage: without CONFIG_LOG, this command's output was silently
# dropped (printk() isn't coordinated with the interrupt-driven shell backend
# while a command is executing) — the command ran but printed nothing. These
# tests fail loudly if that happens again.
#
# Also exposes get_device_info()/get_device_serial(), used by
# test_project_switch_e2e.py to read the device serial over the shell instead
# of parsing it out of the BLE gateway's output.
#
# pyserial lives in the NCS toolchain Python, so run this via the toolchain:
#
#   nrfutil toolchain-manager launch --ncs-version v3.3.1 --chdir <workspace> -- \
#       python3 project/test/e2e/test_device_info.py
#
# Options:
#   --port <dev>   Serial console (VCOM1). Default: $QSBT_PORT or the value below.

import argparse
import os
import re
import sys

from test_project_key import serial_session

FIELDS = ("S/N", "SW type", "SW version", "HW version")
FIELD_RE = re.compile(r"(%s):\s*(.+)" % "|".join(re.escape(f) for f in FIELDS))

DEFAULT_PORT = os.environ.get("QSBT_PORT", "/dev/tty.usbmodem0010577603503")


def get_device_info(port, **kw):
    """Run `mflt get_device_info` and parse its printed fields into a dict."""
    out = serial_session(port, ["mflt get_device_info"], **kw)
    info = {}
    for line in out.splitlines():
        m = FIELD_RE.search(line)
        if m:
            info[m.group(1)] = m.group(2).strip()
    return info


def get_device_serial(port, **kw):
    """Return the device serial reported by `mflt get_device_info`.

    Raises if the command printed nothing or an unset value, rather than
    returning something callers might mistake for a real serial.
    """
    info = get_device_info(port, **kw)
    serial = info.get("S/N")
    if not serial or serial in ("<NULL>", "Unknown"):
        raise RuntimeError(
            f"could not read a device serial from `mflt get_device_info`, got: {info!r}"
        )
    return serial


# --- test cases: each returns (passed: bool, detail: str) --------------------

def test_prints_all_fields(port):
    info = get_device_info(port)
    missing = [f for f in FIELDS if f not in info]
    ok = not missing
    return ok, f"printed all fields: {info}" if ok \
        else f"missing fields {missing}, got: {info!r}"


def test_serial_is_set(port):
    info = get_device_info(port)
    serial = info.get("S/N")
    ok = bool(serial) and serial not in ("<NULL>", "Unknown")
    return ok, f"S/N: {serial}" if ok else f"expected a real serial, got: {serial!r}"


def test_serial_is_stable(port):
    a = get_device_info(port).get("S/N")
    b = get_device_info(port).get("S/N")
    ok = a is not None and a == b
    return ok, f"S/N stable across two reads ({a})" if ok \
        else f"S/N changed between reads: {a!r} vs {b!r}"


TESTS = [
    ("prints all device-info fields", test_prints_all_fields),
    ("device serial is set", test_serial_is_set),
    ("device serial is stable across reads", test_serial_is_stable),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=DEFAULT_PORT)
    args = ap.parse_args()

    print(f"Serial console: {args.port}\n")
    results = []
    for name, fn in TESTS:
        try:
            passed, detail = fn(args.port)
        except Exception as e:
            passed, detail = False, f"exception: {e}"
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {name}\n       {detail}")
        results.append(passed)

    n_pass = sum(results)
    print(f"\n{n_pass}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
