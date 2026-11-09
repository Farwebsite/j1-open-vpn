# Notas técnicas del hardware

Lo aprendido durante el desarrollo, para quien quiera mejorar el proyecto o portarlo.

## Galaxy J1 SM-J100H (j13g)

| | |
|---|---|
| SoC | Spreadtrum SC7727S (SC8830), 2× Cortex-A7 1,2 GHz, NEON |
| RAM | 512 MB (≈460 MB libres con el sistema en marcha) |
| Almacenamiento | eMMC 4 GB; `userdata` (p25) ≈2,2 GB |
| Wi-Fi | Broadcom BCM43430 por SDIO (driver `dhd`), 2,4 GHz, 1×1, 72 Mbit/s de enlace |
| Pantalla | 480×800, framebuffer `sprdfb`, retroiluminación `ktd2801` (0–255) |
| Táctil | `bt432_ts` (Zinitix) |
| USB | `dwc_otg` + MUIC SM5504 (detección de cable) + cargador SM5701 (elevador 5 V) |

Particiones relevantes (nombre en el PIT → archivo para Odin):

| Partición | Archivo | Uso en J1 Open VPN |
|---|---|---|
| `KERNEL` (p20, 16 MB) | `boot.img` | Kernel + initramfs |
| `RECOVERY` (p21) | `recovery.img` | Sin tocar |
| `system` (p23) | `system.img` | Solo lectura: firmware Wi-Fi |
| `efs` (p17) | `efs.img` | Solo lectura: MAC Wi-Fi |
| `HIDDEN` (p24, 100 MB) | `hidden.img` | Sistema comprimido para la instalación |
| `userdata` (p25) | `userdata.img` | `/data/j1-open-vpn` |

`SBOOT`/`SBOOT2` contienen el cargador de arranque **firmado**, incluido el logo de inicio de Samsung: no se pueden modificar sin riesgo de inutilizar el teléfono. La partición `PARAM` también tiene un `logo.jpg`, pero el cargador no lo usa para la pantalla de inicio.

## Arranque

El cargador de Samsung carga `KERNEL` (cabecera Android v0 con el árbol de dispositivo añadido, `dt_size` en la cabecera). El `init` del initramfs monta `userdata`, hace *bind mount* de `rootfs`, `config` (→ `/etc/j1`) y `dropbear` (→ `/etc/dropbear`) y ejecuta `switch_root` a `/sbin/j1-init` (busybox sh como PID 1; no hay OpenRC).

## USB OTG y el cargador SM5701

- El MUIC SM5504 informa del tipo de cable (OTG = resistencia ID a masa). El parche cambia `dwc_otg` a host y pide 5 V al SM5701 (`OPERATIONMODE` = OTG) mediante el driver de batería.
- Si el SM5701 se queda en modo OTG sin que el kernel lo sepa (por ejemplo, tras un cuelgue con el adaptador alimentado), **sobrevive a los reinicios** porque se alimenta de la batería. El puerto queda con 5 V permanentes: no se carga y el MUIC no puede detectar un adaptador nuevo. `j1-network` lo devuelve a modo cargador al arrancar y al terminar el modo host (`echo 4 > /sys/bus/i2c/devices/3-0049/SM5701_core`). Diagnóstico: `tools/sm5701-estado.py` (solo lee registros de estado; los de interrupción se borran al leerlos y no se tocan).
- Parámetros en `/sys/module/dwc_otg/parameters/`: `j1_mode` (0 auto, 1 host, 2 dispositivo), `j1_boost` (0 nunca dar 5 V, 1 automático), y de solo lectura `j1_host_active`, `j1_boost_on`, `j1_boost_locked`.
- Un hub con alimentación que dé 5 V al puerto bloquea el elevador (no se pelean dos fuentes).

## Ethernet USB

- Probado: **RTL8153** (RAMPOW) con `cdc_ether`, ≈57/43 Mbit/s. El límite está en el USB 2.0 del J1 y en la CPU.
- **No cambies el MTU**: con `cdc_ether` + `dwc_otg`, bajarlo de 1500 deja los búferes de recepción por debajo de lo que envía el adaptador y cuelga el kernel al instante.
- Avisos `kevent 11 may have been dropped` en el registro: el adaptador notifica muchos cambios de enlace. Son inofensivos.

## Wi-Fi

- El firmware (`bcmdhd_sta.bin`, `nvram_net.txt`) y la MAC (`/efs/wifi/.mac.info`) son de Samsung: se copian de las particiones del propio teléfono.
- El **ahorro de energía** del chip añade 20–80 ms de latencia; `j1-network` lo desactiva al conectar (`iw dev wlan0 set power_save off`; el driver lo reactiva en cada conexión).
- La red de configuración es un grupo **Wi-Fi Direct** persistente (`DIRECT-…`) en modo GO, gestionado por `wpa_supplicant`, con `dnsmasq` en 192.168.78.0/24.
- Con la VPN por Wi-Fi cada paquete cruza el aire dos veces (entra y sale): espera ~⅓ de la velocidad de la prueba.

## Energía y pantalla

- No hay suspensión (sin `autosleep`): la CPU queda en reposo profundo con `cpuidle`. Con la pantalla apagada `j1-display` solo espera en `poll()`.
- Al apagar la pantalla se borra el framebuffer (no queda un QR en la memoria de vídeo).
- Con el teléfono enchufado, encender con el cargador arranca el sistema completo: el parche anula el modo de carga de Android.

## Registro del kernel

`j1-klog` guarda `/proc/kmsg` en `/root/j1-logs/kmsg.log` (y el arranque anterior en `kmsg.prev.log`), sincronizando cada 2 s, porque este teléfono no conserva el registro tras un reinicio. Filtra el ruido de los drivers de Samsung (regulador, Wi-Fi, CPU, táctil), que de otro modo llenaría 2 MB en minutos.
