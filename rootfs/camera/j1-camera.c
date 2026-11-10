/* j1-camera: the J1's cameras without Android.
 *
 *   j1-camera qr    rear|front [seconds]   prints the first QR code seen
 *   j1-camera photo rear|front file.pgm    saves one 640x480 grey picture
 *
 * While looking for a QR code, every frame also goes to PREVIEW for the screen:
 * 240x320 grey, upright (the sensors are mounted at 90 and 270 degrees) and,
 * for the front camera, mirrored like a selfie.
 *
 * Exit status: 0 done, 1 no QR code before the time limit (or SIGTERM), 2 error.
 *
 * Rear: SR541 (5 MP, has its own MCU), I2C 0x28, 16-bit registers, MIPI 2 lanes
 * on D-PHY A. Front: SR200PC20 (2 MP), I2C 0x20, 8-bit registers, MIPI 1 lane on
 * D-PHY B. The sensors' register tables are Samsung's: j1-camera-tables copies
 * them out of the phone's own Android camera HAL into TABLES.
 *
 * The Samsung kernel (built for SCX35) does not set up the camera PHYs the way
 * this chip (SCX30G layout) needs; done here through /dev/mem:
 *  - AON_APB 0x24 PWR_CTRL: bit 10 / 11 power down PHY A / B (Linux boots with
 *    both set);
 *  - MM_AHB 0x0C MIPI_CSI2_CTRL selects the PHY: 0x0C = A, 0x0F = B;
 *  - after the driver opens the receiver, the selected PHY is configured again
 *    through the CSI test interface with a settle time that works.
 * The CSI registers (0x60C00000) are only touched while the receiver is open:
 * with its clock off a read hangs the bus. */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <linux/videodev2.h>

/* the part of zbar (libzbar.so.0) used here: Alpine's zbar-dev pulls in half
 * a desktop, so no header */
typedef struct zbar_image_scanner_s zbar_image_scanner_t;
typedef struct zbar_image_s zbar_image_t;
typedef struct zbar_symbol_s zbar_symbol_t;
enum { ZBAR_NONE = 0, ZBAR_QRCODE = 64, ZBAR_CFG_ENABLE = 0 };
zbar_image_scanner_t *zbar_image_scanner_create(void);
void zbar_image_scanner_destroy(zbar_image_scanner_t *);
int zbar_image_scanner_set_config(zbar_image_scanner_t *, int symbology, int config, int value);
int zbar_scan_image(zbar_image_scanner_t *, zbar_image_t *);
zbar_image_t *zbar_image_create(void);
void zbar_image_destroy(zbar_image_t *);
void zbar_image_set_format(zbar_image_t *, unsigned long fourcc);
void zbar_image_set_size(zbar_image_t *, unsigned width, unsigned height);
void zbar_image_set_data(zbar_image_t *, const void *data, unsigned long length, void (*cleanup)(zbar_image_t *));
const zbar_symbol_t *zbar_image_first_symbol(const zbar_image_t *);
const char *zbar_symbol_get_data(const zbar_symbol_t *);
#define Y800 0x30303859u   /* 'Y','8','0','0': 8-bit grey */

#define TABLES "/var/lib/j1/camera.tables"
#define PREVIEW "/run/j1-camera.preview"
#define PW 240
#define PH 320

/* ---- sensor driver (/dev/sprd_sensor) ---- */
typedef struct { uint16_t reg_addr, reg_value; uint32_t reg_bits; } SENSOR_REG_BITS_T;
typedef struct { const void *reg_tab; uint32_t reg_num, reg_bits, burst_mode; } SENSOR_REG_TAB_T;
struct sensor_power { uint32_t af, avdd, dvdd, iovdd, pd, rst, mclk; };
typedef struct { uint32_t is_on, op_sensor_id; struct sensor_power main_sensor, sub_sensor; } SENSOR_POWER_CFG_T;
typedef struct { uint32_t is_open, if_type, phy_id, lane_num, bps_per_lane; } SENSOR_IF_CFG_T;
#define SM 'R'
#define SENSOR_IO_SET_MCLK       _IOW(SM, 4, uint32_t)
#define SENSOR_IO_I2C_INIT       _IOW(SM, 6, uint32_t)
#define SENSOR_IO_I2C_DEINIT     _IOW(SM, 7, uint32_t)
#define SENSOR_IO_SET_ID         _IOW(SM, 8, uint32_t)
#define SENSOR_IO_I2C_ADDR       _IOW(SM, 10, uint16_t)
#define SENSOR_IO_I2C_READ       _IOWR(SM, 11, SENSOR_REG_BITS_T)
#define SENSOR_IO_I2C_WRITE      _IOW(SM, 12, SENSOR_REG_BITS_T)
#define SENSOR_IO_I2C_WRITE_REGS _IOW(SM, 14, SENSOR_REG_TAB_T)
#define SENSOR_IO_IF_CFG         _IOW(SM, 19, SENSOR_IF_CFG_T)
#define SENSOR_IO_POWER_CFG      _IOWR(SM, 20, SENSOR_POWER_CFG_T)

/* ---- ION (Android 3.10) ---- */
struct ion_allocation_data { size_t len, align; unsigned int heap_mask, flags; void *handle; };
struct ion_fd_data { void *handle; int fd; };
struct ion_handle_data { void *handle; };
struct ion_custom_data { unsigned int cmd; unsigned long arg; };
struct ion_phys_data { int fd_buffer; unsigned long phys; size_t size; };
#define IM 'I'
#define ION_IOC_ALLOC  _IOWR(IM, 0, struct ion_allocation_data)
#define ION_IOC_FREE   _IOWR(IM, 1, struct ion_handle_data)
#define ION_IOC_SHARE  _IOWR(IM, 4, struct ion_fd_data)
#define ION_IOC_CUSTOM _IOWR(IM, 6, struct ion_custom_data)
#define ION_HEAP_OVERLAY (1 << 3)   /* physical carve-out */

/* ---- DCAM: Spreadtrum's own use of V4L2 ---- */
enum { CAPTURE_MODE = 0x1000, CAPTURE_SKIP_NUM, CAPTURE_SENSOR_SIZE, CAPTURE_SENSOR_TRIM, CAPTURE_FRM_ID_BASE, CAPTURE_SET_CROP };
#define DCAM_PATH1 1
#define DCAM_FREE_FRAME 0xA55A   /* write() flag: give a frame back while streaming */
#define W 640
#define H 480
#define NBUF 4

struct reg { uint16_t r, v; };
struct table { uint32_t n; struct reg *t; };
/* TABLES: front init, front 640x480, rear init, rear 640x480 */
static struct table tab[4];

struct cam {
	const char *name;
	uint32_t id; uint16_t addr; uint32_t regbits;
	uint32_t lanes, bps;
	unsigned pd_bit; uint32_t phy_sel;
	uint8_t hsfreq, settle;
};
static const struct cam REAR  = {"rear", 0, 0x28, 3, 2, 672, 10, 0x0c, 0x18, 24};
static const struct cam FRONT = {"front", 1, 0x20, 0, 1, 192, 11, 0x0f, 0x22, 9};

static int sfd = -1, vfd = -1;
static uint32_t regbits;
static volatile sig_atomic_t stop;
static void on_signal(int sig) { (void)sig; stop = 1; }
static void fail(const char *m) { fprintf(stderr, "j1-camera: %s: %s\n", m, strerror(errno)); exit(2); }
static void failx(const char *m) { fprintf(stderr, "j1-camera: %s\n", m); exit(2); }

static int wreg(int r, int v) {
	SENSOR_REG_BITS_T x = {(uint16_t)r, (uint16_t)v, regbits};
	for (int try = 0; try < 3; try++) if (ioctl(sfd, SENSOR_IO_I2C_WRITE, &x) == 0) return 0;
	return -1;
}
static int rreg(int r) { SENSOR_REG_BITS_T x = {(uint16_t)r, 0, regbits}; return ioctl(sfd, SENSOR_IO_I2C_READ, &x) < 0 ? -1 : x.reg_value; }

static void load_tables(void) {
	FILE *f = fopen(TABLES, "rb");
	if (!f) fail("no sensor tables (" TABLES ", made by j1-camera-tables)");
	for (int i = 0; i < 4; i++) {
		if (fread(&tab[i].n, 4, 1, f) != 1 || tab[i].n == 0 || tab[i].n > 8192) failx("bad sensor tables");
		tab[i].t = malloc(tab[i].n * sizeof *tab[i].t);
		if (!tab[i].t || fread(tab[i].t, sizeof *tab[i].t, tab[i].n, f) != tab[i].n) failx("bad sensor tables");
	}
	fclose(f);
}

/* SR200PC20 tables: 8-bit, reg 0xff = wait in 10 ms units, ff:ff = end */
static int send8(const struct table *t) {
	int bad = 0;
	for (uint32_t i = 0; i < t->n; i++) {
		const struct reg *e = &t->t[i];
		if (e->r == 0xff && e->v == 0xff) break;
		if (e->r == 0xff) { usleep(e->v * 10000); continue; }
		bad += wreg(e->r, e->v) < 0;
	}
	return bad;
}

/* the SR541 loads code into its MCU from the init table: written one register
 * at a time it hangs, the HAL hands the whole table to the kernel (which also
 * does the 0xffff waits) */
static int send16(const struct table *t) {
	SENSOR_REG_TAB_T x = {t->t, t->n, 0x83, 0};
	return ioctl(sfd, SENSOR_IO_I2C_WRITE_REGS, &x) < 0 ? -1 : 0;
}

static void parm(int cap, int ext, uint32_t r2, uint32_t r3) {
	struct v4l2_streamparm p; memset(&p, 0, sizeof p);
	p.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	p.parm.capture.capability = cap; p.parm.capture.extendedmode = ext;
	p.parm.capture.capturemode = 1;   /* continuous */
	p.parm.capture.reserved[2] = r2; p.parm.capture.reserved[3] = r3;
	if (ioctl(vfd, VIDIOC_S_PARM, &p) < 0) fail("dcam parameters");
}

/* D-PHY test interface: CTRL0 (0x30) bit1 testclk, bit0 testclr;
 * CTRL1 (0x34) [7:0] data in, bit16 testen */
static void dphy_write(volatile uint32_t *csi, uint8_t code, uint8_t data) {
	volatile uint32_t *c0 = &csi[0x30 / 4], *c1 = &csi[0x34 / 4];
	*c1 &= ~(1u << 16); usleep(1); *c0 |= 2; usleep(1);
	*c1 = (*c1 & ~0xffu) | code; usleep(1);
	*c1 |= 1u << 16; usleep(1); *c0 &= ~2u; usleep(1);
	*c1 &= ~(1u << 16); usleep(1);
	*c1 = (*c1 & ~0xffu) | data; usleep(1); *c0 |= 2; usleep(1);
}
static void phy_setup(volatile uint32_t *csi, volatile uint32_t *mm, const struct cam *c) {
	mm[0x0c / 4] = (mm[0x0c / 4] & ~0x1fu) | c->phy_sel;
	csi[0x08 / 4] = 0; csi[0x0c / 4] = 0;                          /* PHY_SHUTDOWNZ, DPHY_RSTZ */
	csi[0x30 / 4] |= 1; usleep(1); csi[0x30 / 4] &= ~1u; usleep(1);  /* testclr pulse */
	const uint8_t cfg[][2] = {{0x34, 0x14}, {0x44, (uint8_t)(c->hsfreq << 1)}, {0x75, (uint8_t)(0x80 | c->settle)},
	                          {0x54, 0x14}, {0x64, 0x14}, {0x74, 0x14}};
	for (unsigned k = 0; k < sizeof cfg / sizeof *cfg; k++) dphy_write(csi, cfg[k][0], cfg[k][1]);
	csi[0x34 / 4] &= ~(1u << 16); usleep(1); csi[0x30 / 4] |= 2; usleep(1);
	csi[0x34 / 4] &= ~0xffu; usleep(1); csi[0x34 / 4] |= 1u << 16; usleep(1); csi[0x30 / 4] &= ~2u; usleep(1);
	csi[0x08 / 4] = 1;                                              /* PHY up */
	csi[0x0c / 4] = 0; usleep(1); csi[0x0c / 4] = 1;                /* PHY reset */
	csi[0x10 / 4] = 0; usleep(1); csi[0x10 / 4] = 1;                /* controller reset */
}

/* the Y plane, read out of uncached memory a word at a time */
static void luma(const volatile uint32_t *p, uint8_t *y) { for (int i = 0; i < W * H / 4; i++) ((uint32_t *)y)[i] = p[i]; }

/* half size, turned to portrait; written whole then renamed so the screen never reads half a frame */
static void preview(const uint8_t *y, int rear) {
	static uint8_t o[PW * PH];
	for (int r = 0; r < PH; r++) for (int c = 0; c < PW; c++) {
		/* rear, turned 90 degrees clockwise: screen row = sensor column, screen column =
		 * sensor rows bottom up. Front, turned 270 and mirrored: columns right to left */
		int sx = rear ? r * 2 : W - 2 - r * 2, sy = H - 2 - c * 2;
		o[r * PW + c] = y[sy * W + sx];
	}
	/* dim rooms: stretch the levels between the 2% darkest and brightest points
	 * (only the picture on the screen; the QR reader gets the frame as it is) */
	unsigned hist[256] = {0}, lo = 0, hi = 255, n = 0;
	for (int i = 0; i < PW * PH; i++) hist[o[i]]++;
	while (lo < 255 && (n += hist[lo]) < PW * PH / 50) lo++;
	for (n = 0; hi > 0 && (n += hist[hi]) < PW * PH / 50; ) hi--;
	if (hi > lo + 8 && (lo > 0 || hi < 255))
		for (int i = 0; i < PW * PH; i++) o[i] = o[i] <= lo ? 0 : o[i] >= hi ? 255 : (uint8_t)((o[i] - lo) * 255 / (hi - lo));
	int fd = open(PREVIEW ".tmp", O_WRONLY | O_CREAT | O_TRUNC, 0600);
	if (fd < 0) return;
	int ok = write(fd, o, sizeof o) == (ssize_t)sizeof o;
	close(fd);
	if (ok) rename(PREVIEW ".tmp", PREVIEW);
}

static int find_qr(zbar_image_scanner_t *sc, uint8_t *y) {
	zbar_image_t *im = zbar_image_create();
	zbar_image_set_format(im, Y800);
	zbar_image_set_size(im, W, H);
	zbar_image_set_data(im, y, W * H, 0);
	int found = 0;
	if (zbar_scan_image(sc, im) > 0) {
		const zbar_symbol_t *s = zbar_image_first_symbol(im);
		if (s) { fputs(zbar_symbol_get_data(s), stdout); fflush(stdout); found = 1; }
	}
	zbar_image_destroy(im);
	return found;
}

int main(int argc, char **argv) {
	if (argc < 3 || (strcmp(argv[1], "qr") && strcmp(argv[1], "photo")) || (strcmp(argv[2], "rear") && strcmp(argv[2], "front")) ||
	    (!strcmp(argv[1], "photo") && argc < 4)) {
		fprintf(stderr, "usage: j1-camera qr rear|front [seconds]\n       j1-camera photo rear|front file.pgm\n");
		return 2;
	}
	int qr = !strcmp(argv[1], "qr");
	const struct cam *c = strcmp(argv[2], "rear") ? &FRONT : &REAR;
	int rear = c == &REAR, seconds = qr ? (argc > 3 ? atoi(argv[3]) : 60) : 30;
	if (seconds < 1 || seconds > 600) seconds = 60;
	regbits = c->regbits;
	load_tables();

	struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_handler = on_signal;   /* no SA_RESTART: a signal ends DQBUF */
	sigaction(SIGTERM, &sa, 0); sigaction(SIGINT, &sa, 0); sigaction(SIGALRM, &sa, 0);
	alarm(seconds);

	/* sensor power, I2C */
	if ((sfd = open("/dev/sprd_sensor", O_RDWR)) < 0) fail("/dev/sprd_sensor");
	uint32_t id = c->id; uint16_t addr = c->addr;
	SENSOR_POWER_CFG_T pw; memset(&pw, 0, sizeof pw); pw.is_on = 1; pw.op_sensor_id = id;
	ioctl(sfd, SENSOR_IO_SET_ID, &id);
	if (ioctl(sfd, SENSOR_IO_POWER_CFG, &pw) < 0) fail("sensor power");
	usleep(20000);
	ioctl(sfd, SENSOR_IO_I2C_INIT, &id); ioctl(sfd, SENSOR_IO_I2C_ADDR, &addr);

	/* opening the capture block resets the MM block, sensor clock included:
	 * the clock is set again (the driver skips a set to the same rate) */
	mknod("/dev/video0", S_IFCHR | 0600, makedev(81, 0));
	if ((vfd = open("/dev/video0", O_RDWR)) < 0) fail("/dev/video0");
	uint32_t mclk = 0;
	if (rear) { ioctl(sfd, SENSOR_IO_SET_MCLK, &mclk); usleep(1000); }
	mclk = 24;
	if (ioctl(sfd, SENSOR_IO_SET_MCLK, &mclk) < 0) fail("sensor clock");
	usleep(10000);

	int bad;
	if (rear) {   /* the mode table ends with 0100=0103: streaming */
		bad = send16(&tab[2]) || send16(&tab[3]);
		if (bad || rreg(0x0100) != 0x0103) failx("rear camera does not answer");
	} else {      /* the mode table ends waking the sensor (01=30) */
		wreg(0x03, 0x00);
		if (rreg(0x04) != 0xb4) failx("front camera does not answer");
		bad = send8(&tab[0]) + send8(&tab[1]);
		if (bad) fprintf(stderr, "j1-camera: %d register writes failed\n", bad);
	}

	/* frame memory with a physical address */
	int ion = open("/dev/ion", O_RDWR); if (ion < 0) fail("/dev/ion");
	size_t frame = (W * H * 3 / 2 + 4095) / 4096 * 4096, total = frame * NBUF;
	struct ion_allocation_data al = {total, 4096, ION_HEAP_OVERLAY, 0, 0};
	if (ioctl(ion, ION_IOC_ALLOC, &al) < 0) fail("ion alloc");
	struct ion_fd_data sh = {al.handle, -1};
	if (ioctl(ion, ION_IOC_SHARE, &sh) < 0) fail("ion share");
	struct ion_phys_data ph = {sh.fd, 0, 0};
	struct ion_custom_data cu = {0 /* ION_SPRD_CUSTOM_PHYS */, (unsigned long)&ph};
	if (ioctl(ion, ION_IOC_CUSTOM, &cu) < 0) fail("ion phys");
	uint8_t *mem = mmap(0, total, PROT_READ | PROT_WRITE, MAP_SHARED, sh.fd, 0);
	if (mem == MAP_FAILED) fail("ion mmap");

	/* capture: path 1 turns the sensor's YUV 4:2:2 into NV21 (Y plane, then VU) */
	uint32_t tp[16]; memset(tp, 0, sizeof tp);
	tp[0] = 0; /* YUV */ tp[1] = 2; /* UYVY */ tp[5] = 8; tp[7] = c->lanes; tp[14] = 0; /* IF_OPEN */ tp[15] = 1; /* CSI2 */
	struct v4l2_control ctl = {0, (int32_t)(uintptr_t)tp};
	if (ioctl(vfd, VIDIOC_S_CTRL, &ctl) < 0) fail("dcam timing");
	parm(CAPTURE_MODE, 0, 0, 0);
	parm(CAPTURE_SKIP_NUM, 0, 0, 0);
	parm(CAPTURE_SENSOR_SIZE, 0, W, H);
	parm(CAPTURE_SENSOR_TRIM, 0, W, H);
	parm(CAPTURE_FRM_ID_BASE, 1, 0, 0);
	parm(CAPTURE_SET_CROP, 1, W, H);
	struct v4l2_format f; memset(&f, 0, sizeof f);
	f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE; f.fmt.pix.width = W; f.fmt.pix.height = H;
	f.fmt.pix.pixelformat = V4L2_PIX_FMT_NV21; f.fmt.pix.colorspace = DCAM_PATH1;
	if (ioctl(vfd, VIDIOC_S_FMT, &f) < 0) fail("dcam format");
	for (int i = 0; i < NBUF; i++) {
		struct v4l2_buffer b; memset(&b, 0, sizeof b);
		b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE; b.flags = DCAM_PATH1; b.index = i;
		b.m.userptr = ph.phys + i * frame; b.length = ph.phys + i * frame + W * H;   /* y, uv */
		if (ioctl(vfd, VIDIOC_QBUF, &b) < 0) fail("dcam buffer");
	}
	int t = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	if (ioctl(vfd, VIDIOC_STREAMON, &t) < 0) fail("dcam start");

	/* PHY power and selection; the receiver is opened after the capture started, like the HAL */
	int mfd = open("/dev/mem", O_RDWR | O_SYNC); if (mfd < 0) fail("/dev/mem");
	volatile uint32_t *aon = mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, mfd, 0x402E0000);
	volatile uint32_t *mm = mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, mfd, 0x60D00000);
	volatile uint32_t *csi = mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, mfd, 0x60C00000);
	if (aon == MAP_FAILED || mm == MAP_FAILED || csi == MAP_FAILED) fail("/dev/mem map");
	aon[0x24 / 4] &= ~(1u << c->pd_bit);
	mm[0x0c / 4] = (mm[0x0c / 4] & ~0x1fu) | c->phy_sel;
	SENSOR_IF_CFG_T ifc = {0, 1 /* MIPI */, id, c->lanes, c->bps};
	if (ioctl(sfd, SENSOR_IO_IF_CFG, &ifc) < 0) fail("mipi open");
	phy_setup(csi, mm, c);   /* the receiver is open: csi is safe now */
	if (!rear) { wreg(0x03, 0x00); wreg(0x01, 0x30); }

	/* frames */
	zbar_image_scanner_t *sc = 0;
	if (qr) {
		sc = zbar_image_scanner_create();
		zbar_image_scanner_set_config(sc, ZBAR_NONE, ZBAR_CFG_ENABLE, 0);
		zbar_image_scanner_set_config(sc, ZBAR_QRCODE, ZBAR_CFG_ENABLE, 1);
	}
	uint8_t *y = malloc(W * H);
	int result = 1, frames = 0, want = qr ? -1 : 15;   /* a picture waits for the exposure to settle */
	while (!stop && y) {
		struct v4l2_buffer b; memset(&b, 0, sizeof b); b.type = t;
		if (ioctl(vfd, VIDIOC_DQBUF, &b) < 0) { if (errno == EINTR) break; fprintf(stderr, "j1-camera: frame: %s\n", strerror(errno)); result = 2; break; }
		if (b.flags) {   /* timeout (0x10) or interrupted */
			if (!stop) { fprintf(stderr, "j1-camera: no picture from the %s camera\n", c->name); result = 2; }
			break;
		}
		const volatile uint32_t *p = (const volatile uint32_t *)(mem + (b.index % NBUF) * frame);
		frames++;
		if (qr) { luma(p, y); preview(y, rear); if (frames > 2 && find_qr(sc, y)) { result = 0; break; } }
		if (!qr && frames == want) {
			luma(p, y);
			FILE *o = fopen(argv[3], "wb");
			if (!o) { fprintf(stderr, "j1-camera: %s: %s\n", argv[3], strerror(errno)); result = 2; break; }
			fprintf(o, "P5\n%d %d\n255\n", W, H); fwrite(y, 1, W * H, o);
			result = fclose(o) ? 2 : 0;
			break;
		}
		struct v4l2_buffer fr = b; fr.flags = DCAM_FREE_FRAME;
		if (write(vfd, &fr, sizeof fr) < 0) { fprintf(stderr, "j1-camera: frame release: %s\n", strerror(errno)); result = 2; break; }
	}
	alarm(0);
	unlink(PREVIEW);

	/* everything off again, PHY powered down as at boot */
	ioctl(vfd, VIDIOC_STREAMOFF, &t);
	close(vfd);
	ifc.is_open = 1; ioctl(sfd, SENSOR_IO_IF_CFG, &ifc);
	aon[0x24 / 4] |= 1u << c->pd_bit;
	pw.is_on = 0; ioctl(sfd, SENSOR_IO_POWER_CFG, &pw);
	ioctl(sfd, SENSOR_IO_I2C_DEINIT, &id);
	munmap(mem, total); close(sh.fd);
	struct ion_handle_data hd = {al.handle}; ioctl(ion, ION_IOC_FREE, &hd);
	if (sc) zbar_image_scanner_destroy(sc);
	return result;
}
