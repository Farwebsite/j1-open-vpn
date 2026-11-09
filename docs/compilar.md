# Compilar desde el código fuente

Todo se compila en un PC con **Linux x86_64**: Ubuntu 22.04/24.04, Debian 12 o **WSL2** en Windows. Hacen falta unos 10 GB libres y entre 20 y 60 minutos (la primera vez descarga el kernel y el compilador).

## Dependencias

```sh
sudo apt install git build-essential bc bison flex python3 perl cpio wget qemu-user-static binfmt-support
```

`qemu-user-static` permite ejecutar programas ARM en el PC: el sistema Alpine se prepara "dentro" de sí mismo (paquetes, compilación de la pantalla).

## Compilar

```sh
git clone https://github.com/Farwebsite/j1-open-vpn.git
cd j1-open-vpn
sudo ./build.sh
```

Resultado en `out/`:

| Archivo | |
|---|---|
| `j1-open-vpn-boot.img` | Partición `KERNEL` |
| `j1-open-vpn-rootfs.tar.gz` | Partición `HIDDEN` |
| `j1-open-vpn-odin.tar` | Las dos, para Odin |
| `SHA256SUMS` | Sumas de comprobación |
| `zImage`, `kernel.config` | Kernel y su configuración |

Variables útiles:

| Variable | |
|---|---|
| `WORK=/ruta` | Carpeta de trabajo (por defecto `~/j1-build`). Mejor en un disco Linux (ext4), no en `/mnt/c`. |
| `SKIP_KERNEL=1` | Reutiliza `out/zImage` (el kernel es lo que más tarda). |
| `SSH_PUBKEY=~/.ssh/id_ed25519.pub` | Incluye tu clave pública para entrar por SSH (ver abajo). |

Las versiones están fijadas para que el resultado sea siempre el mismo:

| Componente | Versión |
|---|---|
| Kernel j13g (LineageOS cm-12.1, de jnkcode) | `8e519128` |
| wireguard-linux-compat | `v1.0.20220627` |
| Compilador AOSP arm-eabi-4.8 | `android-8.1.0_r1` (`26e93f6a`) |
| Alpine Linux armv7 | 3.24.4 |

## Partes

### Kernel (`kernel/`)

`build-kernel.sh` descarga el kernel 3.10 del J1, aplica `patch/apply.py` y añade WireGuard:

- **USB host (OTG):** el kernel original solo funcionaba como dispositivo USB. `patch/j1_usb_host.c` cambia el controlador `dwc_otg` a modo host cuando el MUIC (SM5504) detecta un cable OTG, y da 5 V con el elevador del cargador (SM5701) si el adaptador no trae alimentación propia. Vigila el estado del cargador y corta los 5 V ante cualquier fallo.
- Drivers de **Ethernet USB**: CDC Ethernet, RTL8152/8153, ASIX.
- **WireGuard** dentro del kernel (ChaCha20/Poly1305 en ensamblador ARM/NEON).
- Arranque normal aunque se encienda al enchufar el cargador (sin modo carga de Android).

### Arranque (`boot/`)

- `initramfs/init`: monta la partición `userdata`, instala el sistema desde `HIDDEN` si no existe y arranca Alpine desde `/data/j1-open-vpn/rootfs`.
- `dt.img`: árbol de dispositivo del J1, extraído de la imagen de arranque original de Samsung (rev. 3). SHA-256 `d8b8c5a2a583e3e9a612494d19c79600b16855a0ba2ffa66de1734533f35685b`.
- `mkbootimg.py`: empaqueta kernel + initramfs + árbol con la cabecera que espera el cargador de arranque del J1.

### Sistema (`rootfs/`)

- `packages.txt`: paquetes de Alpine.
- `overlay/`: programas del J1:
  - `sbin/j1-init`: arranque de servicios; en el primer arranque genera la clave y el nombre de la red de configuración y copia el firmware Wi-Fi y la MAC de Android.
  - `usr/local/sbin/j1-network`: gestor de red (Wi-Fi cliente, cable, IP compartida con conmutación, red de configuración, modo cargador del SM5701).
  - `usr/local/sbin/j1-udhcpc`: direcciones y rutas (cable con prioridad sobre el Wi-Fi).
  - `usr/local/lib/j1/web.py`: lógica de WireGuard, Wi-Fi, UPnP, Cloudflare, panel web y las vistas de la pantalla.
  - `usr/local/sbin/j1-klog`: registro persistente del kernel (sin el ruido de los drivers).
- `display/j1-display.c`: la pantalla táctil (C, estático, sin dependencias). Dibuja directamente en el framebuffer y pide cada vista a `web.py` por un socket local.

## Pruebas

```sh
python3 -m unittest discover -s tests
```

Funcionan en Linux (o WSL); no necesitan el teléfono.

En el teléfono, `tools/j1-toques.py` simula toques y teclas sobre una instancia de prueba de la pantalla y `tools/j1-captura.py` guarda capturas.

## Acceso SSH

Se activa desde el panel web ([uso.md → Acceso SSH por USB](uso.md#acceso-ssh-por-usb-opcional)). Para que tu imagen ya lo traiga activado con tu clave, compila con:

```sh
sudo SSH_PUBKEY=$HOME/.ssh/id_ed25519.pub ./build.sh
```

La clave se copia a `/etc/j1/authorized_keys` en el primer arranque. **No publiques** una imagen compilada así: tú tendrías acceso SSH a todos los teléfonos donde se instale.

El SSH solo escucha por USB (`192.168.77.1`, el PC recibe `192.168.77.2` automáticamente):

```sh
ssh root@192.168.77.1
```

Con el adaptador de red conectado al USB no hay conexión con el PC, así que tampoco hay SSH.
