/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/* Enumerate ALL GATT services/characteristics on the DK and flag our UUID. */
const noble = require("@abandonware/noble");

const NAME = "Quickstart_Bluetooth";
const OUR_SVC = "b2007aaac20343a58b6fa7f3d001a1e0"; // b2007aaa-c203-43a5-8b6f-a7f3d001a1e0

function dash(u) {
  if (u.length !== 32) return u;
  return `${u.slice(0,8)}-${u.slice(8,12)}-${u.slice(12,16)}-${u.slice(16,20)}-${u.slice(20)}`;
}

noble.on("stateChange", async (s) => {
  if (s === "poweredOn") await noble.startScanningAsync([], false);
});

noble.on("discover", async (p) => {
  if (p.advertisement.localName !== NAME) return;
  await noble.stopScanningAsync();
  console.log(`Connecting to ${NAME}…`);
  await p.connectAsync();
  const { services, characteristics } =
    await p.discoverAllServicesAndCharacteristicsAsync();
  console.log(`\nDiscovered ${services.length} services:\n`);
  for (const svc of services) {
    const mark = svc.uuid === OUR_SVC ? "  <-- OUR APP-IDENTITY SERVICE" : "";
    console.log(`• ${dash(svc.uuid)}${mark}`);
    const chars = characteristics.filter((c) => c._serviceUuid === svc.uuid);
    for (const c of chars) {
      console.log(`    - char ${dash(c.uuid)} [${c.properties.join(",")}]`);
    }
  }
  const found = services.some((s) => s.uuid === OUR_SVC);
  console.log(`\n${found ? "✅ FOUND" : "❌ NOT FOUND"} app-identity service ${dash(OUR_SVC)}`);
  await p.disconnectAsync();
  process.exit(0);
});

setTimeout(() => { console.log("timeout"); process.exit(2); }, 30000);
