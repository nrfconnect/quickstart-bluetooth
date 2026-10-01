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

# Per-board app-identity UUID suffix (last 48 bits of BT_UUID_QSBT_ID_VAL), so
# the mobile app can tell boards apart without a hand-maintained table here.
string(SHA1 qsbt_board_hash "${CONFIG_BOARD}")
string(SUBSTRING "${qsbt_board_hash}" 0 12 qsbt_board_suffix)
target_compile_definitions(app PRIVATE QSBT_ID_BOARD_SUFFIX=0x${qsbt_board_suffix}ULL)

# Temporary workaround until this fix is upstreamed:
# https://github.com/memfault/memfault-firmware-sdk/pull/120
zephyr_compile_definitions(MEMFAULT_PROJECT_KEY_LEN=32)
