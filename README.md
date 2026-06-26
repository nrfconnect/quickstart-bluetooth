# quickstart-bluetooth

A production nRF Connect SDK (NCS) application for the *nRF Connect for Desktop
Quick Start* guide. It is the `peripheral_lbs` sample (button/LED over Bluetooth LE)
with added [Memfault](https://memfault.com) observability: the device collects
heartbeat metrics and coredumps and serves them over the Memfault Diagnostic Service
(MDS) to a phone or desktop gateway, which uploads them to Memfault over HTTPS. The
device itself performs no HTTP.

**Supported board:** nRF54L15 DK (`nrf54l15dk/nrf54l15/cpuapp`).

## Build & flash

This is a [T2 west manifest](https://docs.zephyrproject.org/latest/develop/west/manifest.html)
repository. With the NCS toolchain installed:

```sh
west init -m https://github.com/<org>/quickstart-bluetooth my-workspace
cd my-workspace
west update

west build -b nrf54l15dk/nrf54l15/cpuapp quickstart-bluetooth/app
west flash
```

## Provision the Memfault project key

The project key is set over the serial shell and applied on the next boot:

```sh
settings write string memfault/project_key <your-32-char-project-key>
kernel reboot cold
```

## Try it

1. Connect to the device from the gateway — on mobile, use
   [nRF Toolbox](https://www.nordicsemi.com/Products/Development-tools/nRF-Toolbox).
   The device appears in Memfault shortly after connecting (a heartbeat is sent once
   the link is secured).
2. Press the crash button to force a fault and generate a coredump.
3. Upload `zephyr.elf` from the build to Memfault so coredumps are symbolicated.
