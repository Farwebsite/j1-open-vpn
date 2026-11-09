#!/usr/bin/python3
"""Screenshot of the visible framebuffer page as PNG (no PIL needed).
usage: j1-captura.py salida.png"""
import fcntl, mmap, os, struct, sys, zlib
fd = os.open('/dev/fb0', os.O_RDONLY)
v = fcntl.ioctl(fd, 0x4600, bytes(160))            # FBIOGET_VSCREENINFO
xres, yres, _, _, _, yoff, bpp = struct.unpack_from('7I', v)
# the driver reports R/G/B at 24/16/8, but the panel reads bytes 0, 1, 2 as
# R, G, B: capture what the panel really shows
red, green, blue = 0, 8, 16
stride = xres * bpp // 8
m = mmap.mmap(fd, stride * (yoff + yres), mmap.MAP_SHARED, mmap.PROT_READ)
raw = bytearray()
for y in range(yres):
    row = m[(yoff + y) * stride:(yoff + y + 1) * stride]
    out = bytearray(xres * 3)
    # 32 bpp little endian: channel byte = offset / 8
    out[0::3] = row[red // 8::4]; out[1::3] = row[green // 8::4]; out[2::3] = row[blue // 8::4]
    raw += b'\0' + out
def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', xres, yres, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b'')
open(sys.argv[1], 'wb').write(png)
