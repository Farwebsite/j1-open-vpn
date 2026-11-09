#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Packs a Galaxy J1 (SM-J100H) boot image: Android boot header v0 with the
Spreadtrum device tree appended (its size in the header's 'dt_size' field),
padded to the 16 MiB KERNEL partition. Addresses and command line are the ones
of the stock image; the bootloader replaces the command line anyway.
usage: mkbootimg.py zImage ramdisk.cpio.gz dt.img out.img"""
import hashlib, struct, sys

PAGE = 2048
PARTITION = 16 * 1024 * 1024
KERNEL_ADDR, RAMDISK_ADDR, SECOND_ADDR, TAGS_ADDR = 0x8000, 0x1000000, 0xf00000, 0x100
CMDLINE = b'console=ttyS1,115200n8'

kernel, ramdisk, tree = (open(p, 'rb').read() for p in sys.argv[1:4])
out = sys.argv[4]
assert tree and kernel and ramdisk

sha = hashlib.sha1()
for part in (kernel, ramdisk, b'', tree):
    sha.update(part)
    sha.update(struct.pack('<I', len(part)))
header = bytearray(PAGE)
header[0:8] = b'ANDROID!'
struct.pack_into('<10I', header, 8, len(kernel), KERNEL_ADDR, len(ramdisk), RAMDISK_ADDR,
                 0, SECOND_ADDR, TAGS_ADDR, PAGE, len(tree), 0)
header[64:64 + len(CMDLINE)] = CMDLINE
header[576:596] = sha.digest()

img = bytearray(header)
for part in (kernel, ramdisk, tree):
    img += part
    img += bytes(-len(img) % PAGE)
if len(img) > PARTITION:
    sys.exit('ERROR: la imagen (%d bytes) no cabe en la partición KERNEL (%d)' % (len(img), PARTITION))
img += bytes(PARTITION - len(img))
open(out, 'wb').write(img)
print(out, hashlib.sha256(img).hexdigest())
