# Instalación

Tiempo: unos 30 minutos. Lee la guía entera antes de empezar.

> **Aviso.** Vas a sustituir el sistema del teléfono. Si algo sale mal (por ejemplo, se corta el cable mientras flasheas), el teléfono puede no arrancar hasta que le flashees el firmware original. Tus fotos y datos de Android **no se borran**, pero Android deja de arrancar. Si hay algo importante en el teléfono, cópialo antes al PC.

## 0. Lo que necesitas

**Hardware**

- Un **Samsung Galaxy J1 SM-J100H** con su batería y un **cable USB de datos** (algunos cables solo cargan: si el PC no reconoce el teléfono, prueba otro).
- Un PC con **Windows 10/11** (o Linux).
- Acceso a la configuración de tu **router**, por si hay que abrir el puerto a mano.
- Opcional: adaptador **USB‑Ethernet** (probado RTL8153) y adaptador **OTG micro‑USB**.

**Programas en el PC (Windows)**

| Programa | Para qué | Dónde |
|---|---|---|
| Drivers USB de Samsung | Que Windows reconozca el teléfono | [developer.samsung.com/android-usb-driver](https://developer.samsung.com/android-usb-driver) |
| Zadig | Driver WinUSB para el modo Download (lo necesita Heimdall) | [zadig.akeo.ie](https://zadig.akeo.ie) |
| Heimdall 1.4.2 | Escribir las particiones. **El instalador lo descarga solo** | [github.com/amo13/Heimdall](https://github.com/amo13/Heimdall/releases/tag/v1.4.2) |

En **Linux** basta con `sudo apt install heimdall-flash` (o el paquete `heimdall` de tu distribución, versión 1.4.2 o posterior). No hacen falta drivers.

**En los dispositivos que se conectarán a la VPN**

- La app **WireGuard**: [Android](https://play.google.com/store/apps/details?id=com.wireguard.android), [iPhone/iPad](https://apps.apple.com/app/wireguard/id1441195209), [Windows, macOS y Linux](https://www.wireguard.com/install/).

## 1. Comprueba el modelo

Ajustes → Acerca del teléfono → Modelo: tiene que ser **SM-J100H** (también aparece en la etiqueta debajo de la batería). Otros modelos de J1 no son compatibles: tienen otro procesador.

## 2. Descarga

En [Releases](https://github.com/Farwebsite/j1-open-vpn/releases) descarga **`j1-open-vpn-<versión>.zip`** y descomprímelo (por ejemplo en `C:\j1-open-vpn`). Contiene:

| Archivo | Para qué |
|---|---|
| `instalar-windows.bat` | Instalador para Windows (doble clic) |
| `instalar-linux.sh` | Instalador para Linux |
| `j1-open-vpn-boot.img` | Kernel y arranque → partición `KERNEL` |
| `j1-open-vpn-rootfs.tar.gz` | El sistema → partición `HIDDEN` |
| `SHA256SUMS` | Sumas para comprobar que nada está dañado (los instaladores lo comprueban solos) |
| `LEEME-instalacion.md` | Esta guía |

En Releases también está `j1-open-vpn-odin.tar`, solo para quien use Odin.

Recomendado: descarga también el **firmware original de Samsung** para el SM-J100H de tu región (por ejemplo desde SamFW o SamMobile). Es lo que necesitarás si algún día quieres volver a Android ([recuperacion.md](recuperacion.md)).

## 3. Prepara el teléfono

1. **Carga la batería** al menos al 50 %.
2. Si tiene una cuenta de Google o de Samsung, **elimínala** (Ajustes → Cuentas). Algunos J1 con protección antirrobo rechazan el flasheo.
3. Apágalo.

## 4. Flashea

Elige **una** de las tres opciones. La A y la B (Heimdall) son las probadas.

**Modo Download** (lo usan todas): con el teléfono apagado, mantén **Volumen abajo + Home + Encendido** hasta que salga un aviso en pantalla y pulsa **Volumen arriba** para continuar. Para salir sin hacer nada, mantén Encendido unos segundos.

### Opción A: instalador automático (recomendada)

**Windows:**

1. Instala los **drivers USB de Samsung** (paso 0) y reinicia el PC si te lo pide.
2. Doble clic en **`instalar-windows.bat`**. El instalador:
   - comprueba que los archivos no están dañados,
   - descarga Heimdall 1.4.2 y verifica que es la versión correcta,
   - te pide poner el teléfono en modo Download y conectarlo,
   - pide confirmación (escribe `SI`) y flashea.
3. **La primera vez** dirá *No se detecta*: falta el driver WinUSB. Con el teléfono conectado en modo Download, abre **Zadig** → menú *Options* → *List All Devices*. Elige el dispositivo cuyo **USB ID** sea `04E8 685D` (suele llamarse *SAMSUNG Mobile USB CDC Composite Device* o *Gadget Serial*). A la derecha elige **WinUSB** y pulsa *Replace Driver*. Vuelve al instalador y pulsa Enter.
   (Esto solo cambia el driver del modo Download. Si algún día usas Odin, reinstala los drivers de Samsung.)

Si Windows no deja ejecutar el instalador (*SmartScreen*), pulsa *Más información → Ejecutar de todas formas*.

**Linux:**

```sh
cd j1-open-vpn
sudo sh instalar-linux.sh
```

### Opción B: Heimdall a mano

1. Descarga Heimdall 1.4.2 de [github.com/amo13/Heimdall/releases/tag/v1.4.2](https://github.com/amo13/Heimdall/releases/tag/v1.4.2): `heimdall.windows.zip` **y** `dlls.zip`. Descomprime los dos en la **misma** carpeta, por ejemplo `C:\heimdall`.
   (El Heimdall 1.4.0 oficial falla con este teléfono: *Failed to send data*.)
2. Driver WinUSB con Zadig, como en el paso 3 de la opción A.
3. Copia `j1-open-vpn-boot.img` y `j1-open-vpn-rootfs.tar.gz` a `C:\heimdall`. Con el teléfono en modo Download y conectado, abre PowerShell en esa carpeta:

   ```powershell
   .\heimdall.exe detect
   .\heimdall.exe flash --KERNEL j1-open-vpn-boot.img --HIDDEN j1-open-vpn-rootfs.tar.gz
   ```

   `detect` tiene que responder `Device detected`. El flasheo tarda un minuto. El aviso `Empty bulk transfer after receiving packet failed` es normal. Al terminar pone `Ending session...` y el teléfono se reinicia solo.

### Opción C: Odin (no probada)

1. Instala los drivers USB de Samsung y abre Odin3 (v3.10 o posterior).
2. Pon el teléfono en modo Download y conéctalo: Odin muestra `Added!!`.
3. En **AP** (o **PDA** en versiones antiguas) elige `j1-open-vpn-odin.tar`. No marques *Re-Partition*.
4. Pulsa *Start* y espera `PASS!`.

## 5. Primer arranque

1. El teléfono se reinicia y la pantalla se queda **en negro unos 30 segundos** (como mucho un par de minutos): está instalando el sistema en la memoria interna. **No lo apagues.**
2. Aparece la pantalla de control **J1 · Servidor VPN**. La línea **AP: DIRECT-J1-VPN-XXXX · Clave: …** muestra el nombre de la red de configuración y su **clave**. Apúntala: también es la contraseña del panel web (usuario `admin`).

Si a los 5 minutos la pantalla sigue en negro, mira [recuperacion.md](recuperacion.md#la-pantalla-se-queda-en-negro).

La pantalla se apaga sola a los 60 s. Para encenderla, toca la pantalla o pulsa un botón. El botón de encendido la enciende o apaga; **mantenido** abre el menú Apagar/Reiniciar.

## 6. Conéctalo a tu Wi-Fi

En la pantalla del J1:

1. **Wi-Fi** → **Buscar redes** → toca tu red.
2. Toca *Contraseña Wi-Fi*, escríbela con el teclado de la pantalla (`123` números y símbolos, `ver` muestra lo escrito), pulsa **OK** y luego **Conectar**.
3. Vuelve al inicio: la línea *Wi-Fi* pasa a verde con la IP del J1 (por ejemplo `Wi-Fi: 192.168.1.40`).

Recomendado: en **Wi-Fi → IP de la Wi-Fi** fija la IP, para que no cambie y la redirección del router siga funcionando.

También puedes hacerlo desde otro móvil u ordenador: conéctate a la red `DIRECT-J1-VPN-XXXX` con su clave y abre **http://192.168.78.1** (usuario `admin`, la misma clave).

## 7. Abre el puerto en el router

Los clientes llegan desde Internet al puerto **UDP 51820** del J1.

- **Automático:** en **WireGuard**, el interruptor *Abrir puerto (UPnP)* viene activado. Si debajo pone *Router: Abierto UDP 51820*, ya está. Si dice que el router no responde, tu router no tiene UPnP o lo tiene desactivado.
- **Manual:** en la configuración del router, crea una redirección de puertos (*port forwarding* / *NAT*): **UDP 51820** → IP del J1 (la del paso 6), puerto 51820.

Si tu operador usa **CG‑NAT** (no tienes IP pública), no se puede entrar desde fuera. Pregúntale a tu operador por una IP pública.

## 8. Crea un cliente y conéctate

1. Instala la app **WireGuard** en tu móvil (Android/iOS) o en el ordenador.
2. En la pantalla del J1: **WireGuard** → *Nombre del nuevo cliente* (por ejemplo `movil`) → **Crear cliente**.
3. Toca el cliente → **Mostrar QR**.
4. En la app WireGuard: **+** → *Escanear código QR* → apunta a la pantalla del J1.
5. Desactiva el Wi-Fi del móvil (para probar desde fuera, con datos) y activa el túnel. En la pantalla del cliente, *Última conexión* pasa a "ahora".

Para ordenadores: desde el panel web (http://192.168.78.1 o por USB http://192.168.77.1) cada cliente tiene **Descargar .conf**, que se importa en WireGuard.

## 9. Opcional

- **Nombre de dominio** en vez de IP (útil si tu IP pública cambia): [uso.md → Cloudflare](uso.md#dns-dinámico-con-cloudflare).
- **Cable de red** por USB: [uso.md → Cable](uso.md#cable-de-red-usb).
- **Zona horaria:** viene la de España peninsular; para otra, ver [uso.md → Zona horaria](uso.md#zona-horaria).

Listo. El J1 puede quedarse siempre enchufado al cargador: la batería hace de SAI si se va la luz.
