# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`quickstart-bluetooth` is a **production out-of-tree nRF Connect SDK (NCS) application**
for the *nRF Connect for Desktop Quick Start* guide. It is the `peripheral_lbs` sample
(button/LED over BLE) plus Memfault observability delivered over the Memfault Diagnostic
Service (MDS) BLE gateway path: the device collects heartbeat metrics and coredumps and
serves them as chunks to a phone/desktop gateway that performs the HTTPS upload.
**The device never does on-device HTTP/TLS.**

Supported boards:

- `nrf54l15dk/nrf54l15/cpuapp` — single-core, plain single image.
- `nrf54lm20dk/nrf54lm20a/cpuapp` — single-core, plain single image.
- `nrf54h20dk/nrf54h20/cpuapp` — **multi-core**, built with **sysbuild** (see below).

The L-series boards keep the on-app-core Bluetooth controller and the plain
single-image, no-bootloader model. The nRF54H20's Bluetooth controller runs on
the radio core (cpurad) over HCI/IPC, so it is the one board built with sysbuild.

## Build & run (T2 west workspace)

This is the **top-level west manifest repository** (T2 star topology). It imports `sdk-nrf`,
which pulls Zephyr and all NCS modules. Building requires the NCS toolchain.

```sh
# Bootstrap the workspace (done once, outside the repo dir)
west init -m https://github.com/<org>/quickstart-bluetooth <workspace-dir>
cd <workspace-dir>
west update

# Build / flash (L-series: plain single image)
west build -b nrf54l15dk/nrf54l15/cpuapp --no-sysbuild project/app
west flash

# nRF54LM20 DK
west build -b nrf54lm20dk/nrf54lm20a/cpuapp --no-sysbuild project/app

# nRF54H20 DK (multi-core: sysbuild builds the app + ipc_radio + radio loader)
west build -b nrf54h20dk/nrf54h20/cpuapp --sysbuild project/app
west flash
```

For the **L-series** boards the single `zephyr.hex` is the complete image — **no
MCUboot/sysbuild**, no merged/signed hex, no DFU zip (OTA is explicitly out of
scope). The **nRF54H20** is the sole exception: sysbuild is required because its
Bluetooth controller is a separate `ipc_radio` image on cpurad, loaded from MRAM
into TCM by a radio loader (still **no MCUboot** — the radio-loader path is the
bootloader-free variant). CI merges the per-domain hexes into one release `.hex`.
The H20 support lives under `app/boards/`, `app/common/`, `app/sysbuild/`, and
`app/Kconfig.sysbuild`, mirroring the upstream `peripheral_lbs` sample.

## Architecture & key constraints

- **Upstream-first dependency model.** The reusable Memfault glue is upstreamed into
  `sdk-nrf` (and the vendored Memfault firmware SDK), *not* carried as an out-of-tree
  fork. `west.yml` pins a **specific `sdk-nrf` main SHA** (not the `main` branch) that
  already contains that work. Bumping the SHA is a deliberate, CI-gated action.
- **Plain Zephyr app, not a Zephyr module.** Default to a plain application under `app/`
  with no `zephyr/module.yml`. Only add module machinery if app-local shared code emerges.
- **Runtime project key via settings shell.** The Memfault project key is provisioned over
  the serial shell: `settings write string memfault/project_key <32-char-key>`. **The key
  is applied on boot, not live — a `kernel reboot cold` is required after writing.** A
  stored key overrides the compile-time `CONFIG_MEMFAULT_NCS_PROJECT_KEY`. The key is
  stored **unencrypted** (same at-rest protection as baking it into flash). BLE/SMP
  provisioning is out of scope.
- **Memfault feature scope is core-only:** heartbeat metrics + RAM-backed coredump +
  runtime key, on top of the LBS button/LED base. No MCUboot/MCUmgr/SMP/OTA.
- **Coredump is RAM-backed** (`CONFIG_MEMFAULT_RAM_BACKED_COREDUMP`), so it needs no
  bootloader or flash partition. Re-measure size with the `mflt coredump_size` shell
  command on the LBS build before fixing `CONFIG_MEMFAULT_RAM_BACKED_COREDUMP_SIZE`.

## App behavior to preserve

- **MDS access control:** register `bt_mds_cb` with an `access_enable` callback that gates
  MDS access to the secured/connected gateway link (`CONFIG_BT_SMP=y` is required).
- **Heartbeat-on-connect:** in `security_changed`, once the link is secured, call
  `memfault_metrics_heartbeat_debug_trigger()` once so the device shows up in Memfault
  immediately instead of waiting for the periodic timer.
- **Crash button (demo-only):** map an LBS button to a forced fault (e.g. `k_oops`) to
  demonstrate a coredump. Comment it clearly as demo-only.
- Keep the LBS LED/button behavior so it remains a recognizable LBS device for the guide —
  the GATT LBS service/characteristics stay standard regardless of what's advertised.
- **Scan-time identity:** the scan response advertises the custom app-identity UUID
  (`BT_UUID_QSBT_ID_VAL`, `b2007aaa-...`), not the LBS UUID, so the mobile app can tag this
  device as "quick start" in its scan list before connecting.

## Testing (on-hardware)

The tests under `test/` are **on-hardware bench tests**: they drive a connected
**DK** (nRF54L15, nRF54LM20, or nRF54H20) over its USB serial console and BLE.
There is no pure-host test suite. **If no DK is connected, ask the user whether
they want to connect one of the supported DKs so you can verify functionality
before running anything.** On macOS a connected L-series DK shows up as
`/dev/tty.usbmodem*01/03` (VCOM1 = `…03`); no ports means no board.

- `test/gateway/` — a phone-free Node/noble MDS gateway that stands in for the mobile
  app (connects, secures the link, drains chunks, optionally uploads). Needs Node on
  PATH; run `npm install` in that dir first. See `test/gateway/README.md`.
- `test/e2e/` — serial project-key contract tests plus a cloud project-switch e2e (the
  latter drives the gateway above and confirms the switch via the Memfault REST API).
  Needs the NCS toolchain Python (for pyserial); the e2e also needs credentials in the
  gitignored repo-root `.env`. See `test/e2e/README.md`.

Both suites run through the NCS toolchain launcher
(`nrfutil toolchain-manager launch … -- python3 …`) — the exact invocations, options,
and credential setup are in the two READMEs above; don't duplicate them here.

## Versioning

`app/VERSION` (Zephyr/Asset-Tracker-Template format) is the **single source of truth** for
the firmware version. With `CONFIG_MEMFAULT_NCS_FW_VERSION_STATIC=y` and no explicit
`CONFIG_MEMFAULT_NCS_FW_VERSION`, the Memfault software version defaults to
`$(APP_VERSION_TWEAK_STRING)` (e.g. `1.0.0+0`). **Do not hardcode the firmware version** —
bump a release by editing `app/VERSION` only. The GNU Build ID (used for symbolication) is
independent and changes every build — `zephyr.elf` must be uploaded to Memfault for
symbol resolution.
