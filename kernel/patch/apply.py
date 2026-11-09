#!/usr/bin/env python3
"""Applies the J1 USB host changes to the j13g kernel tree. Fails loudly if any
anchor text is missing, so a mismatch never produces a half-patched tree."""
import pathlib, shutil, sys

src = pathlib.Path(sys.argv[1])
here = pathlib.Path(__file__).parent


def patch(rel, old, new, count=1):
    p = src / rel
    t = p.read_text(errors='surrogateescape')
    if new in t:
        print('ya aplicado:', rel)
        return
    n = t.count(old)
    if n != count:
        sys.exit(f'ERROR {rel}: el texto ancla aparece {n} veces (esperado {count})')
    p.write_text(t.replace(old, new), errors='surrogateescape')
    print('ok:', rel)


# 1) Kconfig option
patch('drivers/usb/gadget/Kconfig',
      'config SPRD_USB_DEVICE_ONLY\n',
      'config J1_USB_HOST\n'
      '\tbool "Galaxy J1: USB host role switch driven by the SM5504 MUIC"\n'
      '\tdepends on USB_GADGET_SPRD_DWC && !SPRD_USB_DEVICE_ONLY && MFD_SM5504 && MFD_SM5701\n'
      '\thelp\n'
      '\t  Switches dwc_otg to host mode on OTG cables reported by the MUIC and\n'
      '\t  drives VBUS with the SM5701 boost unless a powered hub supplies it.\n'
      '\n'
      'config SPRD_USB_DEVICE_ONLY\n')

# 2) Build the new file
shutil.copy(here / 'j1_usb_host.c', src / 'drivers/usb/gadget/dwc_otg/j1_usb_host.c')
patch('drivers/usb/gadget/dwc_otg/Makefile',
      'dwc_otg-objs\t+= dwc_otg_hcd_ddma.o  \n',
      'dwc_otg-objs\t+= dwc_otg_hcd_ddma.o  \n'
      'dwc_otg-$(CONFIG_J1_USB_HOST)\t+= j1_usb_host.o\n')

# 3) ID state comes from the role switch (no ID gpio on this board)
patch('drivers/usb/gadget/dwc_otg/usb_hw.c',
      'int usb_get_id_state(void)\n{\n',
      '#ifdef CONFIG_J1_USB_HOST\n'
      'extern int j1_usb_id_state(void);\n'
      '#endif\n'
      'int usb_get_id_state(void)\n{\n'
      '#ifdef CONFIG_J1_USB_HOST\n'
      '\treturn j1_usb_id_state();\n'
      '#endif\n')

# 4) hcd_init: no ID irq, no hcd at boot; host started on demand via dwc_otg_start()
hcd = 'drivers/usb/gadget/dwc_otg/dwc_otg_hcd_linux.c'
patch(hcd,
      '#ifdef CONFIG_USB_EXTERNAL_DETECT\nint dwc_otg_start(void *data, bool enable)',
      '#if defined(CONFIG_USB_EXTERNAL_DETECT) || defined(CONFIG_J1_USB_HOST)\n'
      'int dwc_otg_start(void *data, bool enable)')
patch(hcd,
      '#ifdef CONFIG_USB_EXTERNAL_DETECT\n\thcd->irq = irq;\n'
      '\tregister_otg_func(dwc_otg_start, NULL, otg_dev);\n#else\n',
      '#if defined(CONFIG_J1_USB_HOST)\n\thcd->irq = irq;\n'
      '\tj1_usb_register(otg_dev);\n'
      '#elif defined(CONFIG_USB_EXTERNAL_DETECT)\n\thcd->irq = irq;\n'
      '\tregister_otg_func(dwc_otg_start, NULL, otg_dev);\n#else\n')
patch(hcd,
      '#ifndef CONFIG_USB_EXTERNAL_DETECT\n\t/*\n\t * setup usb OTG cable detect interrupt',
      '#if !defined(CONFIG_USB_EXTERNAL_DETECT) && !defined(CONFIG_J1_USB_HOST)\n'
      '\t/*\n\t * setup usb OTG cable detect interrupt')
patch(hcd,
      'int hcd_init(\n',
      '#ifdef CONFIG_J1_USB_HOST\n'
      'extern void j1_usb_register(void *otg_dev);\n'
      '#endif\n'
      'int hcd_init(\n')
patch(hcd,
      '#ifndef CONFIG_USB_EXTERNAL_DETECT\n\tusb_remove_hcd(hcd);\n#endif\n',
      '#if !defined(CONFIG_USB_EXTERNAL_DETECT) && !defined(CONFIG_J1_USB_HOST)\n'
      '\tusb_remove_hcd(hcd);\n#endif\n')
# hcd_init must finish (set priv data) before the role switch can run: the
# register call only queues delayed work, so ordering is safe.

# 5) MUIC reports cable changes to the role switch
patch('drivers/mfd/sm5504.c',
      'static void sm5504_cable_change_handler(struct sm5504_chip *chip,\n',
      '#ifdef CONFIG_J1_USB_HOST\n'
      'extern void j1_usb_cable_event(int otg, int vbus);\n'
      '#endif\n'
      'static void sm5504_cable_change_handler(struct sm5504_chip *chip,\n')
patch('drivers/mfd/sm5504.c',
      '\tif(!chip->curr_status.ovp_status){\n'
      '\t\tif( chip->curr_status.cable_type ==MUIC_SM5504_CABLE_TYPE_L_USB)\n',
      '#ifdef CONFIG_J1_USB_HOST\n'
      '\tj1_usb_cable_event(chip->curr_status.cable_type == MUIC_SM5504_CABLE_TYPE_OTG ||\n'
      '\t\t\t   chip->curr_status.cable_type == MUIC_SM5504_CABLE_TYPE_OTG_WITH_VBUS,\n'
      '\t\t\t   chip->curr_status.vbus_status);\n'
      '#endif\n'
      '\tif(!chip->curr_status.ovp_status){\n'
      '\t\tif( chip->curr_status.cable_type ==MUIC_SM5504_CABLE_TYPE_L_USB)\n')

# 6) Powered OTG hub: charge from it (stock J13G treats it as "unknown")
patch('drivers/battery/sec_dt_init.c',
      '\tdefined(CONFIG_MACH_GRANDNEOVE3G) || defined(CONFIG_MACH_J13G)\n'
      '\t\tcurrent_cable_type = POWER_SUPPLY_TYPE_UNKNOWN;\n',
      '\tdefined(CONFIG_MACH_GRANDNEOVE3G) || defined(CONFIG_MACH_J13G)\n'
      '#ifdef CONFIG_J1_USB_HOST\n'
      '\t\t/* VBUS from a powered hub, not from our own boost */\n'
      '\t\tif (!j1_usb_boost_active()) {\n'
      '\t\t\tcurrent_cable_type = POWER_SUPPLY_TYPE_MAINS;\n'
      '\t\t\tbreak;\n'
      '\t\t}\n'
      '#endif\n'
      '\t\tcurrent_cable_type = POWER_SUPPLY_TYPE_UNKNOWN;\n')
# 7) While the J1 boosts VBUS, an OTG cable must stay "OTG" for the charger
#    code (stock J13G maps it to BATTERY, which restores charger mode).
patch('drivers/battery/sec_dt_init.c',
      '\tcase MUIC_SM5504_CABLE_TYPE_OTG:\n#endif\n'
      '\t\tcurrent_cable_type = POWER_SUPPLY_TYPE_BATTERY;\n\t\tbreak;\n',
      '\tcase MUIC_SM5504_CABLE_TYPE_OTG:\n#endif\n'
      '\t\tcurrent_cable_type = POWER_SUPPLY_TYPE_BATTERY;\n'
      '#ifdef CONFIG_J1_USB_HOST\n'
      '\t\tif (cable_type == MUIC_SM5504_CABLE_TYPE_OTG && j1_usb_boost_active())\n'
      '\t\t\tcurrent_cable_type = POWER_SUPPLY_TYPE_OTG;\n'
      '#endif\n'
      '\t\tbreak;\n')
patch('drivers/battery/sec_dt_init.c',
      '#ifdef CONFIG_MFD_SM5504\nvoid sec_charger_cb(u8 cable_type)\n',
      '#ifdef CONFIG_J1_USB_HOST\n'
      'extern int j1_usb_boost_active(void);\n'
      '#endif\n'
      '#ifdef CONFIG_MFD_SM5504\nvoid sec_charger_cb(u8 cable_type)\n')
# 8) A charger power-on (androidboot.mode=charger) must boot the full system:
#    in "LPM" the touch driver is not registered and the battery uses the
#    power-off charging limits. This server never shows the Android charger UI.
patch('drivers/battery/sec_dt_init.c',
      '        if (strncmp(str, "charger", 7) == 0)\n'
      '                lpcharge = 1;\n',
      '        /* J1 Linux: a charger boot runs the full system (no LPM) */\n'
      '        if (0 && strncmp(str, "charger", 7) == 0)\n'
      '                lpcharge = 1;\n')
print('PARCHE COMPLETO')
