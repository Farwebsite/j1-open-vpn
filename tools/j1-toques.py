#!/usr/bin/python3
"""Touch simulator for testing j1-display: creates a virtual multitouch
screen (uinput), runs a test instance of the display on it and replays
taps / keys. usage: j1-toques.py "tap 240 500" "key 158" "hold 116 2" "shot nombre" "wait 1" ...
Needs the real display stopped (it owns the framebuffer)."""
import fcntl, os, struct, subprocess, sys, time
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
MT_SLOT, MT_X, MT_Y, MT_ID = 0x2f, 0x35, 0x36, 0x39
fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
for ev in (EV_SYN, EV_KEY, EV_ABS): fcntl.ioctl(fd, 0x40045564, ev)            # UI_SET_EVBIT
for k in (158, 254, 116): fcntl.ioctl(fd, 0x40045565, k)                            # UI_SET_KEYBIT
for a in (MT_SLOT, MT_X, MT_Y, MT_ID): fcntl.ioctl(fd, 0x40045567, a)          # UI_SET_ABSBIT
absmax = [0] * 64; absmax[MT_SLOT] = 1; absmax[MT_X] = 478; absmax[MT_Y] = 798; absmax[MT_ID] = 65535
os.write(fd, struct.pack('80sHHHHI', b'j1-toques', 3, 1, 1, 1, 0) + struct.pack('64i', *absmax) + bytes(3 * 64 * 4))
fcntl.ioctl(fd, 0x5501)                                                          # UI_DEV_CREATE
time.sleep(0.3)
ev = next(d for d in os.listdir('/sys/class/input') if d.startswith('event') and
          open('/sys/class/input/%s/device/name' % d).read().strip() == 'j1-toques')
# no udev here: make the device node ourselves
major, minor = map(int, open('/sys/class/input/%s/dev' % ev).read().split(':'))
dev = '/run/j1-toques-ev'
if os.path.exists(dev): os.unlink(dev)
os.mknod(dev, 0o600 | 0o020000, os.makedev(major, minor))
def emit(t, c, v): os.write(fd, struct.pack('llHHi', 0, 0, t, c, v))
def syn(): emit(EV_SYN, 0, 0)
env = dict(os.environ, J1_UI_TOUCH=dev, J1_UI_KEYS=dev, J1_UI_DEBUG='1')
log = open('/run/j1-toques.log', 'w')
disp = subprocess.Popen([os.environ.get('J1_UI_BIN', '/usr/local/bin/j1-display')], env=env, stdout=log, stderr=log)
time.sleep(1)
tid = 1
for cmd in sys.argv[1:]:
    op, *a = cmd.split()
    t0 = time.monotonic()
    if op == 'tap':
        x, y = int(a[0]), int(a[1])
        emit(EV_ABS, MT_SLOT, 0); emit(EV_ABS, MT_ID, tid); emit(EV_ABS, MT_X, x); emit(EV_ABS, MT_Y, y); syn()
        time.sleep(0.08); emit(EV_ABS, MT_ID, -1); syn(); tid += 1
        print('%.3f toque %d,%d' % (t0, x, y), file=log, flush=True)
    elif op in ('wobble', 'swipe', 'hswipe'):
        # wobble x y dy: tap that slides dy px; swipe x y dy: slow drag
        x, y, dy = int(a[0]), int(a[1]), int(a[2]); steps = 4 if op == 'wobble' else 12
        emit(EV_ABS, MT_SLOT, 0); emit(EV_ABS, MT_ID, tid); emit(EV_ABS, MT_X, x); emit(EV_ABS, MT_Y, y); syn()
        for k in range(1, steps + 1):
            time.sleep(0.02 if op == 'wobble' else 0.05); emit(EV_ABS, MT_X if op == 'hswipe' else MT_Y, (x if op == 'hswipe' else y) + dy * k // steps); syn()
        emit(EV_ABS, MT_ID, -1); syn(); tid += 1
        print('%.3f %s %d,%d %+d' % (t0, op, x, y, dy), file=log, flush=True)
    elif op == 'key':
        emit(EV_KEY, int(a[0]), 1); syn(); emit(EV_KEY, int(a[0]), 0); syn()
        print('%.3f tecla %s' % (t0, a[0]), file=log, flush=True)
    elif op == 'hold':
        # hold 116 2: keep a key down for some seconds
        emit(EV_KEY, int(a[0]), 1); syn(); time.sleep(float(a[1])); emit(EV_KEY, int(a[0]), 0); syn()
        print('%.3f tecla %s mantenida %ss' % (t0, a[0], a[1]), file=log, flush=True)
    elif op == 'wait': time.sleep(float(a[0]))
    elif op == 'shot': subprocess.run(['python3', '/root/j1-ui-src/j1-captura.py', '/root/j1-ui-src/%s.png' % a[0]])
    time.sleep(0.6)
disp.terminate(); disp.wait()
fcntl.ioctl(fd, 0x5502)                                                          # UI_DEV_DESTROY
print(open('/run/j1-toques.log').read())
