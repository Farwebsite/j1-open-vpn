#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# Screenshots for the documentation, on the J1 (needs gcc: apk add gcc musl-dev
# linux-headers). Shows invented data (tools/demo-pantalla.py), never the real
# configuration. The real screen is stopped meanwhile and started again at the end.
# usage: sh capturas.sh <folder with web.py j1-display.c j1-font.h demo-pantalla.py j1-captura.py> <outdir>
set -e
SRC=$1 OUT=$2
D=/tmp/j1demo
mkdir -p "$D" "$OUT"
sed 's|#define SOCK "/run/j1-ui.sock"|#define SOCK "/tmp/j1demo/run/j1-ui.sock"|' "$SRC/j1-display.c" >"$D/j1-display.c"
grep -q /tmp/j1demo/run "$D/j1-display.c"
cp "$SRC/j1-font.h" "$D/"
cc -Os -static -o "$D/j1-display" "$D/j1-display.c"
python3 "$SRC/demo-pantalla.py" "$SRC/web.py" >"$D/demo.log" 2>&1 &
DEMO=$!
sleep 3
# stop the real screen (and the loop that respawns it)
for p in $(pidof j1-display); do
 pp=$(awk '{print $4}' /proc/$p/stat); [ "$pp" -gt 1 ] && kill "$pp"; kill "$p"
done 2>/dev/null || true
sleep 1
shot() { # name screen [seconds]
 J1_UI_START=$2 "$D/j1-display" >/dev/null 2>&1 &
 pid=$!
 sleep "${3:-2}"
 python3 "$SRC/j1-captura.py" "$OUT/$1.png"
 kill $pid; wait $pid 2>/dev/null || true
}
shot inicio nav:home
shot wifi nav:wifi
shot wireguard nav:vpn
shot cliente nav:client:0000000000000001
shot qr nav:qr:0000000000000001
shot pantalla nav:disp
shot recursos nav:res 5
shot sistema nav:sys
shot velocidad nav:speed
shot apagar nav:power
kill $DEMO
rm -rf "$D"
# real screen back (same loop as j1-init)
export TZ="$(cat /etc/j1/tz 2>/dev/null || echo CET-1CEST,M3.5.0,M10.5.0/3)" J1_UI_DEBUG=1
setsid sh -c "while :; do /usr/local/bin/j1-display; sleep 2; done" >>/run/display.log 2>&1 </dev/null &
ls -l "$OUT"
