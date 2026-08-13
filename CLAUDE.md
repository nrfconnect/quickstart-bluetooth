# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`quickstart-bluetooth` is a **production out-of-tree nRF Connect SDK (NCS) application**
for the *nRF Connect for Desktop Quick Start* guide. It is the `peripheral_lbs` sample
(button/LED over BLE) plus Memfault observability delivered over the Memfault Diagnostic
Service (MDS) BLE gateway path: the device collects heartbeat metrics and coredumps and
serves them as chunks to a phone/desktop gateway that performs the HTTPS upload.
**The device never does on-device HTTP/TLS.**

Target board is **`nrf54l15dk/nrf54l15/cpuapp` only**.

## Build & run (T2 west workspace)

This is the **top-level west manifest repository** (T2 star topology). It imports `sdk-nrf`,
which pulls Zephyr and all NCS modules. Building requires the NCS toolchain.

```sh
# Bootstrap the workspace (done once, outside the repo dir)
west init -m https://github.com/<org>/quickstart-bluetooth <workspace-dir>
cd <workspace-dir>
west update

# Build / flash for the only supported board
west build -b nrf54l15dk/nrf54l15/cpuapp project/app
west flash
```

The single `zephyr.hex` is the complete image — there is **no MCUboot/sysbuild**, no
merged/signed hex, no DFU zip (OTA is explicitly out of scope).

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
  stored key overrides the build-time default key (`CONFIG_QSBT_DEFAULT_PROJECT_KEY`, if
  any — see `app/src/main.c`). The key is stored **unencrypted** (same at-rest protection
  as baking it into flash). BLE/SMP provisioning is out of scope.
  - Release builds bake in a real key at build time (CI passes
    `-DCONFIG_QSBT_DEFAULT_PROJECT_KEY` from the `MEMFAULT_PROJECT_KEY` repo secret — see
    `release.yml`/`build-app.yml`) so a freshly flashed release artifact reports to
    Memfault out of the box, without requiring shell provisioning first.
  - `CONFIG_MEMFAULT_NCS_PROJECT_KEY` is a **dead/deprecated** upstream Kconfig option with
    no effect when `CONFIG_MEMFAULT_PROJECT_KEY_SETTINGS=y` (always the case here) — do not
    reintroduce it as the build-time override mechanism.
- **Memfault feature scope is core-only:** heartbeat metrics + RAM-backed coredump +
  runtime key, on top of the LBS button/LED base. No MCUboot/MCUmgr/SMP/OTA.
- **Coredump is RAM-backed** (`CONFIG_MEMFAULT_RAM_BACKED_COREDUMP`), so it needs no
  bootloader or flash partition. Re-measure size with the `mflt coredump_size` shell
  command on the LBS build before fixing `CONFIG_MEMFAULT_RAM_BACKED_COREDUMP_SIZE`.

## App behavior to preserve

- **No pairing/bonding:** `CONFIG_BT_SMP=n` — this sample has no encryption or bonding. A
  real product handling sensitive data should set `CONFIG_BT_SMP=y` and use bonding
  (`CONFIG_BT_BONDABLE=y`, the default) instead. Because of this, we can't use the
  `CONFIG_BT_MDS_PERM_RW_ENCRYPT` option described in [Restricting Access to
  MDS](https://docs.memfault.com/docs/mcu/mds#restricting-access-to-mds) — that requires a
  bonded, encrypted link — so this app falls back to the custom `access_enable` callback
  from that same doc (see MDS access control below).
- **MDS access control:** register `bt_mds_cb` with an `access_enable` callback that gates
  MDS access to the first connected gateway link (tracked via `mds_conn` in `connected()`,
  since there is no security level to check without `CONFIG_BT_SMP`).
- **Heartbeat-on-connect:** in `connected()`, once the gateway link is captured as
  `mds_conn`, call `memfault_metrics_heartbeat_debug_trigger()` once so the device shows up
  in Memfault immediately instead of waiting for the periodic timer.
- **Crash button (demo-only):** map an LBS button to a forced fault (e.g. `k_oops`) to
  demonstrate a coredump. Comment it clearly as demo-only.
- Keep the LBS LED/button behavior so it remains a recognizable LBS device for the guide —
  the GATT LBS service/characteristics stay standard regardless of what's advertised.
- **Scan-time identity:** the scan response advertises the custom app-identity UUID
  (`BT_UUID_QSBT_ID_VAL`, `b2007aaa-...`), not the LBS UUID, so the mobile app can tag this
  device as "quick start" in its scan list before connecting.

## Testing (on-hardware)

The tests under `test/` are **on-hardware bench tests**: they drive a connected
**nRF54L15 DK** over its USB serial console and BLE. There is no pure-host test suite.
**If no DK is connected, ask the user whether they want to connect an nRF54L15 DK so
you can verify functionality before running anything.** On macOS a connected DK shows
up as `/dev/tty.usbmodem*01/03` (VCOM1 = `…03`); no ports means no board.

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
