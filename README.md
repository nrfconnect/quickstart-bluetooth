# quickstart-bluetooth

A production [nRF Connect SDK](https://www.nordicsemi.com/Products/Development-software/nrf-connect-sdk)
(NCS) application for the *nRF Connect for Desktop Quick Start* guide. It is the
`peripheral_lbs` sample (button/LED over Bluetooth® LE) with added
[Memfault](https://memfault.com) observability: the device collects heartbeat
metrics and coredumps and serves them over the Memfault Diagnostic Service (MDS)
to a phone or desktop **gateway**, which uploads them to Memfault over HTTPS.
**The device itself performs no HTTP/TLS.**

**Supported board:** nRF54L15 DK (`nrf54l15dk/nrf54l15/cpuapp`). This is the only
supported target.

## What the device does

| Control | Behaviour |
|---------|-----------|
| **Button 0** | LBS button characteristic — gateway/central sees the press (standard LBS). |
| **Button 1** | **Demo crash** — forces a fault (`k_oops`) to generate a Memfault coredump. Demo-only. |
| **LED 0** | Run status (1 Hz blink — firmware is alive). |
| **LED 1** | BLE connection status. |
| **LED 2** | LBS LED — controlled by the gateway/central (standard LBS). |

Once a gateway connects and the link is secured, the device sends a heartbeat
immediately, so it shows up in Memfault within seconds instead of waiting for the
periodic interval.

## Prerequisites

- The **nRF Connect SDK toolchain** matching this workspace's NCS base
  (currently **v3.3.x** — see the note under *Bootstrap*). Install it with the
  [Toolchain Manager](https://docs.nordicsemi.com/bundle/ncs-latest/page/nrf/installation/install_ncs.html)
  or `nrfutil`.
- [`nrfutil`](https://www.nordicsemi.com/Products/Development-tools/nrf-util) for
  flashing and reading the device ID.
- A Memfault account and a **32-character project key**.

## Bootstrap (T2 west workspace)

This repository is the **top-level west manifest** (T2 star topology). It imports
`sdk-nrf`, which pulls Zephyr and all NCS modules.

```sh
west init -m https://github.com/nrfconnect/quickstart-bluetooth my-workspace
cd my-workspace
west update
```

> **Note — west version.** Run west from the NCS toolchain environment (its west
> is recent enough for this manifest schema); a system west older than ~v1.2 will
> reject it. With the Toolchain Manager:
> `nrfutil toolchain-manager launch --ncs-version v3.3.1 -- west update`.
>
> **Note — temporary manifest pin.** `west.yml` currently pins a temporary
> `sdk-nrf` fork that carries the runtime Memfault project-key support this app
> needs while that work is upstreamed. It will be swapped to an upstream SHA
> later; see the header comment in `west.yml`. The bootstrap commands are
> unaffected.

## Build & flash

```sh
west build -b nrf54l15dk/nrf54l15/cpuapp --no-sysbuild project/app
west flash
```

The single `zephyr.hex` is the complete image — there is no MCUboot/sysbuild,
no DFU (OTA is out of scope).

## Provision the Memfault project key

The project key is set over the serial shell and applied on the **next boot**:

```sh
settings write string memfault/project_key <your-32-char-project-key>
kernel reboot cold
```

`settings write` persists the key, but it is read once at boot — the
`kernel reboot cold` is required for it to take effect. To verify or clear it:

```sh
settings read string memfault/project_key     # verify
settings delete memfault/project_key           # revert to the compile-time fallback
```

> **Security note.** The key is stored **unencrypted** in settings storage (the
> same at-rest protection as baking it into flash). Runtime provisioning changes
> *how* the key arrives, not its confidentiality. For a hardened product, evaluate
> settings encryption / the nRF54L KMU / TF-M secure storage.

## Find the device ID

The Memfault device serial is the FICR device ID. Read it from the PC:

```sh
nrfutil device device-info     # or: nrfutil device list
```

This lets support correlate a physical board with its Memfault device.

## Try it end-to-end

1. **Connect** from a gateway. On mobile, use
   [nRF Toolbox](https://www.nordicsemi.com/Products/Development-tools/nRF-Toolbox);
   on desktop, the nRF Connect for Desktop gateway. The link must be secured
   (paired) — MDS access is gated to the secured connection.
2. The device **appears in Memfault** within seconds (heartbeat-on-connect).
3. Press **Button 1** to force a crash. After the device reconnects, the gateway
   uploads the coredump.

## Upload symbols for symbolication

Every build has a unique **GNU Build ID**. Upload the build's `zephyr.elf` to
Memfault so coredumps and traces are symbolicated — without a matching ELF,
Memfault shows *"Unknown location"*.

```sh
# zephyr.elf is produced next to zephyr.hex in the build directory:
#   build/zephyr/zephyr.elf
```

Upload it via the Memfault web app (Software → Symbol Files) or the Memfault CLI.
Re-upload on every firmware change; the Build ID changes each build.

## Releasing

Releases are cut by the **Release** GitHub Actions workflow
(`.github/workflows/release.yml`), started manually from the Actions tab. Given a
version, it builds the firmware at that version, uploads symbols to Memfault, tags
the commit, and publishes a GitHub release with `zephyr.hex` + `zephyr.elf`
attached.

Inputs:

- **version** (required) — e.g. `v1.2.3`, or `v1.2.3-rc1` for a pre-release. The
  leading `v` is optional; the tag is always `vX.Y.Z` and the firmware version is
  `X.Y.Z`. An invalid format is rejected.
- **sha** (optional) — commit to tag/release; defaults to the latest commit.
- **dry_run** — build and upload symbols only; skip the git tag and GitHub release.
