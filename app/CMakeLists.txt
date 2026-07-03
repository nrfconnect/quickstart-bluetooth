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

# Workaround for a memfault-firmware-sdk 1.42.0 build bug in the NCS build:
# ports/zephyr/common/memfault_platform_project_key.c sizes its key buffer with
# MEMFAULT_PROJECT_KEY_LEN under CONFIG_MEMFAULT_PROJECT_KEY_SETTINGS, but only
# includes the header that defines it (memfault/http/http_client.h) under
# CONFIG_MEMFAULT_HTTP_CLIENT_CONFIG_BUILTIN, which NCS disables. Define the macro
# (canonical value 32, matching http_client.h) globally so that TU compiles.
# Remove once the SDK includes the header for the settings-key path too.
if(CONFIG_MEMFAULT_PROJECT_KEY_SETTINGS AND NOT CONFIG_MEMFAULT_HTTP_CLIENT_CONFIG_BUILTIN)
  zephyr_compile_definitions(MEMFAULT_PROJECT_KEY_LEN=32)
endif()
