#!/usr/bin/env python3
#
# Copyright (c) 2026 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#
# Validate the Memfault project-key serial-shell provisioning contract on the
# nRF54L15 DK running the quickstart-bluetooth firmware:
#
#   1. After a clean flash the key is unset  -> read returns "Setting not found".
#   2. Writing the key and reading it back returns the written value.
#   3. The key survives a cold reboot         -> persisted in the ZMS backend.
#   4. Deleting the key returns to the unset state.
#
# pyserial lives in the NCS toolchain Python, so run this via the toolchain:
#
#   nrfutil toolchain-manager launch --ncs-version v3.3.1 --chdir <workspace> -- \
#       python3 project/test/e2e/test_project_key.py [--recover]
#
# Options:
#   --port <dev>   Serial console (VCOM1). Default: $QSBT_PORT or the value below.
#   --recover      Erase the device first (west flash --recover) so test 1 checks
#                  a genuine post-flash state. Needs $QSBT_BUILD_DIR (or --build-dir).
#   --build-dir <d>  West build dir for --recover. Default: $QSBT_BUILD_DIR.

import argparse
import os
import re
import subprocess
import sys
import time

import serial  # from the NCS toolchain Python

KEY = "memfault/project_key"
TEST_VALUE = "TESTKEY0011223344556677889900AAB"  # 32 chars, like a real key
ANSI = re.compile(r"\x1b\[[0-9;]*m")

DEFAULT_PORT = os.environ.get("QSBT_PORT", "/dev/tty.usbmodem0010577603503")


def strip(txt):
    return ANSI.sub("", txt)


def serial_session(port, cmds, window=2.5, settle=0.5, reopen_wait=0.0):
    """Open the console, send each command, capture output for `window` seconds.

    Retries the open because the port disappears briefly after a reboot.
    """
    if reopen_wait:
        time.sleep(reopen_wait)
    s = None
    for _ in range(25):
        try:
            s = serial.Serial(port, 115200, timeout=0.3)
            break
        except Exception:
            time.sleep(0.4)
    if s is None:
        raise RuntimeError(f"could not open serial port {port}")
    s.dtr = s.rts = True
    time.sleep(settle)
    try:
        s.reset_input_buffer()
    except Exception:
        pass
    buf = b""
    for c in cmds:
        s.write((c + "\r\n").encode())
        end = time.time() + window
        while time.time() < end:
            buf += s.read(4096)
    s.close()
    return strip(buf.decode("utf-8", "replace").replace("\r", ""))


def read_key(port, **kw):
    return serial_session(port, [f"settings read string {KEY}"], **kw)


def is_not_found(out):
    return "Setting not found" in out


def has_value(out, value):
    # The value is echoed on the command line and printed on its own line;
    # require it to appear on a line that is not the command echo.
    for line in out.splitlines():
        line = line.strip()
        if line == value:
            return True
    return False


# --- test cases: each returns (passed: bool, detail: str) --------------------

def test_empty_after_flash(port):
    out = read_key(port)
    return is_not_found(out), "read returned 'Setting not found'" if is_not_found(out) \
        else f"expected 'Setting not found', got:\n{out}"


def test_write_and_read(port):
    out = serial_session(port, [
        f"settings write string {KEY} {TEST_VALUE}",
        f"settings read string {KEY}",
    ])
    ok = has_value(out, TEST_VALUE)
    return ok, f"read back the written value ({TEST_VALUE})" if ok \
        else f"expected value {TEST_VALUE} in output:\n{out}"


def test_persists_across_reboot(port):
    serial_session(port, ["kernel reboot cold"], window=1.5)
    out = read_key(port, reopen_wait=2.0, settle=1.0)
    ok = has_value(out, TEST_VALUE)
    return ok, "value survived cold reboot (persisted in ZMS)" if ok \
        else f"expected persisted value after reboot:\n{out}"


def test_delete_returns_to_empty(port):
    out = serial_session(port, [
        f"settings delete {KEY}",
        f"settings read string {KEY}",
    ])
    ok = is_not_found(out)
    return ok, "delete returned key to unset state" if ok \
        else f"expected 'Setting not found' after delete:\n{out}"


TESTS = [
    ("read after flash returns empty", test_empty_after_flash),
    ("write + read returns written value", test_write_and_read),
    ("key persists across cold reboot", test_persists_across_reboot),
    ("delete returns to empty", test_delete_returns_to_empty),
]


def flash_recover(build_dir):
    print(f"[setup] west flash --recover (build-dir={build_dir}) …")
    subprocess.run(
        ["west", "flash", "--recover", "--build-dir", build_dir],
        check=True,
    )
    time.sleep(2.0)  # let it boot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--recover", action="store_true",
                    help="erase device first so test 1 checks a real post-flash state")
    ap.add_argument("--build-dir", default=os.environ.get("QSBT_BUILD_DIR"))
    args = ap.parse_args()

    if args.recover:
        if not args.build_dir:
            print("ERROR: --recover needs --build-dir or $QSBT_BUILD_DIR", file=sys.stderr)
            return 2
        flash_recover(args.build_dir)

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
