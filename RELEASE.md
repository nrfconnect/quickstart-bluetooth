# Releasing

## Cadence

Releases are cut on demand, not on a fixed schedule — whenever there's a
firmware change worth shipping to the guide.

## Versioning scheme

Versions are `MAJOR.MINOR.PATCH` (optionally `-SUFFIX` for pre-releases, e.g.
`1.2.3-rc1`), following [Semantic Versioning](https://semver.org/). Git tags
are always `v`-prefixed (`v1.2.3`); the firmware-reported version is not.

`app/VERSION` (Zephyr/Asset-Tracker-Template format) is the single source of
truth for the firmware version, but it is **not hand-edited for a release** —
the committed file stays at `0.0.0-dev`. The release workflow regenerates it
from the `version` input via `scripts/app_version.py` before building, so the
firmware reports the release version to Memfault
(`CONFIG_MEMFAULT_NCS_FW_VERSION`, which defaults to
`$(APP_VERSION_TWEAK_STRING)`, e.g. `1.2.3+0`).

## Changelog / release notes

There is no hand-maintained `CHANGELOG.md`. GitHub Release notes are
auto-generated from merged PRs (`gh release create --generate-notes`) at
publish time — see the release history on the
[Releases page](../../releases).

## How to cut a release

Releases are cut by the **Release** GitHub Actions workflow
(`.github/workflows/release.yml`), started manually from the Actions tab.
Given a version, it:

1. validates the version format and derives the git tag + Memfault software
   version (`scripts/app_version.py`);
2. builds the firmware with `app/VERSION` set to that version
   (`build-app.yml`), so the device reports the release version to Memfault;
3. zips `zephyr.hex` + `zephyr.elf`;
4. uploads `zephyr.elf` as symbols to the Memfault
   `quickstart-shared-project` (registers the software version for
   symbolication);
5. tags the target commit and creates a GitHub release with the zip attached.

Inputs:

- **version** (required) — e.g. `v1.2.3`, or `v1.2.3-rc1` for a pre-release.
  The leading `v` is optional; the tag is always `vX.Y.Z` and the firmware
  version is `X.Y.Z`. An invalid format is rejected.
- **sha** (optional) — commit to tag/release; defaults to the latest commit.
- **dry_run** — build and upload symbols only; skip the git tag and GitHub
  release. Use this to prove `app/VERSION` generation and build output before
  cutting a real release.

## Required repository configuration

- secret `MEMFAULT_ORG_TOKEN` — Organization Auth Token (Bearer) with upload
  rights.
- secret `MEMFAULT_PROJECT_KEY` — project key baked into the build via
  `CONFIG_QSBT_DEFAULT_PROJECT_KEY`. Applied as the default key on first boot;
  a key later written over the settings shell still overrides it.
- var `MEMFAULT_ORG_SLUG` — Memfault organization slug (from the dashboard
  URL).
- var/secret `MEMFAULT_PROJECT` — Memfault project slug symbols are uploaded
  to.
- `GITHUB_TOKEN` is provided automatically; `contents: write` lets it tag and
  create the release.
