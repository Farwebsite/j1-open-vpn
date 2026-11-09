#!/usr/bin/python3
"""Reads SM5701 (i2c-3, 0x49) STATUS1..3 and CNTL without side effects (the INT
registers are read-to-clear and are never touched). usage: sm5701-estado.py [segundos]"""
import fcntl, os, sys, time
I2C_SLAVE_FORCE = 0x0706
S1 = {0x01: 'AICL', 0x02: 'BATOVP', 0x04: 'VBUSOK', 0x08: 'VBUSUVLO', 0x10: 'VBUSOVP',
      0x20: 'VBUSLIMIT', 0x40: 'CHGRSTF', 0x80: 'NOBAT'}
S2 = {0x01: 'TOPOFF', 0x02: 'DONE', 0x04: 'FASTTMROFF', 0x08: 'CHGON'}
S3 = {0x01: 'THEMSHDN', 0x02: 'THEMREG', 0x04: 'FLEDSHORT', 0x08: 'FLEDOPEN',
      0x10: 'BOOSTPOK_NG', 0x20: 'BOOSTPOK', 0x40: 'AMSTMROFF', 0x80: 'LOWBATT'}
MODES = {0: 'SUSPEND', 1: 'FLASH', 2: 'OTG', 3: 'OTG+FLASH', 4: 'CHARGER', 5: 'CHARGER+FLASH'}

fd = os.open('/dev/i2c-3', os.O_RDWR)
fcntl.ioctl(fd, I2C_SLAVE_FORCE, 0x49)

def reg(r):
    os.write(fd, bytes([r]))
    return os.read(fd, 1)[0]

def bits(v, names):
    return '+'.join(n for b, n in names.items() if v & b) or '-'

def line():
    s1, s2, s3, cntl = reg(0x06), reg(0x07), reg(0x08), reg(0x09)
    return (f'{time.strftime("%T")} S1={s1:02x}[{bits(s1, S1)}] S2={s2:02x}[{bits(s2, S2)}] '
            f'S3={s3:02x}[{bits(s3, S3)}] CNTL={cntl:02x}[{MODES.get(cntl & 7, cntl & 7)}]')

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 0
end = time.time() + dur
last = None
while True:
    l = line()
    if l[9:] != last:
        print(l, flush=True); last = l[9:]
    if time.time() >= end:
        break
    time.sleep(0.2)
