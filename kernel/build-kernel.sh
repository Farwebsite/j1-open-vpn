#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
# Builds the J1 Open VPN kernel (zImage) for the Galaxy J1 SM-J100H (j13g):
#  - j13g kernel 3.10 (LineageOS cm-12.1 tree), pinned commit
#  - USB host / OTG role switch with automatic 5 V (patch/j1_usb_host.c)
#  - USB Ethernet drivers (CDC Ethernet, RTL8152/8153, ASIX)
#  - WireGuard inside the kernel (wireguard-linux-compat)
#  - normal boot even when powered on by the charger
# Runs on Linux x86_64 (Ubuntu/Debian or WSL). Uses $WORK (default ~/j1-build).
# Result: $OUT/zImage (default: ../out/zImage next to this script).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$HOME/j1-build}
OUT=${OUT:-$HERE/../out}

KERNEL_URL=https://github.com/jnkcode/android_kernel_samsung_j13g.git
KERNEL_REV=8e519128a49ea37cc5af92185ab30e6b897c3b40        # cm-12.1
WG_URL=https://github.com/WireGuard/wireguard-linux-compat.git
WG_REV=v1.0.20220627
TC_URL=https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/arm/arm-eabi-4.8
TC_REV=26e93f6af47f7bd3a9beb5c102a5f45e19bfa38a           # android-8.1.0_r1

for c in git make gcc bc bison flex python3 perl; do
  command -v $c >/dev/null || { echo "Falta '$c'. En Ubuntu/Debian: sudo apt install git build-essential bc bison flex python3 perl"; exit 1; }
done
mkdir -p "$WORK" "$OUT"
cd "$WORK"

fetch() { # url dir rev
  [ -d "$2/.git" ] || git clone -q "$1" "$2"
  git -C "$2" checkout -q -f "$3" 2>/dev/null || { git -C "$2" fetch -q --all --tags; git -C "$2" checkout -q -f "$3"; }
  echo "$2: $(git -C "$2" rev-parse --short HEAD)"
}
echo "== Fuentes"
# the prebuilts repository is huge: only the tagged snapshot
[ -d toolchain/.git ] || git clone -q --depth 1 -b android-8.1.0_r1 "$TC_URL" toolchain
[ "$(git -C toolchain rev-parse HEAD)" = "$TC_REV" ] || { echo "ERROR: el compilador descargado no es la versión esperada"; exit 1; }
fetch "$KERNEL_URL" kernel "$KERNEL_REV"
fetch "$WG_URL" wireguard "$WG_REV"
git -C kernel clean -qfdx

echo "== Parches"
python3 "$HERE/patch/apply.py" "$WORK/kernel"
cp -a wireguard/src kernel/net/wireguard
# wireguard-linux-compat uses the 5.4+ 'fallthrough' keyword without defining it for 3.10
sed -i '1i #ifndef fallthrough\n#define fallthrough do {} while (0)\n#endif' kernel/net/wireguard/compat/siphash/siphash.c
sed -i '0,/^if INET$/s//if INET\nsource "net\/wireguard\/Kconfig"/' kernel/net/Kconfig
echo 'obj-$(CONFIG_WIREGUARD) += wireguard/' >> kernel/net/Makefile

echo "== Configuración"
export ARCH=arm CROSS_COMPILE=$WORK/toolchain/bin/arm-eabi-
# neutral build identity (otherwise the build machine name ends up in the kernel)
export KBUILD_BUILD_USER=j1 KBUILD_BUILD_HOST=j1-open-vpn
HOSTCFLAGS="-Wall -Wmissing-prototypes -Wstrict-prototypes -O2 -fomit-frame-pointer -fcommon"
B=$WORK/kernel-out
rm -rf "$B" && mkdir -p "$B"
make -s -C kernel O="$B" "HOSTCFLAGS=$HOSTCFLAGS" j13g-dt_hw00_defconfig
kernel/scripts/config --file "$B/.config" \
   --disable SPRD_USB_DEVICE_ONLY --enable J1_USB_HOST \
   --enable USB_USBNET --enable USB_NET_CDCETHER \
   --enable USB_NET_RTL8152 --enable USB_NET_AX8817X --enable USB_NET_AX88179_178A \
   --enable USB_STORAGE \
   --enable WIREGUARD --disable WIREGUARD_DEBUG \
   --set-str LOCALVERSION "-j1wg" --disable LOCALVERSION_AUTO
make -s -C kernel O="$B" "HOSTCFLAGS=$HOSTCFLAGS" olddefconfig >/dev/null
for o in J1_USB_HOST USB_NET_CDCETHER WIREGUARD; do
  grep -q "^CONFIG_$o=y" "$B/.config" || { echo "ERROR: CONFIG_$o no quedó activado"; exit 1; }
done

echo "== Compilando (10-30 min)"
make -s -C kernel O="$B" "HOSTCFLAGS=$HOSTCFLAGS" -j"$(nproc)" zImage >"$WORK/build.log" 2>&1 || {
  echo "ERROR de compilación. Últimas líneas de $WORK/build.log:"; grep -nE "error:|Error [0-9]" "$WORK/build.log" | head -20; exit 1; }
cp "$B/arch/arm/boot/zImage" "$OUT/zImage"
cp "$B/.config" "$OUT/kernel.config"
strings "$B/vmlinux" | grep "Linux version" | head -1 || true
sha256sum "$OUT/zImage"
