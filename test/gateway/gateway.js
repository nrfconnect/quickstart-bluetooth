/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/*
 * Minimal MDS gateway for the nRF54L15 DK quickstart-bluetooth firmware.
 * Node port of memfault/web-ble-example's mds.js, using @abandonware/noble.
 * Upstream reference: https://github.com/memfault/web-ble-example
 *
 * Default: BLE-only dry run (connect, drain chunks, hexdump) — NO upload.
 * Pass --upload to actually POST chunks to the Memfault data URI read from the device.
 *
 * Usage: node gateway.js [--upload] [--name Quickstart_Bluetooth] [--seconds 30]
 */

const noble = require("@abandonware/noble");

// noble uses lowercase, dash-stripped UUIDs
const MDS_SERVICE = "54220000f6a54007a371722f4ebd8436";
const CHAR = {
  supportedFeatures: "54220001f6a54007a371722f4ebd8436",
  deviceIdentifier: "54220002f6a54007a371722f4ebd8436",
  dataUri: "54220003f6a54007a371722f4ebd8436",
  authorization: "54220004f6a54007a371722f4ebd8436",
  dataExport: "54220005f6a54007a371722f4ebd8436",
};

const args = process.argv.slice(2);
const UPLOAD = args.includes("--upload");
const NAME = argVal("--name", "Quickstart_Bluetooth");
const SECONDS = parseInt(argVal("--seconds", "30"), 10);

function argVal(flag, def) {
  const i = args.indexOf(flag);
  return i !== -1 && args[i + 1] ? args[i + 1] : def;
}
function log(...a) {
  console.log(new Date().toISOString().slice(11, 23), ...a);
}
function hex(buf) {
  return Buffer.from(buf).toString("hex");
}

let expectedSeq = 0;
let chunksReceived = 0;
let bytesReceived = 0;
let uploaded = 0;
let dataUri = null;
let authHeader = null;

// Memfault reassembles chunks in the order they are POSTed, so uploads must be
// serialized. Firing fetches concurrently lets them arrive out of order and
// triggers "chunk missing" / CRC reassembly errors on large (coredump) streams.
const uploadQueue = [];
let draining = false;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function uploadChunk(data) {
  // authHeader looks like "Memfault-Project-Key:<key>"
  const idx = authHeader.indexOf(":");
  const key = authHeader.slice(0, idx);
  const val = authHeader.slice(idx + 1);
  const res = await fetch(dataUri, {
    method: "POST",
    headers: { [key]: val, "Content-Type": "application/octet-stream" },
    body: Buffer.from(data),
  });
  uploaded++;
  log(`  ↑ uploaded chunk ${uploaded} -> HTTP ${res.status}`);
  if (!res.ok) log("    body:", (await res.text()).slice(0, 200));
}

// Upload queued chunks one at a time, in arrival order, so Memfault receives
// them in sequence. Retries transient network failures a couple of times.
async function drainUploadQueue() {
  if (draining) return;
  draining = true;
  while (uploadQueue.length) {
    const data = uploadQueue.shift();
    for (let attempt = 1; ; attempt++) {
      try {
        await uploadChunk(data);
        break;
      } catch (e) {
        if (attempt >= 3) {
          log("  upload error (giving up):", e.message);
          break;
        }
        await sleep(200);
      }
    }
  }
  draining = false;
}

function handleChunk(data) {
  const sn = data[0];
  const payload = data.slice(1);
  chunksReceived++;
  bytesReceived += payload.length;
  log(
    `chunk #${chunksReceived} sn=${sn} len=${payload.length} data=${hex(payload).slice(0, 48)}${
      payload.length > 24 ? "…" : ""
    }`
  );
  if (expectedSeq !== sn) {
    log(`  ⚠ SEQUENCE GAP: expected ${expectedSeq} got ${sn}`);
  }
  expectedSeq = (sn + 1) % 32;
  if (UPLOAD) {
    uploadQueue.push(payload);
    drainUploadQueue();
  }
}

async function run(peripheral) {
  log(`Connecting to ${peripheral.advertisement.localName} (${peripheral.address || peripheral.id})`);
  await peripheral.connectAsync();
  log("Connected. Discovering MDS…");

  const { characteristics } = await peripheral.discoverSomeServicesAndCharacteristicsAsync(
    [MDS_SERVICE],
    Object.values(CHAR)
  );
  const byUuid = Object.fromEntries(characteristics.map((c) => [c.uuid, c]));

  log("Reading supported features…");
  const feat = await byUuid[CHAR.supportedFeatures].readAsync();
  log(`  SupportedFeatures: 0x${feat[0].toString(16)}`);

  const devId = (await byUuid[CHAR.deviceIdentifier].readAsync()).toString("utf8");
  dataUri = (await byUuid[CHAR.dataUri].readAsync()).toString("utf8");
  authHeader = (await byUuid[CHAR.authorization].readAsync()).toString("utf8");
  log(`  Device Identifier: ${devId}`);
  log(`  Data URI: ${dataUri}`);
  log(`  Authorization: ${authHeader.slice(0, authHeader.indexOf(":") + 1)}****`);

  const exportChar = byUuid[CHAR.dataExport];
  exportChar.on("data", (d) => handleChunk(d));
  await exportChar.subscribeAsync();
  log("Subscribed to chunk notifications. Enabling streaming (write 0x01)…");
  await exportChar.writeAsync(Buffer.from([0x01]), false);
  log(`Streaming for ${SECONDS}s. Upload=${UPLOAD ? "ON" : "OFF (dry run)"}`);

  setTimeout(async () => {
    try {
      await exportChar.writeAsync(Buffer.from([0x00]), false); // stop streaming
    } catch {
      // best-effort; we're tearing down the connection regardless.
    }
    // Finish uploading everything received (in order) before disconnecting.
    while (UPLOAD && (uploadQueue.length || draining)) {
      await sleep(100);
    }
    log(
      `--- done: ${chunksReceived} chunks, ${bytesReceived} bytes${
        UPLOAD ? `, ${uploaded} uploaded` : ""
      } ---`
    );
    try {
      await peripheral.disconnectAsync();
    } catch {
      // best-effort; we're exiting regardless.
    }
    process.exit(0);
  }, SECONDS * 1000);
}

noble.on("stateChange", async (state) => {
  log("BLE state:", state);
  if (state === "poweredOn") {
    log(`Scanning for "${NAME}" …`);
    await noble.startScanningAsync([], false);
  }
});

noble.on("discover", async (peripheral) => {
  const name = peripheral.advertisement.localName;
  if (name !== NAME) return;
  await noble.stopScanningAsync();
  try {
    await run(peripheral);
  } catch (e) {
    log("ERROR:", e.message);
    process.exit(1);
  }
});

setTimeout(() => {
  log("Timed out with no device / no completion.");
  process.exit(2);
}, (SECONDS + 30) * 1000);
