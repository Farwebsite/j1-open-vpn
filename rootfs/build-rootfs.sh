#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
# Builds the J1 Open VPN system: Alpine Linux armv7 + packages.txt + the
# J1 programs (overlay/, display/). Runs as root on Linux x86_64 with
# qemu-user-static (ARM programs run through binfmt).
# Result: $OUT/j1-open-vpn-rootfs.tar.gz and $OUT/alpine-minirootfs (for the boot image).
# Optional: SSH_PUBKEY=/path/key.pub enables SSH over USB with that key.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$HOME/j1-build}
OUT=${OUT:-$HERE/../out}
VERSION=${VERSION:-$(cat "$HERE/../VERSION")}
ALPINE=3.24.4
BRANCH=v3.24
MINI=alpine-minirootfs-$ALPINE-armv7.tar.gz
MIRROR=https://dl-cdn.alpinelinux.org/alpine

[ "$(id -u)" = 0 ] || { echo "Ejecuta como root (sudo)"; exit 1; }
[ -e /proc/sys/fs/binfmt_misc/qemu-arm ] || { echo "Falta qemu para ARM. En Ubuntu/Debian: sudo apt install qemu-user-static binfmt-support"; exit 1; }
mkdir -p "$WORK" "$OUT"
cd "$WORK"

echo "== Alpine $ALPINE armv7"
if [ ! -f "$MINI" ]; then
  wget -q "$MIRROR/$BRANCH/releases/armv7/$MINI" -O "$MINI.part"
  wget -q "$MIRROR/$BRANCH/releases/armv7/$MINI.sha256" -O "$MINI.sha256"
  [ "$(sha256sum <"$MINI.part" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$MINI.sha256")" ] || { echo "ERROR: suma SHA-256 de $MINI incorrecta"; exit 1; }
  mv "$MINI.part" "$MINI"
fi
R=$WORK/rootfs
cleanup() { for m in dev proc; do mountpoint -q "$R/$m" && umount -l "$R/$m"; done; return 0; }
trap cleanup EXIT
cleanup
rm -rf "$R" "$OUT/alpine-minirootfs"
mkdir -p "$R" "$OUT/alpine-minirootfs"
tar -xzf "$MINI" -C "$R"
tar -xzf "$MINI" -C "$OUT/alpine-minirootfs"
mount --bind /dev "$R/dev"
mount -t proc proc "$R/proc"
cp /etc/resolv.conf "$R/etc/resolv.conf"
printf '%s\n' "$MIRROR/$BRANCH/main" "$MIRROR/$BRANCH/community" >"$R/etc/apk/repositories"

echo "== Paquetes"
chroot "$R" /sbin/apk add --no-cache $(grep -v '^#' "$HERE/packages.txt")

echo "== Pantalla (se compila dentro de Alpine y luego se quita el compilador)"
chroot "$R" /sbin/apk add --no-cache --virtual .j1-build gcc musl-dev linux-headers
mkdir -p "$R/tmp/display" "$R/usr/local/bin"
cp "$HERE/display/j1-display.c" "$HERE/display/j1-ui-font.h" "$R/tmp/display/"
chroot "$R" /usr/bin/cc -Os -static -Wall -Wextra -Werror -o /usr/local/bin/j1-display /tmp/display/j1-display.c
chroot "$R" /usr/bin/strip /usr/local/bin/j1-display
chroot "$R" /sbin/apk del .j1-build
rm -rf "$R/tmp/display"

echo "== Programas J1"
# plain copy: permissions come from here, not from the checkout (a Windows
# disk shows everything as 777), and existing Alpine directories keep theirs
cp -r --no-preserve=mode,ownership "$HERE/overlay/." "$R/"
find "$R/usr/local" -name __pycache__ -prune -exec rm -rf {} +
chmod 755 "$R/sbin/j1-init" "$R"/usr/local/sbin/*
chmod 700 "$R/usr/local/bin/j1-display"
chmod 600 "$R/usr/local/lib/j1/web.py"
mkdir -p "$R/usr/share/j1/defaults" "$R/system/etc/wifi" "$R/efs" "$R/etc/j1" "$R/etc/dropbear"
install -m 600 "$HERE"/defaults/* "$R/usr/share/j1/defaults/"
chmod 700 "$R/efs" "$R/etc/j1" "$R/etc/dropbear"
echo galaxy-j1-linux >"$R/etc/hostname"
# SSH keys live with the configuration (/etc/j1), managed from the web panel
install -d -m 700 "$R/root/.ssh"
ln -sf /etc/j1/authorized_keys "$R/root/.ssh/authorized_keys"
if [ -n "${SSH_PUBKEY:-}" ]; then
  # copied to /etc/j1 on the first boot, like every default
  install -m 600 "$SSH_PUBKEY" "$R/usr/share/j1/defaults/authorized_keys"
  echo "SSH por USB activado con $SSH_PUBKEY"
fi

echo "== Limpieza"
cleanup
rm -rf "$R"/var/cache/apk/* "$R"/tmp/* "$R/etc/resolv.conf"
# the release marker goes last in the archive: the installer checks it to
# know the archive was unpacked completely
mkdir -p "$R/usr/share/j1"
echo "j1-open-vpn $VERSION (Alpine $ALPINE)" >"$R/usr/share/j1/release"
(cd "$R" && { find . -mindepth 1 ! -path ./usr/share/j1/release | LC_ALL=C sort; echo ./usr/share/j1/release; } >"$WORK/rootfs.list")
tar --numeric-owner --no-recursion -C "$R" -cf - -T "$WORK/rootfs.list" | gzip -9n >"$OUT/j1-open-vpn-rootfs.tar.gz"
SIZE=$(stat -c %s "$OUT/j1-open-vpn-rootfs.tar.gz")
# HIDDEN holds 100 MiB
[ "$SIZE" -lt 104857600 ] || { echo "ERROR: el sistema ($SIZE bytes) no cabe en la partición HIDDEN"; exit 1; }
echo "Sistema: $SIZE bytes, $(du -sm "$R" | cut -f1) MB descomprimido"
sha256sum "$OUT/j1-open-vpn-rootfs.tar.gz"
