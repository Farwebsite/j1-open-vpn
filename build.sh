#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
# Builds everything: kernel, system and boot image, plus the Odin package and
# checksums. Run as root on Linux x86_64 (Ubuntu 22.04/24.04, Debian 12 or WSL2).
# Results in out/:
#   j1-open-vpn-boot.img        -> partition KERNEL
#   j1-open-vpn-rootfs.tar.gz   -> partition HIDDEN
#   j1-open-vpn-odin.tar        -> both, for Odin (AP slot)
#   SHA256SUMS
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
export OUT=${OUT:-$HERE/out}
export WORK=${WORK:-$HOME/j1-build}
export VERSION=$(cat "$HERE/VERSION")
mkdir -p "$OUT"

# SKIP_KERNEL=1 reuses out/zImage (the kernel takes the longest)
[ "${SKIP_KERNEL:-0}" = 1 ] && [ -f "$OUT/zImage" ] || bash "$HERE/kernel/build-kernel.sh"
bash "$HERE/rootfs/build-rootfs.sh"
bash "$HERE/boot/build-boot.sh"

echo "== Paquetes de instalación"
cd "$OUT"
# Odin picks the partition from each file name (PIT: KERNEL=boot.img, HIDDEN=hidden.img)
rm -rf odin && mkdir odin
cp j1-open-vpn-boot.img odin/boot.img
cp j1-open-vpn-rootfs.tar.gz odin/hidden.img
tar --numeric-owner --owner=0 --group=0 -H ustar -C odin -cf j1-open-vpn-odin.tar boot.img hidden.img
rm -rf odin
sha256sum j1-open-vpn-boot.img j1-open-vpn-rootfs.tar.gz j1-open-vpn-odin.tar >SHA256SUMS
# one download with everything needed to install (images + installers + guide)
python3 - "$HERE" "$VERSION" <<'EOF'
import sys, zipfile
here, version = sys.argv[1:3]
name = 'j1-open-vpn-%s.zip' % version
with zipfile.ZipFile(name, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in ('j1-open-vpn-boot.img', 'j1-open-vpn-rootfs.tar.gz', 'SHA256SUMS'):
        z.write(f, 'j1-open-vpn/' + f)
    for f in ('instalar-windows.bat', 'instalar-windows.ps1', 'instalar-linux.sh'):
        z.write(here + '/install/' + f, 'j1-open-vpn/' + f)
    z.write(here + '/docs/instalacion.md', 'j1-open-vpn/LEEME-instalacion.md')
print(name)
EOF
cat SHA256SUMS
echo "Listo: j1-open-vpn $VERSION en $OUT"
