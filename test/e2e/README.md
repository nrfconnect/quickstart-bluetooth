# End-to-end tests

Bench tests for the Memfault project-key provisioning over the serial shell.
They drive the DK's console with pyserial, so run them through the **NCS
toolchain Python** (which ships pyserial). Connect the DK and note its VCOM1
port (`/dev/tty.usbmodem*03` on macOS).

```sh
nrfutil toolchain-manager launch --ncs-version v3.3.1 --chdir <workspace> -- \
    python3 quickstart-bluetooth/test/e2e/<test>.py [options]
```

## `test_project_key.py` — command contract (offline, no cloud)

Validates the `settings` shell contract for `memfault/project_key`:

1. read after a clean flash returns **Setting not found**;
2. write + read returns the written value;
3. the value **persists across a cold reboot** (ZMS backend);
4. delete returns to the unset state.

```sh
# device already flashed; checks current behaviour and leaves the key cleared
… python3 quickstart-bluetooth/test/e2e/test_project_key.py

# genuinely check the post-flash state by erasing first (needs a build dir)
QSBT_BUILD_DIR=<workspace>/build \
… python3 quickstart-bluetooth/test/e2e/test_project_key.py --recover
```

Exit code is non-zero if any check fails.

## `test_project_switch_e2e.py` — cloud e2e (project switching)

Proves that switching the project key over the shell re-targets the device to
that project in Memfault: for each configured project it writes the key,
reboots, runs the BLE gateway (`../gateway`) with `--upload`, then polls the
Memfault REST API until the device's `last_seen` advances.

Needs Node on PATH (for the gateway) and a Memfault API credential — an
Organization Auth Token (Bearer, preferred) or a User API key (HTTP Basic).
Secrets are read from the environment or an untracked repo-root `.env` — copy
`.env.example`:

```sh
cp quickstart-bluetooth/.env.example quickstart-bluetooth/.env
# edit .env with your API token, org slug, and the project(s) to test

cd quickstart-bluetooth/test/gateway && npm install && cd -
# the test loads quickstart-bluetooth/.env by default
… python3 quickstart-bluetooth/test/e2e/test_project_switch_e2e.py
```

The repo-root `.env` is gitignored. Configure at least `MEMFAULT_PROJECT_B_*`
(the project to switch to); add `MEMFAULT_PROJECT_A_*` to also test a baseline
project first.
