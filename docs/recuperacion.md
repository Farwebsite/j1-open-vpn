# Volver a Android y solución de problemas

## Volver a Android

J1 Open VPN solo cambia dos particiones: `KERNEL` (arranque) y `HIDDEN` (contenido precargado de Samsung). Android, tus datos y el resto de particiones no se tocan.

1. Descarga el **firmware original** del SM-J100H para tu región (SamFW, SamMobile…). Es un `.zip` con archivos `.tar.md5` (AP, BL, CP, CSC).
2. Instala los drivers USB de Samsung y abre **Odin3**.
3. Pon el J1 en modo Download (**Volumen abajo + Home + Encendido**, luego **Volumen arriba**) y conéctalo.
4. Carga cada archivo en su casilla (AP, BL, CP, CSC) y pulsa *Start*.

Si habías usado Zadig para Heimdall, Odin no verá el teléfono hasta que reinstales los drivers de Samsung.

La carpeta `/data/j1-open-vpn` se queda en la memoria interna ocupando unos 60 MB hasta que hagas un restablecimiento de fábrica.

## La pantalla se queda en negro

En el primer arranque es normal que esté en negro **unos 30 segundos**. Si pasan más de 5 minutos:

1. Mantén el botón de encendido 10 segundos para apagarlo (o quita la batería).
2. Vuelve a flashear **los dos** archivos (paso 4 de la [instalación](instalacion.md)). Lo más habitual es que `HIDDEN` no se haya escrito: sin él, el J1 no tiene sistema que instalar y se queda esperando.
3. Si se queda en el logo de Samsung en vez de en negro, el problema está en `KERNEL`: flashea de nuevo `j1-open-vpn-boot.img`.

## No aparece la red `DIRECT-J1-VPN-XXXX`

- En la pantalla, **Red de configuración** debe estar *Activa*. Si pone *Apagada*, actívala con el interruptor.
- Si el Wi-Fi no funciona en absoluto, mira **Registros → Sistema**: debe aparecer *Primer arranque: firmware Wi-Fi copiado de Android*. Si no aparece, el J1 no pudo copiar el firmware Wi-Fi de Android. Pasa si la partición `system` se borró o se reemplazó por otra ROM. Solución: flashea el firmware original de Samsung y repite la instalación.

## No conecta desde fuera de casa

En orden:

1. ¿La línea *WG* del inicio está en verde? Si no, mira **Registros → VPN**.
2. **WireGuard → Router:** ¿pone *Abierto UDP 51820*? Si no, crea la redirección a mano en el router (UDP, a la IP del J1).
3. ¿Tienes IP pública? Compara la IP WAN del router con la que ves en [ifconfig.me](https://ifconfig.me). Si no coinciden, estás detrás de **CG‑NAT** y hay que pedir una IP pública al operador.
4. Prueba desde **datos móviles**, no desde el Wi-Fi de casa: muchos routers no permiten conectarse a su propia IP pública desde dentro.
5. Si cambiaste el puerto o el dominio, vuelve a importar el perfil en el cliente.

## El adaptador de red USB no se detecta

1. Desenchufa todo del USB, espera **5 segundos** y conecta el adaptador. Un cambio muy rápido de PC/cargador a adaptador puede pasar desapercibido.
2. Si la luz del adaptador se enciende pero el J1 no lo ve, reinícialo (mantén el botón de encendido → *Reiniciar*).
3. Comprueba en **Cable USB** que *Alimentación automática 5 V* está activada.

## Olvidé la clave de la red de configuración

Se ve en la pantalla de inicio (línea *AP: … · Clave: …*) y en **Red de configuración**.

## Reinstalar desde cero

Para empezar de cero (se pierden los clientes VPN y la configuración), hace falta borrar `/data/j1-open-vpn` (por SSH o con un restablecimiento de fábrica desde el firmware original) y volver a flashear.
