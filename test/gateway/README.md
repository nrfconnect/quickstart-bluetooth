# MDS test gateway (phone-free)

A small Node.js gateway that acts as the phone/desktop side of the Memfault
Diagnostic Service (MDS) path, so you can verify the `quickstart-bluetooth`
firmware end-to-end **without the mobile app**. It connects to the DK over
Bluetooth Low Energy, secures the link, drains Memfault chunks from the MDS
data-export characteristic, and (optionally) forwards them to the Memfault
cloud — exactly what the *nRF Connect for Desktop Quick Start* gateway does.

It is a Node/[`@abandonware/noble`](https://github.com/abandonware/noble) port of
Memfault's Web Bluetooth example, <https://github.com/memfault/web-ble-example>.

## Requirements

- **macOS** (uses CoreBluetooth via noble; Linux works with BlueZ but is untested here).
- **Node.js 18+** (uses the built-in `fetch`).
- A supported DK (`nrf54l15dk`, `nrf54lm20dk`, or `nrf54h20dk`) flashed with this
  firmware and advertising as `Quickstart_Bluetooth`.
- On first run, macOS will ask to grant your terminal **Bluetooth** permission
  (System Settings → Privacy & Security → Bluetooth). The just-works pairing the
  firmware uses is handled automatically by CoreBluetooth — no manual dialog.

## Install

```sh
cd test/gateway
npm install
```

## Enumerate the GATT database

Lists every service/characteristic on the device and flags the app-identity
service. Useful as a quick connectivity smoke test:

```sh
npm run discover        # or: node discover.js
```

## Run the gateway

**Dry run (default) — BLE only, no upload.** Connects, secures, and hexdumps the
drained chunks so you can confirm streaming works without touching the cloud:

```sh
npm run gateway         # or: node gateway.js
```

**Forward to Memfault.** POSTs each chunk to the data URI and project key read
*from the device* (the baked-in public Quickstart Shared key), so data lands in
the shared demo project:

```sh
node gateway.js --upload
```

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--upload` | off | Actually POST chunks to Memfault (omit for a dry run) |
| `--name <str>` | `Quickstart_Bluetooth` | Advertised device name to connect to |
| `--seconds <n>` | `30` | How long to stream before stopping and disconnecting |

## Exercising a coredump

1. Run the gateway once so the device is known/paired.
2. Press **Button 2** on the DK (the demo crash → `k_oops`; on a `0`-labelled DK
   silkscreen this is the button labelled **`1`**). The device captures a
   RAM-backed coredump and reboots. Don't power-cycle — a RAM-backed coredump
   does not survive a cold reset.
3. Run `node gateway.js --upload` again to drain and forward the coredump chunks.

To get a readable backtrace in Memfault, upload the matching `zephyr.elf` (same
build) to the Memfault project — it is symbolicated by GNU Build ID.
