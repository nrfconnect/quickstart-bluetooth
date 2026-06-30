# SPDX-License-Identifier: TBD  (license decision tracked by NPE-1777)
#
# quickstart-bluetooth application (peripheral_lbs + Memfault over MDS).
# Plain Zephyr application — no sysbuild, no MCUboot (PLAN.md §1, §2.2).

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(quickstart_bluetooth)

target_sources(app PRIVATE src/main.c)
