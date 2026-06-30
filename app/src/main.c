/*
 * SPDX-License-Identifier: TBD  (license decision tracked by NPE-1777)
 *
 * quickstart-bluetooth — application entry point.
 *
 * PLACEHOLDER (NPE-1770 scaffolding). The real application — LBS button/LED
 * base, MDS access-control callback, heartbeat-on-connect, and the demo crash
 * button — is implemented in NPE-1771 per PLAN.md §4.2.
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(app, LOG_LEVEL_INF);

int main(void)
{
	LOG_INF("quickstart-bluetooth skeleton booted");
	return 0;
}
