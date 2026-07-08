# Copyright (c) 2026 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#
# quickstart-bluetooth application (peripheral_lbs + Memfault over MDS).
# Plain Zephyr application — no sysbuild, no MCUboot.

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(quickstart_bluetooth)

target_sources(app PRIVATE src/main.c)

# Temporary workaround until this fix is upstreamed:
# https://github.com/memfault/memfault-firmware-sdk/pull/120
zephyr_compile_definitions(MEMFAULT_PROJECT_KEY_LEN=32)
