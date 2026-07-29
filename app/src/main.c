/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/*
 * quickstart-bluetooth application.
 *
 * The peripheral_lbs button/LED base with Memfault observability over the
 * Memfault Diagnostic Service (MDS). The device serves Memfault chunks to a
 * secured gateway connection; the gateway performs the HTTPS upload. The device
 * never does on-device HTTP/TLS.
 *
 * Controls (nRF54L15 DK):
 *   Button 0  LBS button characteristic (standard LBS — central sees the press)
 *   Button 1  DEMO-ONLY crash trigger (forces a fault -> Memfault coredump)
 *   LED 0     run status (1 Hz heartbeat blink)
 *   LED 1     BLE connection status
 *   LED 2     LBS LED (controlled by the central/gateway — standard LBS)
 */

#include <zephyr/kernel.h>
#include <zephyr/types.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/uuid.h>

#include <bluetooth/services/lbs.h>
#include <bluetooth/services/mds.h>

#include <zephyr/settings/settings.h>

#include <dk_buttons_and_leds.h>

#include <memfault/metrics/metrics.h>
#include <memfault/ports/zephyr/http.h>

#define DEVICE_NAME     CONFIG_BT_DEVICE_NAME
#define DEVICE_NAME_LEN (sizeof(DEVICE_NAME) - 1)

#define RUN_STATUS_LED         DK_LED1
#define CON_STATUS_LED         DK_LED2
#define LBS_LED                DK_LED3
#define RUN_LED_BLINK_INTERVAL 1000

#define LBS_BUTTON   DK_BTN1_MSK
#define CRASH_BUTTON DK_BTN2_MSK /* DEMO-ONLY, see button_handler() */

/* App-identity marker: an empty vendor service whose UUID the nRF Toolbox app
 * discovers over GATT to recognize this firmware and tailor its UX.
 */
#define BT_UUID_QSBT_ID_VAL BT_UUID_128_ENCODE(0xb2007aaa, 0xc203, 0x43a5, 0x8b6f, 0xa7f3d001a1e0)
#define BT_UUID_QSBT_ID     BT_UUID_DECLARE_128(BT_UUID_QSBT_ID_VAL)

/* Named to sort alphabetically before lbs_svc/mds_svc: Zephyr's
 * BT_GATT_SERVICE_DEFINE places services into a linker section sorted by name
 * (SORT_BY_NAME), so this controls GATT discovery order, not declaration
 * order. Mobile app requests: custom, lbs, MDS.
 */
BT_GATT_SERVICE_DEFINE(custom_id_svc, BT_GATT_PRIMARY_SERVICE(BT_UUID_QSBT_ID));

static bool app_button_state;
static struct bt_conn *mds_conn;
static struct k_work adv_work;

/* Advertise the app-identity UUID (not the LBS UUID) so the mobile app can
 * recognize this as a quickstart device from the scan list, before
 * connecting. MDS is discovered over GATT after connecting; it does not need
 * to be advertised.
 */
static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, DEVICE_NAME, DEVICE_NAME_LEN),
};

static const struct bt_data sd[] = {
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_QSBT_ID_VAL),
};

static void adv_work_handler(struct k_work *work)
{
	int err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_2, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));

	if (err) {
		printk("Advertising failed to start (err %d)\n", err);
		return;
	}

	printk("Advertising successfully started\n");
}

static void advertising_start(void)
{
	k_work_submit(&adv_work);
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		printk("Connection failed, err 0x%02x %s\n", err, bt_hci_err_to_str(err));
		return;
	}

	printk("Connected\n");
	dk_set_led_on(CON_STATUS_LED);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	printk("Disconnected, reason 0x%02x %s\n", reason, bt_hci_err_to_str(reason));

	dk_set_led_off(CON_STATUS_LED);

	if (conn == mds_conn) {
		mds_conn = NULL;
	}
}

static void security_changed(struct bt_conn *conn, bt_security_t level, enum bt_security_err err)
{
	char addr[BT_ADDR_LE_STR_LEN];

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));

	if (err) {
		printk("Security failed: %s level %u err %d %s\n", addr, level, err,
		       bt_security_err_to_str(err));
		return;
	}

	printk("Security changed: %s level %u\n", addr, level);

	/* Once the gateway link is secured, mark it as the MDS-authorized
	 * connection and capture a heartbeat immediately so the device (with its
	 * software/hardware version and serial) appears in Memfault within
	 * seconds instead of waiting for the periodic heartbeat timer.
	 */
	if (level >= BT_SECURITY_L2 && !mds_conn) {
		mds_conn = conn;
		memfault_metrics_heartbeat_debug_trigger();
	}
}

static void recycled_cb(void)
{
	advertising_start();
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
	.security_changed = security_changed,
	.recycled = recycled_cb,
};

static void pairing_complete(struct bt_conn *conn, bool bonded)
{
	char addr[BT_ADDR_LE_STR_LEN];

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
	printk("Pairing completed: %s, bonded: %d\n", addr, bonded);
}

static void pairing_failed(struct bt_conn *conn, enum bt_security_err reason)
{
	char addr[BT_ADDR_LE_STR_LEN];

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
	printk("Pairing failed conn: %s, reason %d %s\n", addr, reason,
	       bt_security_err_to_str(reason));
}

static void auth_cancel(struct bt_conn *conn)
{
	char addr[BT_ADDR_LE_STR_LEN];

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
	printk("Pairing cancelled: %s\n", addr);
}

/* Just-works pairing (no passkey entry) — the gateway initiates security. */
static struct bt_conn_auth_cb conn_auth_callbacks = {
	.cancel = auth_cancel,
};

static struct bt_conn_auth_info_cb conn_auth_info_callbacks = {
	.pairing_complete = pairing_complete,
	.pairing_failed = pairing_failed,
};

/* Gate MDS access to the secured gateway connection only. */
static bool mds_access_enable(struct bt_conn *conn)
{
	return (mds_conn && conn == mds_conn);
}

static const struct bt_mds_cb mds_cb = {
	.access_enable = mds_access_enable,
};

/* Standard LBS callbacks: central writes the LED, reads the button state. */
static void app_led_cb(bool led_state)
{
	dk_set_led(LBS_LED, led_state);
}

static bool app_button_cb(void)
{
	return app_button_state;
}

static struct bt_lbs_cb lbs_callbacks = {
	.led_cb = app_led_cb,
	.button_cb = app_button_cb,
};

static void button_handler(uint32_t button_state, uint32_t has_changed)
{
	if (has_changed & LBS_BUTTON) {
		uint32_t pressed = button_state & LBS_BUTTON;

		bt_lbs_send_button_state(pressed);
		app_button_state = pressed ? true : false;
	}

	/* DEMO-ONLY: force a fault so the guide can show a coredump in Memfault.
	 * Remove this in a real product — a button should never crash firmware.
	 */
	if ((button_state & has_changed) & CRASH_BUTTON) {
		printk("Crash button pressed — forcing a fault for the Memfault demo\n");
		k_oops();
	}
}

int main(void)
{
	uint32_t blink_status = 0;
	int err;

	printk("Starting quickstart-bluetooth (LBS + Memfault/MDS)\n");

	err = dk_leds_init();
	if (err) {
		printk("LEDs init failed (err %d)\n", err);
		return 0;
	}

	err = dk_buttons_init(button_handler);
	if (err) {
		printk("Buttons init failed (err %d)\n", err);
		return 0;
	}

	/* Register before bt_enable() so MDS access gating is in place from the
	 * first connection (see bt_mds_cb_register() docs).
	 */
	err = bt_mds_cb_register(&mds_cb);
	if (err) {
		printk("MDS callback registration failed (err %d)\n", err);
		return 0;
	}

	err = bt_conn_auth_cb_register(&conn_auth_callbacks);
	if (err) {
		printk("Failed to register authorization callbacks (err %d)\n", err);
		return 0;
	}

	err = bt_conn_auth_info_cb_register(&conn_auth_info_callbacks);
	if (err) {
		printk("Failed to register authorization info callbacks (err %d)\n", err);
		return 0;
	}

	err = bt_enable(NULL);
	if (err) {
		printk("Bluetooth init failed (err %d)\n", err);
		return 0;
	}

	printk("Bluetooth initialized\n");

#if defined(CONFIG_SETTINGS)
	/* Loads the stored Memfault project key (memfault/project_key) and BT
	 * bonds. The runtime key is applied here at boot, not live.
	 */
	settings_load();

#if defined(CONFIG_MEMFAULT_PROJECT_KEY_SETTINGS)
	/* No key provisioned yet: fall back to the build-time default (if any),
	 * baked in via CONFIG_QSBT_DEFAULT_PROJECT_KEY. A key written later via
	 * the settings shell overrides this on the next boot.
	 */
	if (sizeof(CONFIG_QSBT_DEFAULT_PROJECT_KEY) > 1
	    && settings_get_val_len("memfault/project_key") <= 0) {
		err = memfault_zephyr_port_set_project_key(CONFIG_QSBT_DEFAULT_PROJECT_KEY,
							   sizeof(CONFIG_QSBT_DEFAULT_PROJECT_KEY)
								   - 1);
		if (err) {
			printk("Failed to set default Memfault project key (err %d)\n", err);
		}
	}
#endif /* CONFIG_MEMFAULT_PROJECT_KEY_SETTINGS */
#endif /* CONFIG_SETTINGS */

	err = bt_lbs_init(&lbs_callbacks);
	if (err) {
		printk("Failed to init LBS (err %d)\n", err);
		return 0;
	}

	k_work_init(&adv_work, adv_work_handler);
	advertising_start();

	for (;;) {
		dk_set_led(RUN_STATUS_LED, (++blink_status) % 2);
		k_sleep(K_MSEC(RUN_LED_BLINK_INTERVAL));
	}
}
