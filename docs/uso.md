# Uso

## Pantalla

| Acción | Cómo |
|---|---|
| Encender la pantalla | Tocarla o pulsar cualquier botón |
| Desbloquear | Arrastrar el círculo de *Desliza para desbloquear* hasta el final (con la pantalla de bloqueo activada) |
| Apagarla | Botón de encendido (pulsación corta) o sola al pasar el tiempo elegido |
| Apagar o reiniciar el J1 | Mantener el botón de encendido 1,5 s → *Apagar* / *Reiniciar* |
| Cambiar de página en el inicio | Deslizar las baldosas a izquierda o derecha (los puntos indican la página); *Atrás* vuelve a la primera |
| Desplazar | Arrastrar, o Volumen +/− |
| Volver | Flecha arriba a la izquierda, o tecla táctil *Atrás* |
| Inicio | Botón Home |

Vistas del inicio:

- **Wi-Fi:** encender/apagar el Wi-Fi cliente, buscar redes, red oculta, IP fija, QR de la red guardada.
- **Red de configuración:** la red propia del J1 (`DIRECT-J1-VPN-XXXX`). Se puede apagar y cambiar su clave (que es también la clave del panel web). *QR para conectarse* muestra un código para entrar desde otro móvil.
- **WireGuard:** puerto, dominio, UPnP, clientes (crear, ver última conexión y tráfico, **QR**, quitar).
- **Cloudflare DNS:** DNS dinámico (ver abajo).
- **Cable USB:** estado del adaptador de red, 5 V automáticos, IP del cable.
- **Recursos:** CPU total y por proceso, RAM, disco, tráfico y temperatura.
- **Pantalla:** brillo (deslizador), pantalla de bloqueo y tiempo de apagado. En los últimos segundos se atenúa; un toque la recupera.
- **Pantalla de bloqueo** (activada de serie; también se cambia en el panel web, sección *Pantalla de bloqueo*): cuando la pantalla se apaga, un toque o un botón solo muestran la hora y la batería, y hay que deslizar el círculo hasta el final para usarla. Así una mano apoyada encima no pulsa nada. Sin desbloquear vuelve a apagarse a los 10 s. Mantener el botón de encendido abre el menú de apagado igualmente.
- **Registros:** sistema, red, VPN y kernel.
- **Sistema:** encendido, carga, RAM, **zona horaria**, **prueba de velocidad**, reiniciar y apagar.

Con la pantalla apagada se borra la memoria de vídeo: un código QR no se queda guardado.

## Panel web

Desde un dispositivo conectado a la red de configuración: **http://192.168.78.1**. Por USB desde el PC: **http://192.168.77.1** (el J1 da la IP al PC solo). Usuario `admin`, contraseña = clave de la red de configuración.

Permite lo mismo que la pantalla y además **descargar el archivo `.conf`** de cada cliente para ordenadores.

En la pantalla, **Panel web** (baldosa de la segunda página del inicio):

- **Panel web** activado/desactivado. Desactivado, el puerto 80 queda cerrado; la pantalla sigue funcionando igual.
- **Acceso desde la red local** (desactivado de serie): el panel responde también en la IP del J1 en tu red de casa (Wi-Fi o cable), sea fija o por DHCP; la pantalla muestra la dirección (`http://IP-del-J1`). En la red local va sin cifrar (HTTP): úsalo solo en casa. Por la VPN el panel nunca responde.
- **IP de la Wi-Fi / IP del cable:** accesos directos para poner esa IP por DHCP o fija.

El panel **no** debe publicarse en Internet: no redirijas el TCP 80 en el router.

**Conexión USB con el PC:** el J1 aparece como una tarjeta de red USB (RNDIS) y le da al PC la IP `192.168.77.2` automáticamente. Windows 10/11 la reconoce sola. Si en el Administrador de dispositivos sale como dispositivo desconocido (*J13G-Linux-USB*), actualiza su driver: *Buscar en mi equipo → Elegir de una lista → Adaptadores de red → Microsoft → Dispositivo compatible con NDIS remoto*. Si el PC no recibe IP, ponle a mano `192.168.77.2`, máscara `255.255.255.252`.

## Acceso SSH por USB (opcional)

Para usuarios avanzados que quieran entrar en la consola de Linux. Viene **desactivado** y solo funciona con el J1 conectado al PC por USB: nunca desde la Wi-Fi ni desde Internet, y solo con clave (sin contraseña).

Panel web por USB (http://192.168.77.1) → sección **Acceso SSH por USB**:

- **Generar una clave y descargarla:** el J1 crea un par de claves, autoriza la pública y te descarga la privada (`j1-open-vpn-ssh-key`). Guárdala bien: no se puede volver a descargar.
- **O pega tu clave pública** (`id_ed25519.pub`) si ya tienes una.
- **Desactivar SSH** borra todas las claves autorizadas.

Para entrar (PowerShell en Windows 10/11, o Linux/macOS):

```sh
ssh -i j1-open-vpn-ssh-key root@192.168.77.1
```

En Linux/macOS, antes: `chmod 600 j1-open-vpn-ssh-key`. En Windows, si `ssh` se queja de los permisos del archivo, guárdalo dentro de tu carpeta de usuario (`C:\Users\<tú>\.ssh\`).

Las claves se guardan con la configuración (`/etc/j1/authorized_keys`), así que sobreviven a una reinstalación del sistema.

## Clientes VPN

- Cada cliente recibe una IP `10.66.0.X` y su propia clave precompartida.
- *Última conexión* y el tráfico se ven tocando el cliente en **WireGuard**.
- Si cambias el **puerto** o el **dominio**, vuelve a importar los perfiles en los clientes.
- Para quitar el acceso a un dispositivo perdido: toca el cliente → *Quitar*.
- El túnel lleva todo el tráfico del cliente (IPv4 sale por tu casa; IPv6 se manda al túnel para que no se escape por fuera).

## DNS dinámico con Cloudflare

Si tu IP pública cambia, los clientes dejan de encontrar el J1. Con un dominio en Cloudflare, el J1 mantiene un registro apuntando a tu IP:

1. En Cloudflare, crea un **token API** con permiso *Zone → DNS → Edit* limitado a tu zona.
2. Copia el **ID de zona** (página de resumen del dominio).
3. En el panel web, sección *Cloudflare · DNS dinámico*: nombre completo (por ejemplo `vpn.tudominio.com`), ID de zona y token. Marca *Actualizar automáticamente* y guarda.

El J1 crea o actualiza solo ese registro A, en modo *Solo DNS* (sin proxy), cada 5 minutos. El token no se vuelve a mostrar. Deja el campo *Dominio o IP* de WireGuard vacío para que los perfiles usen ese nombre.

## Cable de red USB

Con un adaptador **USB‑Ethernet** (probado RTL8153; también CDC Ethernet, RTL8152, ASIX AX88179/AX8817x) y un adaptador **OTG** micro‑USB:

1. Desenchufa el cable del PC o el cargador y **espera 5 segundos**.
2. Conecta el adaptador con el cable de red. El J1 le da 5 V solo; a los pocos segundos la pantalla muestra *Cable: …* con su IP.

Mientras el adaptador está conectado, el J1 **no se carga** (el puerto USB lo está alimentando): funciona con la batería. Para uso continuo por cable hace falta un cable OTG en Y con alimentación o un hub USB alimentado.

### Misma IP por cable y Wi-Fi (un solo puerto en el router)

En **Wi-Fi → IP de la Wi-Fi** fija una IP y pulsa *Usar esta IP también en el cable*. Desde entonces:

- Con el cable conectado y con Internet, el cable usa la IP y el Wi-Fi se queda **de reserva** (desconectado).
- Si el cable se desconecta o se queda sin Internet (3 pings fallidos), pasa al Wi-Fi.
- Lo vuelve a intentar por cable cada 10 minutos. Si el Wi-Fi tampoco tiene Internet, se queda en el cable.

Así el router solo necesita una redirección de puerto.

**No cambies el MTU del adaptador.** Con este driver USB, bajarlo cuelga el kernel.

## Prueba de velocidad

**Sistema → Prueba de velocidad → Empezar.** Mide ping, bajada y subida contra `speed.cloudflare.com` por el enlace activo (cable o Wi-Fi). Tarda unos 25 s y gasta 100–200 MB. Para la VPN cuenta sobre todo la **subida**: es lo que el J1 puede enviar a tus dispositivos cuando estás fuera.

Por Wi-Fi la VPN rinde menos de lo que marca la prueba: cada dato entra y sale por el mismo Wi-Fi.

## Zona horaria

Viene la de España peninsular. Para cambiarla:

- En la pantalla: **Sistema → Zona horaria** y toca la tuya.
- En el panel web: sección **Zona horaria** → elige y *Guardar zona horaria*.

Zonas disponibles: España y Europa central, Canarias y Portugal, Reino Unido e Irlanda, Europa del este, México, Colombia/Perú/Ecuador, Venezuela/Bolivia, Chile, Argentina/Uruguay, EE. UU. este y pacífico, y UTC. El horario de verano es automático.

El cambio se aplica al momento: el reloj de la pantalla, la web y los registros pasan a la hora nueva sin reiniciar. Solo el registro del kernel sigue con la zona anterior hasta el siguiente arranque.

Para una zona que no está en la lista, con [acceso SSH](#acceso-ssh-por-usb-opcional) escribe su cadena TZ POSIX en `/etc/j1/tz` (por ejemplo `<+0545>-5:45` para Nepal) y reinicia.

## Dónde se guarda todo

En la memoria interna (`/data/j1-open-vpn/`):

| Carpeta | Contenido |
|---|---|
| `rootfs/` | El sistema. Se puede reemplazar sin perder la configuración. |
| `config/` | Configuración y claves (WireGuard, Wi-Fi, Cloudflare). Privada. |
| `dropbear/` | Claves del servidor SSH. |

Para reinstalar el sistema conservando la configuración: flashea la versión nueva en `KERNEL` y `HIDDEN` y borra `rootfs/` (por SSH), o sigue las notas de la versión.
