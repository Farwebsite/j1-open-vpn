/*
 * Galaxy J1 (SM-J100H / j13g): USB host role switch driven by the SM5504 MUIC.
 *
 * The board has no OTG ID gpio, so the vendor hcd_init() path (ID irq) can't
 * be used and the Samsung notify layer is incomplete. The MUIC reports OTG
 * cables and external VBUS to us; this file switches dwc_otg between device
 * and host and decides who drives VBUS:
 *   - OTG adapter alone          -> the J1 drives 5 V with the SM5701 boost
 *   - powered hub / OTG Y cable  -> the external supply drives VBUS
 *
 * Automatic boost (v3). A powered hub reported as OTG before its VBUS arrived
 * made the boost fight the hub and the J1 browned out, so:
 *   1. wait J1_SETTLE_MS after the cable shows up before boosting;
 *   2. boost only if neither the MUIC nor the SM5701 (STATUS1.VBUSOK) sees VBUS;
 *   3. while boosting, poll the SM5701 every J1_MONITOR_MS and cut on any
 *      j1_cut_mask status bit or if OTG mode is dropped;
 *   4. after a cut, external VBUS locks the boost until the cable is unplugged;
 *      otherwise retry, at most J1_MAX_TRIES per insertion;
 *   5. drive the boost through the battery driver (cable type OTG), so the
 *      charger code keeps OTG mode instead of silently restoring charging.
 *
 * Runtime controls (/sys/module/dwc_otg/parameters/):
 *   j1_mode      0 = auto (MUIC), 1 = force host, 2 = force device
 *   j1_boost     0 = never drive VBUS, 1 = automatic (default)
 *   j1_cut_mask  cut bits while boosting: 0-7 SM5701 STATUS1, 8-15 STATUS3
 *   j1_host_active, j1_boost_on, j1_boost_locked, j1_boost_tries: read-only
 *
 * SPDX-License-Identifier: GPL-2.0
 */
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/i2c.h>
#include <linux/power_supply.h>
#include <linux/mfd/sm5701_core.h>

extern int dwc_otg_start(void *data, bool enable);
extern int epmic_event_handler(int level);

enum { J1_AUTO, J1_HOST, J1_DEVICE };

/* The MUIC re-detects for ~2.5 s when VBUS changes (e.g. our own boost
 * turning on), reporting a bogus detach: keep detach debounce above that. */
#define J1_ATTACH_DELAY_MS	300
#define J1_DETACH_DELAY_MS	3000
#define J1_SETTLE_MS		2000	/* time for a hub/charger to bring VBUS */
#define J1_BOOST_START_MS	300	/* boost ramp before the first check */
#define J1_MONITOR_MS		100
#define J1_RECHECK_MS		500	/* after a cut, before reading VBUSOK */
#define J1_MAX_TRIES		3
#define J1_REPLUG_MS		5000	/* shorter gaps are MUIC flaps, not replugs */

/* SM5701 charger on i2c-3: STATUS/CNTL reads have no side effects
 * (unlike the INT registers, which are read-to-clear). */
#define J1_SM5701_BUS		3
#define J1_SM5701_ADDR		0x49
#define J1_SM5701_STATUS1	0x06
#define J1_SM5701_STATUS3	0x08
#define J1_SM5701_CNTL		0x09
#define J1_S1_VBUSOK		0x04
#define J1_S1_VBUSOVP		0x10
#define J1_S3_BOOSTPOK_NG	0x10

static int j1_mode = J1_AUTO;
static int j1_boost = 1;
static int j1_cut_mask = J1_S1_VBUSOVP | (J1_S3_BOOSTPOK_NG << 8);
static int j1_host_active;
static int j1_boost_on;
static int j1_boost_locked;
static int j1_boost_tries;

static void *j1_otg;
static int j1_cable_otg;
static int j1_cable_vbus;	/* external VBUS as seen by the MUIC */
static unsigned long j1_settle_from;	/* jiffies: start of the settle wait */
static unsigned long j1_otg_gone;	/* jiffies: last OTG detach */
static int j1_mon_first;
static int j1_last_status = -1;
static DEFINE_MUTEX(j1_lock);

static void j1_work_fn(struct work_struct *work);
static DECLARE_DELAYED_WORK(j1_work, j1_work_fn);
static void j1_cut_fn(struct work_struct *work);
static DECLARE_WORK(j1_cut_work, j1_cut_fn);
static void j1_mon_fn(struct work_struct *work);
static DECLARE_DELAYED_WORK(j1_mon_work, j1_mon_fn);

static int j1_sm5701_read(u8 reg)
{
	struct i2c_adapter *adap = i2c_get_adapter(J1_SM5701_BUS);
	union i2c_smbus_data data;
	int ret;

	if (!adap)
		return -ENODEV;
	ret = i2c_smbus_xfer(adap, J1_SM5701_ADDR, 0, I2C_SMBUS_READ, reg,
			     I2C_SMBUS_BYTE_DATA, &data);
	i2c_put_adapter(adap);
	return ret < 0 ? ret : data.byte;
}

/* Only meaningful while our boost is off. Unreadable counts as "maybe". */
static int j1_external_vbus(void)
{
	int s1;

	if (j1_cable_vbus)
		return 1;
	s1 = j1_sm5701_read(J1_SM5701_STATUS1);
	return s1 < 0 || (s1 & J1_S1_VBUSOK);
}

static void j1_battery_cable(int type)
{
	struct power_supply *psy = power_supply_get_by_name("battery");
	union power_supply_propval val = { .intval = type };

	if (psy && psy->set_property)
		psy->set_property(psy, POWER_SUPPLY_PROP_ONLINE, &val);
}

static void j1_boost_enable(void)
{
	/* set first: sec_charger_cb keeps cable type OTG while this is on */
	j1_boost_on = 1;
	j1_boost_tries++;
	j1_mon_first = 1;
	j1_last_status = -1;
	pr_info("j1_usb: VBUS boost on (try %d)\n", j1_boost_tries);
	j1_battery_cable(POWER_SUPPLY_TYPE_OTG);
	mod_delayed_work(system_wq, &j1_mon_work,
			 msecs_to_jiffies(J1_BOOST_START_MS));
}

static void j1_boost_disable(const char *why)
{
	if (!j1_boost_on)
		return;
	j1_boost_on = 0;
	cancel_delayed_work(&j1_mon_work);
	/* immediate; the battery driver then settles on charger mode too */
	SM5701_set_operationmode(SM5701_OPERATIONMODE_CHARGER_ON);
	j1_battery_cable(POWER_SUPPLY_TYPE_BATTERY);
	pr_info("j1_usb: VBUS boost off (%s)\n", why);
}

/* A cut while the cable is still there: re-evaluate once VBUS has settled. */
static void j1_boost_fault(const char *why)
{
	j1_boost_disable(why);
	j1_settle_from = jiffies;
	mod_delayed_work(system_wq, &j1_work, msecs_to_jiffies(J1_RECHECK_MS));
}

static void j1_boost_decide(void)
{
	unsigned long ready;

	if (!j1_host_active || !j1_cable_otg || !j1_boost) {
		j1_boost_disable("no unpowered OTG adapter");
		return;
	}
	if (j1_boost_on || j1_boost_locked)
		return;
	ready = j1_settle_from + msecs_to_jiffies(J1_SETTLE_MS);
	if (time_before(jiffies, ready)) {
		mod_delayed_work(system_wq, &j1_work, ready - jiffies);
		return;
	}
	if (j1_external_vbus()) {
		j1_boost_locked = 1;
		pr_info("j1_usb: external VBUS present, boost locked until replug\n");
	} else if (j1_boost_tries >= J1_MAX_TRIES) {
		j1_boost_locked = 1;
		pr_info("j1_usb: %d boost faults, boost locked until replug\n",
			j1_boost_tries);
	} else {
		j1_boost_enable();
	}
}

static void j1_work_fn(struct work_struct *work)
{
	int want_host;

	mutex_lock(&j1_lock);
	if (!j1_otg)
		goto out;

	want_host = j1_mode == J1_HOST ||
		    (j1_mode == J1_AUTO && j1_cable_otg);

	if (want_host && !j1_host_active) {
		/* set first: gadget VBUS handlers check usb_get_id_state() */
		j1_host_active = 1;
		pr_info("j1_usb: host mode on (otg=%d vbus=%d)\n",
			j1_cable_otg, j1_cable_vbus);
		dwc_otg_start(j1_otg, true);
	} else if (!want_host && j1_host_active) {
		j1_boost_disable("host mode off");
		pr_info("j1_usb: host mode off\n");
		dwc_otg_start(j1_otg, false);
		j1_host_active = 0;
		/* resume device mode if a PC is connected */
		epmic_event_handler(j1_cable_vbus);
	}
	j1_boost_decide();
out:
	mutex_unlock(&j1_lock);
}

/* No debounce: VBUS goes off as soon as the cable leaves or someone else
 * powers the port. Only the host role waits for the MUIC to settle. */
static void j1_cut_fn(struct work_struct *work)
{
	mutex_lock(&j1_lock);
	if (j1_boost_on && (!j1_cable_otg || j1_cable_vbus || !j1_boost)) {
		if (j1_cable_otg && j1_cable_vbus) {
			j1_boost_locked = 1;
			j1_boost_disable("MUIC sees external VBUS");
		} else {
			j1_boost_disable("cable removed or boost disabled");
		}
	}
	mutex_unlock(&j1_lock);
}

static void j1_mon_fn(struct work_struct *work)
{
	int s1, s3, cntl, status;

	mutex_lock(&j1_lock);
	if (!j1_boost_on)
		goto out;
	s1 = j1_sm5701_read(J1_SM5701_STATUS1);
	s3 = j1_sm5701_read(J1_SM5701_STATUS3);
	cntl = j1_sm5701_read(J1_SM5701_CNTL);
	if (s1 < 0 || s3 < 0 || cntl < 0) {
		j1_boost_fault("SM5701 unreadable");
		goto out;
	}
	status = s1 | s3 << 8 | cntl << 16;
	if (status != j1_last_status) {
		pr_info("j1_usb: boost S1=%02x S3=%02x CNTL=%02x\n", s1, s3, cntl);
		j1_last_status = status;
	}
	if ((cntl & 7) != SM5701_OPERATIONMODE_OTG_ON) {
		if (!j1_mon_first) {
			/* someone else changed the mode: don't fight it */
			j1_boost_fault("OTG mode dropped");
			goto out;
		}
		/* the battery driver did not start the boost: do it directly */
		pr_info("j1_usb: starting OTG mode directly\n");
		SM5701_set_bstout(SM5701_BSTOUT_5P0);
		SM5701_set_operationmode(SM5701_OPERATIONMODE_OTG_ON);
	}
	j1_mon_first = 0;
	if ((s1 | s3 << 8) & j1_cut_mask) {
		j1_boost_fault("SM5701 status");
		goto out;
	}
	mod_delayed_work(system_wq, &j1_mon_work, msecs_to_jiffies(J1_MONITOR_MS));
out:
	mutex_unlock(&j1_lock);
}

/* usb_hw.c: 0 = host (ID grounded), 1 = device */
int j1_usb_id_state(void)
{
	return !j1_host_active;
}
EXPORT_SYMBOL(j1_usb_id_state);

/* sec_dt_init.c: our boost, not a powered hub, is on the port */
int j1_usb_boost_active(void)
{
	return j1_boost_on;
}
EXPORT_SYMBOL(j1_usb_boost_active);

/* sm5504.c: called on every cable change (MUIC irq thread) */
void j1_usb_cable_event(int otg, int vbus)
{
	if (otg && !j1_cable_otg) {
		/* a real replug re-arms the boost; quick re-attaches are flaps */
		if (!j1_otg_gone || time_after(jiffies,
				j1_otg_gone + msecs_to_jiffies(J1_REPLUG_MS))) {
			j1_boost_tries = 0;
			j1_boost_locked = 0;
		}
		j1_settle_from = jiffies;
	} else if (!otg && j1_cable_otg) {
		j1_otg_gone = jiffies;
	}
	j1_cable_otg = otg;
	j1_cable_vbus = vbus;
	if (j1_boost_on && (!otg || vbus))
		schedule_work(&j1_cut_work);
	mod_delayed_work(system_wq, &j1_work, msecs_to_jiffies(
		otg ? J1_ATTACH_DELAY_MS : J1_DETACH_DELAY_MS));
}
EXPORT_SYMBOL(j1_usb_cable_event);

/* dwc_otg_hcd_linux.c: hcd_init() */
void j1_usb_register(void *otg_dev)
{
	j1_otg = otg_dev;
	j1_settle_from = jiffies;
	pr_info("j1_usb: registered, mode=%d boost=%d (v3)\n", j1_mode, j1_boost);
	mod_delayed_work(system_wq, &j1_work, msecs_to_jiffies(J1_ATTACH_DELAY_MS));
}

static int j1_param_set(const char *val, const struct kernel_param *kp)
{
	int ret;

	mutex_lock(&j1_lock);
	ret = param_set_int(val, kp);
	/* switching the boost on by hand re-arms it after a lock */
	if (!ret && kp->arg == &j1_boost && j1_boost) {
		j1_boost_locked = 0;
		j1_boost_tries = 0;
		j1_settle_from = jiffies;
	}
	mutex_unlock(&j1_lock);
	if (!ret) {
		schedule_work(&j1_cut_work);
		mod_delayed_work(system_wq, &j1_work, 0);
	}
	return ret;
}

static struct kernel_param_ops j1_param_ops = {
	.set = j1_param_set,
	.get = param_get_int,
};

module_param_cb(j1_mode, &j1_param_ops, &j1_mode, 0644);
MODULE_PARM_DESC(j1_mode, "0 auto (MUIC), 1 force host, 2 force device");
module_param_cb(j1_boost, &j1_param_ops, &j1_boost, 0644);
MODULE_PARM_DESC(j1_boost, "0 never drive VBUS, 1 automatic (default)");
module_param(j1_cut_mask, int, 0644);
MODULE_PARM_DESC(j1_cut_mask, "cut boost on SM5701 bits: 0-7 STATUS1, 8-15 STATUS3");
module_param(j1_host_active, int, 0444);
module_param(j1_boost_on, int, 0444);
module_param(j1_boost_locked, int, 0444);
module_param(j1_boost_tries, int, 0444);
