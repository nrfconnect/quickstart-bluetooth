# quickstart-bluetooth

[![Release](https://img.shields.io/github/v/release/nrfconnect/quickstart-bluetooth)](https://github.com/nrfconnect/quickstart-bluetooth/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/nrfconnect/quickstart-bluetooth/build.yml?event=push&branch=main&label=build)](https://github.com/nrfconnect/quickstart-bluetooth/actions/workflows/build.yml?query=branch%3Amain+event%3Apush)
[![Lint](https://img.shields.io/github/actions/workflow/status/nrfconnect/quickstart-bluetooth/lint.yml?event=push&branch=main&label=lint)](https://github.com/nrfconnect/quickstart-bluetooth/actions/workflows/lint.yml?query=branch%3Amain+event%3Apush)

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
| **Button 0** | LBS button characteristic - gateway/central sees the press (standard LBS). |
| **Button 1** | **Demo crash** - forces a fault (`k_oops`) to generate a Memfault coredump. Demo-only. |
| **LED 0** | Run status (1 Hz blink - firmware is alive). |
| **LED 1** | BLE connection status. |
| **LED 2** | LBS LED - controlled by the gateway/central (standard LBS). |

Once a gateway connects and the link is secured, the device sends a heartbeat
immediately, so it shows up in Memfault within seconds instead of waiting for the
periodic interval.

## Prerequisites

- The **nRF Connect SDK toolchain** matching this workspace's NCS base
  (currently **v3.3.x** - see the note under *Bootstrap*). Install it with the
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

> **Note - west version.** Run west from the NCS toolchain environment (its west
> is recent enough for this manifest schema); a system west older than ~v1.2 will
> reject it. With the Toolchain Manager:
> `nrfutil toolchain-manager launch --ncs-version v3.3.1 -- west update`.

## Build & flash

```sh
west build -b nrf54l15dk/nrf54l15/cpuapp --no-sysbuild project/app
west flash
```

The single `zephyr.hex` is the complete image - there is no MCUboot/sysbuild,
no DFU (OTA is out of scope).

## Provision the Memfault project key

The project key is set over the serial shell and applied on the **next boot**:

```sh
mflt set_project_key <your-32-char-project-key>
kernel reboot cold
```

`mflt set_project_key` persists the key, but it is read once at boot - the
`kernel reboot cold` is required for it to take effect. To verify it:

```sh
mflt set_project_key
Project key: <your-32-char-project-key>
```

> **Security note.** The key is stored **unencrypted** in settings storage (the
> same at-rest protection as baking it into flash). Runtime provisioning changes
> *how* the key arrives, not its confidentiality. For a hardened product, evaluate
> settings encryption / the nRF54L KMU / TF-M secure storage.

## Set the advertising name

The BLE advertising name is set over the serial shell and applied on the **next
boot**:

```sh
bt name <name>
kernel reboot cold
```

`bt name <name>` persists the name (settings key `bt/name`), but the
advertising data is only rebuilt on the next `kernel reboot cold`. To verify
it:

```sh
bt name
Bluetooth Local Name: <name>
```

This lets each device be given a distinct, recognizable name during
onboarding (e.g. per-kit or per-desk), overriding the build-time default
(`CONFIG_BT_DEVICE_NAME`, currently `Quickstart_Bluetooth`).

Use double quotes if the name has spaces, e.g. `bt name "My Quickstart"`.

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
   (paired) - MDS access is gated to the secured connection.
2. The device **appears in Memfault** within seconds with a reboot report.
3. Press **Button 1** to force a crash. After the device reconnects, the gateway
   uploads the coredump.

## Upload symbols for symbolication

Every build has a unique **GNU Build ID**. Upload the build's `zephyr.elf` to
Memfault so coredumps and traces are symbolicated - without a matching ELF,
Memfault shows *"Unknown location"*.

```sh
# zephyr.elf is produced next to zephyr.hex in the build directory:
#   build/zephyr/zephyr.elf
```

Upload it via the Memfault web app (Software → Symbol Files) or the Memfault CLI.
Re-upload on every firmware change; the Build ID changes each build.

## Releasing

See [RELEASE.md](RELEASE.md) for the release process, versioning scheme, and
cadence.
