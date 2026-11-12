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
- **Red de configuración:** la red propia del J1 (`DIRECT-J1-VPN-XXXX`). Se puede apagar y cambiar su clave (que es también la del panel web mientras el panel no tenga contraseña propia). *QR para conectarse* muestra un código para entrar desde otro móvil.
- **WireGuard:** puerto, dominio, UPnP, clientes (crear, ver última conexión y tráfico, **QR**, **pausar**, quitar). Un cliente en pausa no puede conectarse pero conserva su perfil: al reanudarlo funciona sin importarlo de nuevo.
- **Cloudflare DNS:** DNS dinámico (ver abajo).
- **Cable USB:** estado del adaptador de red, 5 V automáticos, IP del cable.
- **Recursos:** CPU total y por proceso, RAM, disco y tráfico.
- **Batería:** carga, si está cargando, temperatura, voltaje y salud. Sin cargador muestra el consumo real (mA y W, medido por el chip de la batería) y el tiempo restante, calculado con la corriente media de los últimos 10 minutos y la capacidad de fábrica (1850 mAh); cargando, la corriente de carga y cuánto falta. También en el panel web, sección *Batería*. **Limitar la carga** (50–95 %, por defecto 80 %): al llegar al límite se pausa la carga y el J1 funciona con la batería aunque el cable siga puesto; vuelve a cargar 5 puntos por debajo. Tenerla siempre al 100 % con el cargador puesto la desgasta.
- **Pantalla:** brillo (deslizador), pantalla de bloqueo y tiempo de apagado. En los últimos segundos se atenúa; un toque la recupera.
- **Pantalla de bloqueo** (activada de serie; también se cambia en el panel web, sección *Pantalla de bloqueo*): cuando la pantalla se apaga, un toque o un botón solo muestran la hora y la batería, y hay que deslizar el círculo hasta el final para usarla. Así una mano apoyada encima no pulsa nada. Sin desbloquear vuelve a apagarse a los 10 s. Mantener el botón de encendido abre el menú de apagado igualmente (salvo con código).
- **Código de desbloqueo** (opcional, en *Pantalla*, con la pantalla de bloqueo activada): de 4 a 8 cifras, escrito dos veces. Tras deslizar sale un teclado numérico. Con código el J1 arranca bloqueado y el botón de encendido no se salta el bloqueo. Intentos: los 4 primeros fallos seguidos solo avisan; del 5.º al 9.º hay que esperar 30 s, 1, 2, 4 y 8 min; al **10.º fallo seguido la pantalla se bloquea por completo** (no acepta ningún código, ni el correcto) hasta desbloquearla desde el panel web (*Pantalla de bloqueo* → *Desbloquear la pantalla*). El contador se guarda en disco: reiniciar no lo pone a cero. El J1 solo guarda un hash (PBKDF2 con sal): protege frente a quien toca la pantalla, no frente a quien extrae la memoria del teléfono (con 4-8 cifras se puede adivinar fuera del J1), así que mejor 6 cifras o más. **Si lo olvidas:** panel web → *Pantalla de bloqueo* → *Quitar el código de desbloqueo* (necesitas la clave del panel o tu clave SSH). Desactivar la pantalla de bloqueo también lo borra. En la pantalla, **quitar el código o desactivar el bloqueo pide el código actual** (los fallos cuentan igual que al desbloquear); desde el panel web se puede quitar sin él, por si se olvida.
- **Avisos:** avisos al móvil (ver abajo).
- **Registros:** sistema, red, VPN y kernel.
- **Velocidad** y **Zona horaria:** cada una con su propio acceso en el inicio (ver abajo).
- **Sistema:** encendido, carga, RAM, **Actualizar** (ver abajo), reiniciar y apagar.

Con la pantalla apagada se borra la memoria de vídeo: un código QR no se queda guardado.

## Panel web

Desde un dispositivo conectado a la red de configuración: **http://192.168.78.1**. Por USB desde el PC: **http://192.168.77.1** (el J1 da la IP al PC solo). Usuario `admin`. Contraseña: la clave de la red de configuración, salvo que le pongas una **propia** (pantalla *Panel web* → *Cambiar contraseña del panel*, o en el propio panel, sección *Contraseña del panel*, que pide la actual). La propia se guarda como hash (PBKDF2 con sal). Si la olvidas, cámbiala desde la pantalla del J1 o pulsa *Volver a usar la clave de la red*.

Permite lo mismo que la pantalla y además **descargar el archivo `.conf`** de cada cliente para ordenadores. Desde el panel se pueden cambiar **todas las claves**: la del propio panel, la de la red de configuración, el código de la pantalla de bloqueo, la de la Wi-Fi de casa y el token de Cloudflare. Las tres primeras piden la contraseña actual del panel. Al cambiar la clave de la red de configuración se desconectan los equipos conectados a ella (y, si el panel no tiene contraseña propia, el navegador pedirá la nueva).

En la pantalla, **Panel web** (baldosa de la segunda página del inicio):

- **Panel web** activado/desactivado. Desactivado, el puerto 80 queda cerrado; la pantalla sigue funcionando igual.
- **Acceso desde la red local** (desactivado de serie): el panel responde también en la IP del J1 en tu red de casa (Wi-Fi o cable), sea fija o por DHCP; la pantalla muestra la dirección (`http://IP-del-J1`). En la red local va sin cifrar (HTTP): úsalo solo en casa. Solo entran equipos de la misma subred que el J1.
- **Acceso desde la VPN** (desactivado de serie): desde un dispositivo conectado a WireGuard, en cualquier sitio, en **http://10.66.0.1**. El túnel ya va cifrado. Desactivado, un cliente de la VPN no llega al panel por ninguna dirección.
- **Cifrado HTTPS** (desactivado de serie): el panel va cifrado también en la red de casa, en `https://`. El certificado lo crea el propio J1, así que el navegador avisa la primera vez: acéptalo si la huella SHA-256 coincide con la de la pantalla o la del panel (sección *HTTPS*). Con HTTPS activado, `http://` solo redirige a `https://`.
- **IP de la Wi-Fi / IP del cable:** accesos directos para poner esa IP por DHCP o fija.

El panel **no** debe publicarse en Internet: no redirijas el TCP 80 en el router.

**Conexión USB con el PC:** el J1 aparece como una tarjeta de red USB (RNDIS) y le da al PC la IP `192.168.77.2` automáticamente. Windows 10/11 la reconoce sola. Si en el Administrador de dispositivos sale como dispositivo desconocido (*J13G-Linux-USB*), actualiza su driver: *Buscar en mi equipo → Elegir de una lista → Adaptadores de red → Microsoft → Dispositivo compatible con NDIS remoto*. Si el PC no recibe IP, ponle a mano `192.168.77.2`, máscara `255.255.255.252`.

## Acceso SSH (opcional)

Para usuarios avanzados que quieran entrar en la consola de Linux. Viene **desactivado** (sin claves) y solo funciona con clave, nunca con contraseña. Por USB funciona siempre; desde la red de casa y desde la VPN, solo si lo activas. Desde Internet, nunca.

Panel web → sección **Acceso SSH**:

- **Generar una clave y descargarla:** el J1 crea un par de claves, autoriza la pública y te descarga la privada (`j1-open-vpn-ssh-key`). Guárdala bien: no se puede volver a descargar.
- **O pega tu clave pública** (`id_ed25519.pub`) si ya tienes una.
- **SSH activado**, **también desde la red local** (Wi-Fi o cable de casa) y **también desde la VPN**: también en la pantalla del J1, en *Sistema → Acceso SSH*, que muestra las direcciones para entrar. Desactivado no acepta conexiones nuevas por ningún lado, tampoco por USB (la sesión abierta sigue); se vuelve a activar desde la pantalla. Si el J1 está lejos, la red local es la forma de volver a entrar desde otro equipo de esa red cuando la VPN falla. No abras el puerto 22 en el router.
- **Desactivar SSH** borra todas las claves autorizadas.

Para entrar (PowerShell en Windows 10/11, o Linux/macOS):

```sh
ssh -i j1-open-vpn-ssh-key root@192.168.77.1   # USB
ssh -i j1-open-vpn-ssh-key root@<IP del J1>    # red local, la que muestra el panel
ssh -i j1-open-vpn-ssh-key root@10.66.0.1      # VPN
```

En Linux/macOS, antes: `chmod 600 j1-open-vpn-ssh-key`. En Windows, si `ssh` se queja de los permisos del archivo, guárdalo dentro de tu carpeta de usuario (`C:\Users\<tú>\.ssh\`).

Las claves se guardan con la configuración (`/etc/j1/authorized_keys`), así que sobreviven a una reinstalación del sistema.

## Vigilantes y reinicio

Sistema → **Vigilantes y reinicio** en la pantalla, o la sección *Vigilantes* del panel web. Pensado para un J1 que se queda lejos, sin nadie que lo reinicie:

- **Vigilar WireGuard** (activado): cada minuto comprueba que la interfaz está levantada y responde con su puerto y sus clientes. Si no, la vuelve a configurar y, si sigue mal, la crea de nuevo. Avisa al móvil si tienes los avisos de la VPN activados.
- **Vigilar Internet** (activado): tras 5 a 60 minutos sin Internet (10 por defecto) reinicia la red (Wi-Fi y cable). **Si no vuelve en otro tanto, reinicia el J1.** Nunca en la primera media hora tras arrancar ni más de una vez cada 6 horas, para que un corte de la conexión de casa no lo tenga reiniciándose sin parar. Al volver Internet avisa de cuánto tiempo estuvo caído.
- **Reinicio programado** (desactivado): cada día o cada domingo a la hora que elijas. Un minuto sin VPN.

El aviso de *J1 encendido* dice si el reinicio lo hizo un vigilante o el reinicio programado.

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

**Velocidad → Empezar** (acceso en el inicio). Mide ping, bajada y subida contra `speed.cloudflare.com` por el enlace activo (cable o Wi-Fi). Tarda unos 25 s y gasta 100–200 MB. Para la VPN cuenta sobre todo la **subida**: es lo que el J1 puede enviar a tus dispositivos cuando estás fuera.

Por Wi-Fi la VPN rinde menos de lo que marca la prueba: cada dato entra y sale por el mismo Wi-Fi.

## Avisos al móvil

El J1 puede avisarte en el móvil (pantalla *Avisos* o panel web, sección *Avisos al móvil*) cuando:

- se va o vuelve la corriente (se desconecta el cargador) y cuando se enciende;
- la batería está baja (20 %) o caliente (45 °C);
- la VPN da un error o vuelve a funcionar;
- cambia la IP pública de casa (con el DNS de Cloudflare activado);
- se conecta un cliente de la VPN.

Usa [ntfy](https://ntfy.sh): instala su app (o usa el navegador) y suscríbete a la dirección que muestra el J1, también como QR en la pantalla. El tema es una cadena secreta generada en el J1: quien la conozca puede leer los avisos, por eso los textos **no llevan IPs, claves ni contraseñas**. *Cambiar el tema secreto* (o *Tema nuevo al azar* en la pantalla) deja de enviar al anterior. También se puede **escribir el tema**: empieza por `j1-` y, sin token de acceso, debe tener al menos 16 caracteres más para que no se pueda adivinar. Por defecto usa el servidor público `ntfy.sh`; en el panel se puede poner uno propio (`https://`) con **token de acceso**, para que solo el J1 pueda publicar y nadie pueda mandarte avisos falsos: ver [Servidor de avisos propio](ntfy-propio.md). Vienen desactivados: actívalos y pulsa *Enviar aviso de prueba*.

## Copia de seguridad

Panel web → *Copia de seguridad*. **Descargar copia** guarda en un archivo `.j1bak` la configuración: clientes de la VPN, Wi-Fi, Cloudflare, avisos, contraseñas, certificado HTTPS y claves SSH. Va cifrado (AES-256-GCM, clave derivada con scrypt) con la contraseña que elijas: sin ella no se puede abrir, apúntala. No incluye lo propio de cada teléfono (MAC Wi-Fi, semillas aleatorias).

**Restaurar y reiniciar** sustituye la configuración por la de la copia y reinicia el J1. Sirve para reinstalar o pasar a otro J1 sin volver a configurar los clientes: sus perfiles siguen valiendo.

## Actualizar

Pantalla *Sistema* → *Actualizar*, o panel web → *Actualizar*. *Buscar actualizaciones* mira la última versión publicada en GitHub. *Instalar* descarga el sistema, comprueba su suma SHA-256 con `SHA256SUMS`, lo descomprime junto al actual y lo cambia en el siguiente arranque (el J1 se reinicia solo; un minuto sin VPN). La configuración y las tablas de la cámara se conservan, y el sistema anterior queda guardado como `<carpeta>.old`.

Solo se actualiza el sistema: la imagen de arranque (kernel) no se toca. Si la versión nueva trae otro kernel, el J1 lo dice; para tenerlo hay que reinstalar la imagen de arranque (ver [Instalación](instalacion.md)).

## Zona horaria

Viene la de España peninsular. Para cambiarla:

- En la pantalla: acceso **Zona horaria** del inicio y toca la tuya.
- En el panel web: sección **Zona horaria** → elige y *Guardar zona horaria*.

Zonas disponibles: España y Europa central, Canarias y Portugal, Reino Unido e Irlanda, Europa del este, México, Colombia/Perú/Ecuador, Venezuela/Bolivia, Chile, Argentina/Uruguay, EE. UU. este y pacífico, y UTC. El horario de verano es automático.

El cambio se aplica al momento: el reloj de la pantalla, la web y los registros pasan a la hora nueva sin reiniciar. Solo el registro del kernel sigue con la zona anterior hasta el siguiente arranque.

Para una zona que no está en la lista, con [acceso SSH](#acceso-ssh-opcional) escribe su cadena TZ POSIX en `/etc/j1/tz` (por ejemplo `<+0545>-5:45` para Nepal) y reinicia.

## Dónde se guarda todo

En la memoria interna (`/data/j1-open-vpn/`):

| Carpeta | Contenido |
|---|---|
| `rootfs/` | El sistema. Se puede reemplazar sin perder la configuración. |
| `config/` | Configuración y claves (WireGuard, Wi-Fi, Cloudflare). Privada. |
| `dropbear/` | Claves del servidor SSH. |

Para reinstalar el sistema conservando la configuración: flashea la versión nueva en `KERNEL` y `HIDDEN` y borra `rootfs/` (por SSH), o sigue las notas de la versión.
