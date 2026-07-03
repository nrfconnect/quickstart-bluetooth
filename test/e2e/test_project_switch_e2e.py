#!/usr/bin/env python3
#
# Copyright (c) 2026 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#
# End-to-end test that switching the Memfault project key over the serial shell
# actually re-targets the device to that project in the Memfault cloud.
#
# For each configured project (A, then B):
#   1. Write its project key over the serial shell and `kernel reboot cold`.
#   2. Read the device serial over the shell (`mflt get_device_info`, see
#      test_device_info.py) rather than from the BLE gateway's output.
#   3. Run the BLE gateway (--upload) so the device drains a fresh heartbeat; poll
#      the Memfault REST API until the device's `last_seen` advances, proving the
#      switch re-targeted uploads to this project. (A heartbeat drain reliably
#      bumps last_seen; a coredump-carrying drain does not, so verification uses a
#      clean heartbeat.)
#   4. Force a coredump (`mflt test hardfault`) with this project's key active and
#      drain it, so a real crash — not just reboot/heartbeat events — is captured
#      in this project. Draining also clears the coredump so the next project's
#      heartbeat check stays clean.
#
# Data landing in project B (and not just A) after the switch proves the runtime
# key override works end to end.
#
# Secrets are read from the repo-root .env (or --env-file), never committed.
# Run via the NCS toolchain Python (for pyserial); Node must be on PATH for the
# gateway subprocess:
#
#   nrfutil toolchain-manager launch --ncs-version v3.3.1 --chdir <workspace> -- \
#       python3 quickstart-bluetooth/test/e2e/test_project_switch_e2e.py \
#       --env-file quickstart-bluetooth/.env
#
# Required environment (see .env.example):
#   MEMFAULT_ORG_TOKEN                       (Organization Auth Token; Bearer) — or —
#   MEMFAULT_API_EMAIL + MEMFAULT_API_KEY    (User API key; HTTP Basic)
#   MEMFAULT_ORG_SLUG
#   MEMFAULT_PROJECT_B_SLUG + MEMFAULT_PROJECT_B_KEY   (the project to switch TO)
# Optional:
#   MEMFAULT_PROJECT_A_SLUG + MEMFAULT_PROJECT_A_KEY   (baseline, tested first)
#   MEMFAULT_API_BASE        (default: https://api.memfault.com)
#   QSBT_PORT, QSBT_GATEWAY_DIR, QSBT_UPLOAD_SECONDS

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from test_device_info import get_device_serial  # noqa: E402
from test_project_key import KEY, serial_session  # noqa: E402

API_BASE = os.environ.get("MEMFAULT_API_BASE", "https://api.memfault.com")
PORT = os.environ.get("QSBT_PORT", "/dev/tty.usbmodem0010577603503")
GATEWAY_DIR = os.environ.get(
    "QSBT_GATEWAY_DIR",
    os.path.join(os.path.dirname(__file__), "..", "gateway"),
)
UPLOAD_SECONDS = int(os.environ.get("QSBT_UPLOAD_SECONDS", "20"))


def load_env_file(path):
    if not path or not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def auth_header():
    """Authorization header for the Memfault management API.

    An Organization Auth Token uses Bearer auth; a User API Key uses HTTP Basic
    with the account email as the username.
    """
    org_token = os.environ.get("MEMFAULT_ORG_TOKEN")
    email = os.environ.get("MEMFAULT_API_EMAIL")
    key = os.environ.get("MEMFAULT_API_KEY")
    if org_token:
        return f"Bearer {org_token}"
    if email and key:
        return "Basic " + base64.b64encode(f"{email}:{key}".encode()).decode()
    raise SystemExit(
        "Missing API credentials: set MEMFAULT_ORG_TOKEN (Bearer) "
        "or MEMFAULT_API_EMAIL+MEMFAULT_API_KEY (Basic)"
    )


def get_device(org, project, serial):
    """GET the device record; return the device object or None if 404.

    The management API wraps single resources as {"data": {...}}.
    """
    url = f"{API_BASE}/api/v0/organizations/{org}/projects/{project}/devices/{serial}"
    req = urllib.request.Request(url, headers={"Authorization": auth_header()})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.load(resp)
            return body.get("data", body)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def switch_key_and_reboot(project_key):
    serial_session(PORT, [f"settings write string {KEY} {project_key}"])
    serial_session(PORT, ["kernel reboot cold"], window=1.5)
    time.sleep(2.0)


def crash_and_reboot():
    """Force a coredump with the current key active, then wait for the reboot.

    `mflt test hardfault` captures a RAM-backed coredump and warm-resets; the key
    persists in ZMS, so the device comes back up ready to serve the coredump to
    the gateway for upload into the current project.
    """
    print("    crashing device (mflt test hardfault) for a coredump …")
    serial_session(PORT, ["mflt test hardfault"], window=2.0)
    time.sleep(6.0)


def run_gateway_upload():
    """Run the gateway with --upload so the device drains its queued chunks."""
    print(f"    running gateway --upload for {UPLOAD_SECONDS}s …")
    proc = subprocess.run(
        ["node", "gateway.js", "--upload", "--seconds", str(UPLOAD_SECONDS)],
        cwd=os.path.abspath(GATEWAY_DIR),
        check=True,
        capture_output=True,
        text=True,
    )
    print(proc.stdout)


def poll_last_seen(org, project, serial, since, timeout=150):
    """Return True once the device's last_seen advances past `since`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        dev = get_device(org, project, serial)
        if dev:
            last = parse_ts(dev.get("last_seen"))
            if last and last >= since:
                print(f"    device last_seen={last.isoformat()} (>= {since.isoformat()})")
                return True
        time.sleep(5)
    return False


def test_project(org, name, slug, project_key):
    print(f"\n=== project {name}: {slug} ===")
    since = datetime.now(timezone.utc)
    switch_key_and_reboot(project_key)
    serial = get_device_serial(PORT)
    print(f"    device serial (mflt get_device_info): {serial}")
    # Verify the switch with a clean heartbeat drain — last_seen advances
    # reliably (a coredump-carrying drain does not).
    run_gateway_upload()
    ok = poll_last_seen(org, slug, serial, since)
    mark = "PASS" if ok else "FAIL"
    detail = f"device {serial} reported into project after switch" if ok else \
        f"device {serial} did NOT report into project within timeout"
    print(f"[{mark}] switch to {name} ({slug}): {detail}")

    # Now capture a real crash in this project: coredump uploads under the
    # just-verified key. Drained here so it clears before the next iteration.
    crash_and_reboot()
    print("    draining coredump …")
    run_gateway_upload()
    return ok


def main():
    # Default to the repo-root .env (two levels up from test/e2e/).
    default_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=default_env)
    ap.add_argument("--port", default=PORT)
    args = ap.parse_args()
    load_env_file(args.env_file)

    org = os.environ.get("MEMFAULT_ORG_SLUG")
    if not org:
        raise SystemExit("Missing MEMFAULT_ORG_SLUG")

    projects = []
    if os.environ.get("MEMFAULT_PROJECT_A_SLUG") and os.environ.get("MEMFAULT_PROJECT_A_KEY"):
        projects.append(("A", os.environ["MEMFAULT_PROJECT_A_SLUG"],
                         os.environ["MEMFAULT_PROJECT_A_KEY"]))
    if os.environ.get("MEMFAULT_PROJECT_B_SLUG") and os.environ.get("MEMFAULT_PROJECT_B_KEY"):
        projects.append(("B", os.environ["MEMFAULT_PROJECT_B_SLUG"],
                         os.environ["MEMFAULT_PROJECT_B_KEY"]))
    if not projects:
        raise SystemExit("Configure at least MEMFAULT_PROJECT_B_SLUG + _KEY")

    print(f"Org: {org}   API: {API_BASE}")

    results = [test_project(org, n, s, k) for (n, s, k) in projects]

    # leave the device clean
    serial_session(args.port, [f"settings delete {KEY}"])
    serial_session(args.port, ["kernel reboot cold"], window=1.5)

    print(f"\n{sum(results)}/{len(results)} project(s) verified")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
