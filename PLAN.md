# quickstart-bluetooth — Implementation Plan

**Status:** Design basis (no task breakdown yet). This document defines scope,
architecture, and the split between upstream `sdk-nrf` work and the out-of-tree
`quickstart-bluetooth` repo. It is intended to be handed to an implementing
agent and then decomposed into tasks.

---

## 1. Goal & scope

Build a **production-ready** out-of-tree nRF Connect SDK application,
`quickstart-bluetooth`, used by the *nRF Connect for Desktop Quick Start* guide.
It is based on the `peripheral_lbs` sample and adds Memfault observability over
the Memfault Diagnostic Service (MDS) BLE gateway path: the device collects
heartbeat metrics and coredumps and serves chunks to a phone/desktop gateway
which performs the HTTPS upload to Memfault. The device never does on-device
HTTP.

**Decisions locked in (from review):**

| Area | Decision |
|------|----------|
| SDK-side changes | **Upstream to `sdk-nrf` first**; the quickstart repo depends on an `sdk-nrf` *main* SHA that already contains them. No long-lived fork. |
| Project-key provisioning | **Serial shell** (`settings write string memfault/project_key …`) driven by the desktop app. BLE provisioning is explicitly out of scope (note it as a future extension). |
| Boards | **nRF54L15 DK only** (`nrf54l15dk/nrf54l15/cpuapp`). |
| Feature scope | **Core Memfault only**: heartbeat metrics + coredump/crash upload + runtime project key, on top of the LBS button/LED base. **No MCUboot / MCUmgr / SMP / OTA.** |

**Consequences of "core only / no bootloader":**
- No `sysbuild.conf`, no `sysbuild.cmake`, no MCUboot FPROTECT 60 KB boot-partition
  overlay (all of which were needed only because OTA pulled in MCUboot).
- Coredump is **RAM-backed**, which needs no bootloader or flash partition.
- Single `zephyr.hex` is the complete image; no merged hex / signed hex / DFU zip.

---

## 2. Architecture & dependency model

### 2.1 West topology (T2 star, ATT-inspired)

`quickstart-bluetooth` is the **top-level manifest repository**. It imports
`sdk-nrf` (which in turn imports Zephyr and all NCS modules, including the
vendored `memfault-firmware-sdk`).

`west.yml` (repo root):

```yaml
manifest:
  version: "0.13"
  remotes:
    - name: ncs
      url-base: https://github.com/nrfconnect
  projects:
    - name: sdk-nrf
      remote: ncs
      repo-path: sdk-nrf
      revision: <PINNED main SHA that contains the upstreamed Memfault glue>
      import: true
  self:
    path: quickstart-bluetooth
```

- **Pin a SHA, not `main`**, for reproducible builds; document a bump policy
  (e.g. update the SHA deliberately, re-run CI). The "latest main" requirement
  is satisfied by choosing a recent SHA at integration time.
- This pulls the Memfault firmware SDK at whatever version that `sdk-nrf` SHA
  pins — see §3.3 (the runtime-key feature has a hard dependency on the
  Memfault SDK version).

### 2.2 Is the repo a Zephyr *module*?

ATT registers itself as a module via `zephyr/module.yml` because it ships shared
libraries/Kconfig. For this project the reusable glue is being **upstreamed into
`sdk-nrf`**, so the app has little or no shared out-of-tree code.

- **Default recommendation:** keep it simple — a plain Zephyr application under
  `app/`, built with `west build -b nrf54l15dk/nrf54l15/cpuapp app`. **No
  `zephyr/module.yml`.**
- Add `zephyr/module.yml` + top-level `CMakeLists.txt`/`Kconfig` **only if** an
  app-local shared library emerges (e.g. a provisioning helper not suitable for
  upstream). Keep that escape hatch in mind but don't build it preemptively.

---

## 3. What goes UPSTREAM into sdk-nrf (and the Memfault SDK)

These are **prerequisite PRs** that must merge to `sdk-nrf` main before the
quickstart repo pins its SHA. They generalize the local edits we validated on
the `peripheral_mds` branch.

### 3.1 NCS Memfault integration — runtime project key from settings

File: `modules/memfault-firmware-sdk/memfault_integration.c`
File: `modules/memfault-firmware-sdk/Kconfig`

- New Kconfig symbol **`MEMFAULT_PROJECT_KEY_SETTINGS`** (`bool`, `select
  SETTINGS`) — defines the feature. (Currently the symbol is *referenced* by
  Noah's commit but never *defined*, so the code path is dead. This PR makes it
  real.)
- A Zephyr settings handler registered for the **`memfault`** subtree
  (`SETTINGS_STATIC_HANDLER_DEFINE`) whose `h_set` copies the stored
  **`memfault/project_key`** value into a static buffer and points
  `g_mflt_http_client_config.api_key` at it, overriding the compile-time key.
- The Memfault `init()` already calls `settings_subsys_init()` +
  `settings_load_subtree("memfault")` under this guard; keep it, and keep the
  informational `settings_get_val_len("memfault/project_key")` check (it logs at
  ERR if no key is stored — useful diagnostics).
- Behaviour contract to document: a stored key overrides the compile-time
  `CONFIG_MEMFAULT_NCS_PROJECT_KEY`; with no stored key the compile-time value
  (possibly empty) is the fallback. **The key is applied on boot, not live** —
  `settings write` persists, a reboot applies. (Validated on hardware.)

Reference implementation (already built & hardware-tested on the branch):

```c
#if defined(CONFIG_MEMFAULT_PROJECT_KEY_SETTINGS)
#define MEMFAULT_PROJECT_KEY_MAX_LEN 32
static char s_project_key[MEMFAULT_PROJECT_KEY_MAX_LEN + 1];

static int memfault_settings_set(const char *name, size_t len,
                                 settings_read_cb read_cb, void *cb_arg)
{
    const char *next;
    if (settings_name_steq(name, "project_key", &next) && !next) {
        if (len > sizeof(s_project_key) - 1) { return -EINVAL; }
        ssize_t rc = read_cb(cb_arg, s_project_key, len);
        if (rc < 0) { return rc; }
        s_project_key[rc] = '\0';
        g_mflt_http_client_config.api_key = s_project_key;
        return 0;
    }
    return -ENOENT;
}
SETTINGS_STATIC_HANDLER_DEFINE(memfault, "memfault", NULL,
                               memfault_settings_set, NULL, NULL);
#endif
```

Upstream concerns to resolve in review:
- Where `g_mflt_http_client_config` is defined for the `BT_MDS &&
  !MEMFAULT_HTTP_ENABLE` case (today NCS conditionally defines it; the SDK only
  defines it when `!CONFIG_MEMFAULT_NCS_PROJECT_KEY`). Make the ownership of that
  symbol unambiguous so it links exactly once across NCS + Memfault SDK.
- Note the **double-load**: with `CONFIG_BT_SETTINGS`, the BT stack’s
  `settings_load()` and the Memfault init’s `settings_load_subtree("memfault")`
  both fire the handler. It’s idempotent, but consider gating the explicit load
  to avoid redundant work.

### 3.2 MDS Authorization characteristic

File: `subsys/bluetooth/services/mds.c`

- Build the `Memfault-Project-Key:<key>` Authorization value from the **live**
  `g_mflt_http_client_config.api_key` (already in Noah's commit 53383c1e) rather
  than a compile-time macro, so runtime key changes are reflected.
- **Fix the missing `MEMFAULT_PROJECT_KEY_LEN`**: the auth buffer is sized with
  this macro, which is *undefined* in the currently-vendored Memfault SDK
  (1.37.1). Our branch worked around it with a local `#ifndef … #define 32`.
  Upstream, the canonical definition should come from the Memfault SDK (see
  §3.3); `sdk-nrf` should depend on that rather than carry a private fallback.
  If the Memfault SDK version pinned by the target ncs SHA still lacks it, the
  PR must add a properly-scoped definition in NCS.

### 3.3 Memfault firmware SDK (third-party, vendored via west) — **investigate first**

This is the **critical dependency and biggest open risk.** Noah's commit message
references `CONFIG_MEMFAULT_PROJECT_KEY_RUNTIME` "added to memfault-firmware-sdk",
but that symbol **does not exist** in the SDK version this workspace pins
(1.37.1, commit `c63797fd92`) or any local branch. The canonical runtime-key
support (runtime-settable `api_key`, and a defined `MEMFAULT_PROJECT_KEY_LEN`)
belongs in the Memfault SDK.

Required investigation before committing to a plan:
- Determine whether a **newer Memfault SDK release** provides native runtime
  project-key support (`CONFIG_MEMFAULT_PROJECT_KEY_RUNTIME` or equivalent) and
  defines `MEMFAULT_PROJECT_KEY_LEN`.
- If yes: the path is **bump the Memfault SDK in `sdk-nrf`** to that release,
  then build the NCS settings glue (§3.1) on top, and drop the private macro
  fallback (§3.2). The quickstart SHA must include this bump.
- If no: contribute the mechanism to the Memfault SDK (or carry a minimal,
  clearly-scoped NCS-side definition) — and flag that this widens the upstream
  effort.

---

## 4. What goes into the quickstart-bluetooth repo

### 4.1 Repository layout (minimal, ATT-inspired)

```
quickstart-bluetooth/
├── README.md                     # getting started + Memfault demo walkthrough
├── LICENSE                       # license decision — see §7
├── west.yml                      # T2 manifest, pins sdk-nrf main SHA (§2.1)
├── .github/
│   └── workflows/
│       └── build.yml             # west init/update + build for nrf54l15dk + (later) twister
├── .gitignore                    # ignore build/, .west/, etc.
└── app/
    ├── CMakeLists.txt            # standard Zephyr app (find_package(Zephyr))
    ├── prj.conf                  # all config (§4.3)
    ├── Kconfig                   # app-specific options if any (likely thin)
    ├── VERSION                   # ATT-style Zephyr version file; source of truth (§4.5)
    ├── boards/                   # only if a board overlay/conf proves necessary
    └── src/
        ├── main.c                # LBS base + Memfault/MDS wiring (§4.2)
        └── (optional) memfault_handlers.c  # heartbeat-on-connect, crash trigger
```

Deliberately **absent** vs the old mds sample: `sysbuild.conf`,
`sysbuild.cmake`, `boards/*mcuboot*`, signed/merged hex artifacts — none needed
without OTA.

### 4.2 Application source (`app/src`)

Start from `peripheral_lbs/src/main.c` (LBS button/LED) and fold in the Memfault
pieces proven in the `peripheral_mds` work:

- **MDS service**: register `bt_mds_cb` with an `access_enable` callback that
  gates MDS access to the authenticated/connected gateway connection.
- **Heartbeat-on-connect**: in the `security_changed` callback, once the link
  reaches the required security level, call
  `memfault_metrics_heartbeat_debug_trigger()` once so the device appears in
  Memfault shortly after connecting instead of waiting for the periodic timer.
- **Crash trigger (demo)**: keep a button that forces a fault (the LBS sample
  has buttons; map one to a divide-by-zero or `k_oops`) so the guide can
  demonstrate a coredump. Clearly comment it as demo-only.
- Keep the LBS LED/button behaviour so the app is still a recognizable LBS
  device for the Quick Start guide — the GATT LBS service/characteristics stay
  standard regardless of what's advertised.
- **App-identity service**: register an empty vendor GATT service
  (`b2007aaa-c203-43a5-8b6f-a7f3d001a1e0`) purely so the mobile app can mark
  this firmware. Its UUID is advertised in the scan response (replacing the
  LBS UUID there) so the mobile app can tag the device as "quick start" in
  its scan list before connecting.
- Decide whether heartbeat-on-connect/crash glue lives inline in `main.c` or a
  small `memfault_handlers.c` (cleaner; recommended).

### 4.3 `prj.conf` (carried over and de-OTA'd)

Core groups (values validated on hardware, re-measure coredump size for the LBS
build — see §6):

```ini
# Base BLE + LBS
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_SMP=y                 # MDS access control requires a secured link
CONFIG_BT_DEVICE_NAME="Nordic_Memfault"   # confirm desired name with guide
CONFIG_BT_LBS=y
CONFIG_BT_LBS_POLL_BUTTON=y     # per LBS sample
CONFIG_DK_LIBRARY=y

# MDS gateway path
CONFIG_BT_MDS=y
CONFIG_BT_MDS_DATA_POLL_INTERVAL=1000      # drain chunks ~1s for snappy demo

# Memfault core
CONFIG_MEMFAULT=y
CONFIG_MEMFAULT_SHELL=y
CONFIG_MEMFAULT_NCS_FW_TYPE="main"
# Firmware version is derived from app/VERSION (§4.5) — do NOT hardcode it.
# With STATIC selected, CONFIG_MEMFAULT_NCS_FW_VERSION defaults to
# "$(APP_VERSION_TWEAK_STRING)" whenever a VERSION file is present.
CONFIG_MEMFAULT_NCS_FW_VERSION_STATIC=y
CONFIG_MEMFAULT_METRICS_HEARTBEAT_INTERVAL_SECS=60
CONFIG_MEMFAULT_EVENT_STORAGE_SIZE=4096
CONFIG_MEMFAULT_RAM_BACKED_COREDUMP=y
CONFIG_MEMFAULT_RAM_BACKED_COREDUMP_SIZE=16384   # re-measure with `mflt coredump_size`

# Runtime project key (the upstreamed feature)
CONFIG_MEMFAULT_PROJECT_KEY_SETTINGS=y
CONFIG_MEMFAULT_NCS_PROJECT_KEY=""         # compile-time fallback; "" = pure runtime
# (or ship the Quickstart Shared Project key here as a convenience default)

# Settings storage + serial provisioning
CONFIG_BT_SETTINGS=y
CONFIG_FLASH=y
CONFIG_FLASH_MAP=y
CONFIG_SETTINGS=y
CONFIG_SETTINGS_SHELL=y         # provides `settings write/read/delete`
CONFIG_SHELL=y
CONFIG_REBOOT=y                 # `kernel reboot cold` after provisioning
CONFIG_KERNEL_SHELL=y

# Unique device ID from FICR via hw_id (discoverable with nrfutil)
CONFIG_MEMFAULT_NCS_DEVICE_ID_HW_ID=y
CONFIG_HW_ID_LIBRARY_SOURCE_DEVICE_ID=y

# Device Information Service (nice-to-have metadata)
CONFIG_BT_DIS=y
# … serial/hw/sw/fw revision strings as desired
```

Open value decisions to confirm: device name, whether to bake the Quickstart
Shared Project key as a fallback or ship empty, final heartbeat/poll cadence for
the guide, coredump size after measuring the LBS build.

### 4.4 README / docs (production)

The README is part of the deliverable. It must cover:
- Prerequisites and **`west init -m https://github.com/<org>/quickstart-bluetooth …` →
  `west update`** workflow (T2 bootstrap).
- Build & flash for `nrf54l15dk/nrf54l15/cpuapp`.
- **Provision the project key over serial**:
  `settings write string memfault/project_key <32-char-key>` then
  `kernel reboot cold` (and the *requires reboot* caveat).
- Connecting via the phone/desktop gateway and what to expect in Memfault
  (device appears on connect via heartbeat-on-connect; press the crash button to
  see a coredump).
- **Symbol upload**: each build has a unique GNU Build ID; upload
  `app/build/.../zephyr.elf` to Memfault for symbolication (mismatch ⇒ "Unknown
  location"). Consider automating this in CI.
- How to find the device ID with `nrfutil` (matches the Memfault device serial).

### 4.5 Application version (`app/VERSION`) — ATT-style

Mirror the Asset-Tracker-Template approach: a Zephyr-format `VERSION` file in the
application directory (`app/VERSION`) is the **single source of truth** for the
firmware version. Zephyr's build system reads it automatically and generates
`app_version.h` (`APP_VERSION_STRING`, `APP_VERSION_TWEAK_STRING`,
`APP_VERSION_NUMBER`, …) and exports the fields as Kconfig preprocessor env vars
(`$(VERSION_MAJOR)`, `$(APP_VERSION_TWEAK_STRING)`, …).

`app/VERSION` (same format/fields as ATT):

```
VERSION_MAJOR = 1
VERSION_MINOR = 0
PATCHLEVEL = 0
VERSION_TWEAK = 0
EXTRAVERSION = dev
```

**Why this is all we need to wire Memfault:** the NCS Memfault integration
already defaults the reported firmware version to the app version when a VERSION
file exists. From `sdk-nrf` `modules/memfault-firmware-sdk/Kconfig`:

```kconfig
config MEMFAULT_NCS_FW_VERSION
	depends on MEMFAULT_NCS_FW_VERSION_STATIC
	default "$(APP_VERSION_TWEAK_STRING)" if "$(VERSION_MAJOR)" != ""
```

So with `CONFIG_MEMFAULT_NCS_FW_VERSION_STATIC=y` and **no** explicit
`CONFIG_MEMFAULT_NCS_FW_VERSION`, the Memfault "software version" becomes e.g.
`1.0.0+0`, tied to `app/VERSION`. Bumping a release = editing `app/VERSION` only.

Recommendations:
- Prefer **STATIC** (semantic, reproducible versions from `app/VERSION`) over
  `MEMFAULT_NCS_FW_VERSION_AUTO` (regenerated git/commit string every build) so
  Memfault release/issue grouping is stable for the guide.
- Drop `EXTRAVERSION = dev` (or set it per release process) when cutting tagged
  builds; document the bump policy alongside the `sdk-nrf` SHA bump policy (§7).
- Optionally surface the same version in the DIS firmware-revision string by
  templating it in Kconfig, e.g. `CONFIG_BT_DIS_FW_REV_STR="$(APP_VERSION_STRING)"`
  (verify the env-var expansion in a string Kconfig before relying on it), so DIS
  and Memfault report one consistent version.
- The GNU Build ID (used for symbolication) is independent of this version and
  still changes per build — keep the symbol-upload guidance in the README (§4.4).

---

## 5. Runtime project-key design (detail)

- **Settings key:** `memfault/project_key`, string, max 32 chars (Memfault keys
  are 32 chars).
- **Provisioning (chosen path):** Zephyr settings shell over USB/UART:
  - `settings write string memfault/project_key <key>` → persists to settings
    storage (ZMS on nRF54L).
  - `settings read string memfault/project_key` → verify.
  - `settings delete memfault/project_key` → revert to compile-time fallback.
  - **Apply requires `kernel reboot cold`** — write persists but the handler runs
    at boot, not live.
- **Security note (must be in docs / risk register):** the key is stored
  **unencrypted** in settings storage, equivalent to baking it into flash today.
  This changes *how* the key arrives, not its at-rest protection. For a hardened
  product, evaluate settings encryption / nRF54L KMU / TF-M secure storage. Call
  this out explicitly; don't imply runtime provisioning adds confidentiality.
- **Future extension (out of scope):** a BLE GATT characteristic (or SMP) that
  writes the same settings key, so the desktop app can provision without a
  serial console. Design the settings key now so this drops in later.

---

## 6. Memfault feature wiring & verification

- **Heartbeat:** periodic (`HEARTBEAT_INTERVAL_SECS`) + one-shot on secure
  connect. Metrics content is not important for the guide; device version /
  serial visibility is the value.
- **Coredump:** RAM-backed. **Re-measure** with the `mflt coredump_size` shell
  command on the *LBS* build (stack/region layout differs from the mds sample;
  our mds build required ~9.3 KB). Size `RAM_BACKED_COREDUMP_SIZE` with headroom.
  Note: Memfault *truncates* an oversized dump (registers written first), so a
  backtrace survives even if undersized — but size it properly anyway.
- **Device ID:** from FICR `DEVICEID` via `hw_id` (`hwinfo_get_device_id()`),
  16 hex chars; discoverable from PC with `nrfutil` so support can correlate a
  physical board to its Memfault device.
- **Upload path:** device serves chunks via MDS; the gateway (phone/desktop)
  performs HTTPS upload using the project key read from the MDS Authorization
  characteristic. No on-device HTTP, no TLS certs on device.
- **End-to-end acceptance test** (mirror what we did by hand): provision key →
  reboot → connect gateway → confirm device + heartbeat in Memfault → trigger
  crash → confirm coredump symbolicated (after elf upload).

---

## 7. Production-readiness concerns

- **Versioning:** ATT-style `app/VERSION` is the single source of truth (§4.5).
  It auto-populates the Memfault firmware version via the
  `MEMFAULT_NCS_FW_VERSION` default (`$(APP_VERSION_TWEAK_STRING)`) and can
  template the DIS FW-revision string. Document the release bump policy (edit
  `app/VERSION`, manage `EXTRAVERSION`) and how Memfault "software version" maps
  to releases.
- **License & headers:** decide repo license (ATT uses Apache-2.0; NCS samples
  use LicenseRef-Nordic-5-Clause). Pick one, apply consistent SPDX headers.
  **Open item — confirm with the owning team.**
- **CI:** GitHub Actions that does `west init`/`update` against the pinned SHA
  and builds `nrf54l15dk/nrf54l15/cpuapp`. Add twister/build-only smoke test.
  Optionally auto-upload symbols to Memfault on tagged builds.
- **SHA bump policy:** documented, deliberate updates of the `sdk-nrf` revision;
  CI must pass before bumping.
- **Reproducibility:** pinned SHA + toolchain version documented (NCS toolchain
  bundle / `west sdk`).
- **No secrets in repo:** if a default project key is baked in, confirm it is the
  intentionally-public *Quickstart Shared Project* key, not a private one.
- **Testing:** at minimum build-CI; ideally a hardware-in-the-loop or twister
  scenario for the settings-handler logic.

---

## 8. Open risks / things to confirm before task breakdown

1. **Memfault SDK runtime-key support (§3.3)** — does a released Memfault SDK
   version provide it, and will the target ncs main SHA pin that version? This
   gates the entire upstream-first plan. Investigate first.
2. **Exact `sdk-nrf` main SHA** to pin (must contain the merged §3.1–§3.2 work
   and the Memfault SDK bump).
3. **Coredump size** for the LBS-based build (re-measure).
4. **Repo license** and SPDX header convention.
5. **Default project key** policy (empty vs baked Quickstart Shared key).
6. **Owning org / repo URL** for the `west init -m` instructions and CI.
7. Whether the Quick Start guide needs the LBS UI behaviour preserved verbatim
   or only as a thin base.

---

## 9. Summary of the upstream/out-of-tree split

| Concern | Home |
|---------|------|
| Runtime-key settings handler + `MEMFAULT_PROJECT_KEY_SETTINGS` Kconfig | **sdk-nrf** (`modules/memfault-firmware-sdk`) |
| MDS auth char reads live `api_key`; `MEMFAULT_PROJECT_KEY_LEN` fix | **sdk-nrf** (`subsys/bluetooth/services/mds.c`) |
| Canonical runtime `api_key` / `MEMFAULT_PROJECT_KEY_LEN` | **Memfault firmware SDK** (vendored; bump or contribute) |
| App: LBS base + MDS callback + heartbeat-on-connect + crash button | **quickstart-bluetooth** (`app/src`) |
| App config (`prj.conf`), device ID, coredump/heartbeat sizing, serial provisioning enablement | **quickstart-bluetooth** |
| West manifest (T2), CI, README, license, versioning | **quickstart-bluetooth** |
| Key provisioning *transport* (serial shell) | **quickstart-bluetooth** (enablement) + desktop-app team (UX) |
