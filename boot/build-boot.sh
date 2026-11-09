#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
# Builds the boot image: kernel (out/zImage) + initramfs (initramfs/init with the
# busybox and musl loader of Alpine armv7) + the stock J1 device tree (dt.img).
# Needs out/zImage (kernel/build-kernel.sh) and out/alpine-minirootfs
# (rootfs/build-rootfs.sh). Result: out/j1-open-vpn-boot.img
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-$HERE/../out}
MINI=$OUT/alpine-minirootfs
[ -f "$OUT/zImage" ] || { echo "Falta $OUT/zImage: ejecuta antes kernel/build-kernel.sh"; exit 1; }
[ -x "$MINI/bin/busybox" ] || { echo "Falta $MINI: ejecuta antes rootfs/build-rootfs.sh"; exit 1; }
command -v cpio >/dev/null || { echo "Falta cpio (sudo apt install cpio)"; exit 1; }

RD=$(mktemp -d)
trap 'rm -rf "$RD"' EXIT
mkdir -p "$RD"/{bin,lib,dev,proc,sys,mnt/state,newroot}
cp "$MINI/bin/busybox" "$RD/bin/busybox"
cp "$MINI/lib/ld-musl-armhf.so.1" "$RD/lib/"
ln -s ld-musl-armhf.so.1 "$RD/lib/libc.musl-armv7.so.1"
for a in sh test '['; do ln -s /bin/busybox "$RD/bin/$a"; done
install -m 755 "$HERE/initramfs/init" "$RD/init"
(cd "$RD" && find . | LC_ALL=C sort | cpio -o -H newc -R 0:0 --quiet | gzip -9n) >"$OUT/ramdisk.cpio.gz"

python3 "$HERE/mkbootimg.py" "$OUT/zImage" "$OUT/ramdisk.cpio.gz" "$HERE/dt.img" "$OUT/j1-open-vpn-boot.img"
