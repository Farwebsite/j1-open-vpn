#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# J1 Open VPN - instalador para Linux (Heimdall).
# Uso: sudo sh instalar-linux.sh   (en la carpeta con j1-open-vpn-boot.img,
# j1-open-vpn-rootfs.tar.gz y SHA256SUMS)
set -e
cd "$(dirname "$0")"
step() { printf '\n== %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*"; exit 1; }

echo "J1 Open VPN - instalación en Samsung Galaxy J1 SM-J100H"
echo "Se escribirán las particiones KERNEL y HIDDEN. Android dejará de arrancar (tus datos no se borran)."

step "1/5 Comprobando los archivos descargados"
[ -f SHA256SUMS ] || die "Falta SHA256SUMS"
grep -E ' \*?j1-open-vpn-(boot\.img|rootfs\.tar\.gz)$' SHA256SUMS | sha256sum -c - || die "Archivos dañados o incompletos: descárgalos otra vez"

step "2/5 Heimdall"
command -v heimdall >/dev/null || die "Instala Heimdall 1.4.2 o posterior (Debian/Ubuntu: sudo apt install heimdall-flash)"
heimdall version
[ "$(id -u)" = 0 ] || die "Ejecútalo con sudo (Heimdall necesita acceso al USB)"

step "3/5 Teléfono en modo Download"
echo "  1. Apaga el J1 (batería al menos al 50 %)."
echo "  2. Mantén Volumen abajo + Home + Encendido hasta que salga un aviso."
echo "  3. Pulsa Volumen arriba y conéctalo al PC."
while :; do
  printf '  Pulsa Enter cuando esté en modo Download y conectado: '; read -r _
  heimdall detect >/dev/null 2>&1 && { echo "  Teléfono detectado"; break; }
  echo "  No se detecta. Revisa el cable (de datos, no solo de carga) y el modo Download."
done

step "4/5 Confirmación"
echo "  KERNEL <- j1-open-vpn-boot.img"
echo "  HIDDEN <- j1-open-vpn-rootfs.tar.gz"
echo "  No desconectes el cable mientras se escribe."
printf '  Escribe SI para continuar: '; read -r ok
[ "$ok" = SI ] || { echo "Cancelado: no se ha escrito nada."; exit 0; }

step "5/5 Flasheando (alrededor de 1 minuto)"
heimdall flash --KERNEL j1-open-vpn-boot.img --HIDDEN j1-open-vpn-rootfs.tar.gz || die "Heimdall falló. Repite desde el modo Download (docs/recuperacion.md)"

echo
echo "Listo. El J1 se reinicia y se instala solo (pantalla en negro unos 30 segundos)."
echo "Después muestra 'AP: DIRECT-J1-VPN-XXXX · Clave: ...': apunta la clave."
echo "Siguiente paso: docs/instalacion.md, apartado 6."
