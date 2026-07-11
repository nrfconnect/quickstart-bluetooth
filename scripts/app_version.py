#!/usr/bin/env python3
"""Parse a release version string into Zephyr VERSION-file fields.

A release is identified by ``vMAJOR.MINOR.PATCH`` with an optional ``-SUFFIX``
(e.g. ``v1.2.3`` or ``v1.2.3-rc1``); the leading ``v`` is optional. Validates
that string and emits the fields to overwrite ``app/VERSION`` at build time in
the release workflow.

Modes:
  version-file  (default) the 5 VERSION lines, ready to write to app/VERSION
  tag                     the normalised git tag (always ``v``-prefixed)

Exits non-zero with a clear message if the version string is malformed, which
is how the workflow's validation step rejects bad input.
"""

import argparse
import sys


def parse_version(ref: str):
    """Return (major, minor, patch, extra) for a vX.Y.Z[-suffix] string.

    Raises ValueError on anything that is not at least three dot-separated
    numeric components. ``extra`` keeps only the alphanumeric characters of the
    suffix after the first hyphen (e.g. ``rc1``), matching the ATT parser.
    """
    s = ref.strip()
    if s.startswith("v") or s.startswith("V"):
        s = s[1:]

    parts = s.split(".")
    if len(parts) < 3:
        raise ValueError(
            f"invalid version {ref!r}: expected vMAJOR.MINOR.PATCH[-SUFFIX] "
            f"(e.g. v1.2.3 or v1.2.3-rc1)"
        )

    third = parts[2]
    extra = ""
    if "-" in third:
        patch_str, suffix = third.split("-", 1)
        extra = "".join(c for c in suffix if c.isalnum())
    else:
        patch_str = third

    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(patch_str)
    except ValueError as e:
        raise ValueError(
            f"invalid version {ref!r}: MAJOR, MINOR and PATCH must be integers"
        ) from e

    return major, minor, patch, extra


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", help="release version, e.g. v1.2.3 or v1.2.3-rc1")
    ap.add_argument("--mode", choices=["version-file", "tag"],
                    default="version-file",
                    help="what to print (default: version-file)")
    args = ap.parse_args()

    try:
        major, minor, patch, extra = parse_version(args.version)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.mode == "version-file":
        lines = [
            f"VERSION_MAJOR = {major}",
            f"VERSION_MINOR = {minor}",
            f"PATCHLEVEL = {patch}",
            "VERSION_TWEAK = 0",
        ]
        # Leave EXTRAVERSION out for final releases so Memfault release/issue
        # grouping stays on stable semantic versions (app/VERSION policy).
        if extra:
            lines.append(f"EXTRAVERSION = {extra}")
        print("\n".join(lines))
    elif args.mode == "tag":
        tag = f"v{major}.{minor}.{patch}"
        if extra:
            tag += f"-{extra}"
        print(tag)

    return 0


if __name__ == "__main__":
    sys.exit(main())
