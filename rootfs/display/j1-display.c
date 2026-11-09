/* SPDX-License-Identifier: GPL-2.0 */
/* J1 touch screen: draws the widgets that web.py sends over /run/j1-ui.sock
 * (protocol described in web.py) and sends back taps and typed fields.
 * Idle cost is zero: with the backlight off it only blocks in poll(). */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <time.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <linux/fb.h>
#include <linux/input.h>
#include "j1-font.h"

#define SOCK "/run/j1-ui.sock"
#define TOP 60          /* title bar */
#define PAD 14
#define MAXEL 400

static int fb, SW, SH, stride;
static struct fb_var_screeninfo v;
static struct fb_fix_screeninfo f;
static unsigned char *mem;
static uint32_t *buf;
/* sprdfb reports R/G/B at bits 24/16/8, but this panel reads the pixel bytes as
 * R, G, B from the lowest byte (XBGR8888): with the reported offsets every color
 * came out shifted (green looked blue). */
#define R_OFF 0
#define G_OFF 8
#define B_OFF 16
static int clip0, clip1;
static uint32_t C_ACC, C_OKB, C_LINE, C_BG, C_BAR, C_TXT, C_MUT, C_GRN, C_YEL, C_RED, C_BTN, C_PRI, C_DNG, C_ITM, C_FLD, C_KEY, C_KEYS, C_DOWN, C_WHITE, C_BLACK;

static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
static void value(const char *p, const char *s) { int fd = open(p, O_WRONLY); if (fd >= 0) { if (write(fd, s, strlen(s)) < 0) {} close(fd); } }
static uint32_t color(unsigned r, unsigned g, unsigned b) {
	return ((r >> (8 - v.red.length)) << R_OFF) | ((g >> (8 - v.green.length)) << G_OFF) |
	       ((b >> (8 - v.blue.length)) << B_OFF) | (v.transp.length ? (((1U << v.transp.length) - 1) << v.transp.offset) : 0);
}

/* ---- drawing ---- */
static void fill(int x, int y, int w, int h, uint32_t c) {
	if (x < 0) { w += x; x = 0; }
	if (y < clip0) { h -= clip0 - y; y = clip0; }
	if (x + w > SW) w = SW - x;
	if (y + h > clip1) h = clip1 - y;
	for (int j = 0; j < h; j++) { uint32_t *p = buf + (size_t)(y + j) * stride + x; for (int i = 0; i < w; i++) p[i] = c; }
}
static void put(int x, int y, uint32_t c) {
	if (x >= 0 && x < SW && y >= clip0 && y < clip1) buf[(size_t)y * stride + x] = c;
}
/* mix two colors, a = 0..256 parts of c1 (antialiased corners) */
static uint32_t mix(uint32_t c1, uint32_t c2, int a) {
	uint32_t o = 0;
	for (int k = 0; k < 3; k++) {
		int off = k == 0 ? R_OFF : k == 1 ? G_OFF : B_OFF;
		int x1 = (c1 >> off) & 255, x2 = (c2 >> off) & 255;
		o |= (uint32_t)((x1 * a + x2 * (256 - a)) >> 8) << off;
	}
	return o | (c1 & ~((255u << R_OFF) | (255u << G_OFF) | (255u << B_OFF)));
}
/* rounded rectangle; the curved edge pixel is blended with what is under it */
static void rrect(int x, int y, int w, int h, int r, uint32_t c) {
	if (r * 2 > h) r = h / 2;
	if (r * 2 > w) r = w / 2;
	for (int j = 0; j < h; j++) {
		int yy = y + j;
		if (yy < clip0 || yy >= clip1) continue;
		int d = j < r ? r - j : j >= h - r ? j - (h - r) + 1 : 0;
		if (!d) { fill(x, yy, w, 1, c); continue; }
		float dy = d - 0.5f, dx = r - __builtin_sqrtf((float)(r * r) - dy * dy);
		int in = (int)dx; int a = (int)((1.0f - (dx - in)) * 256);
		fill(x + in + 1, yy, w - 2 * (in + 1), 1, c);
		if (x + in >= 0 && x + in < SW) put(x + in, yy, mix(c, buf[(size_t)yy * stride + x + in], a));
		if (x + w - 1 - in >= 0 && x + w - 1 - in < SW) put(x + w - 1 - in, yy, mix(c, buf[(size_t)yy * stride + x + w - 1 - in], a));
	}
}
/* Scale2x: doubles a 1-bit bitmap rounding the diagonals (smoother than plain 2x) */
static void scale2x(const uint16_t *in, int w, int h, uint32_t *out) {
#define PX(X, Y) ((X) < 0 || (Y) < 0 || (X) >= w || (Y) >= h ? 0 : (in[Y] >> (w - 1 - (X))) & 1)
	for (int y = 0; y < h; y++) { out[2 * y] = out[2 * y + 1] = 0; }
	for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
		int P = PX(x, y), A = PX(x, y - 1), B = PX(x + 1, y), C = PX(x - 1, y), D = PX(x, y + 1);
		int e0 = (C == A && C != D && A != B) ? A : P, e1 = (A == B && A != C && B != D) ? B : P;
		int e2 = (D == C && D != B && C != A) ? C : P, e3 = (B == D && B != A && D != C) ? D : P;
		int bx = 2 * w - 1 - 2 * x;
		out[2 * y] |= (uint32_t)e0 << bx | (uint32_t)e1 << (bx - 1);
		out[2 * y + 1] |= (uint32_t)e2 << bx | (uint32_t)e3 << (bx - 1);
	}
#undef PX
}
static uint32_t big[256][32];   /* font at 2x, smoothed once at start */
static void font_init(void) {
	for (int ch = 0; ch < 256; ch++) { uint16_t g[16]; for (int j = 0; j < 16; j++) g[j] = font8x16[ch * 16 + j]; scale2x(g, 8, 16, big[ch]); }
}
static void glyph(int x, int y, unsigned char ch, int s, uint32_t c) {
	if (y + 16 * s <= clip0 || y >= clip1) return;
	if (s == 2) { for (int j = 0; j < 32; j++) { uint32_t b = big[ch][j]; for (int i = 0; i < 16; i++) if (b & (1u << (15 - i))) put(x + i, y + j, c); } return; }
	for (int j = 0; j < 16; j++) { unsigned b = font8x16[ch * 16 + j]; for (int i = 0; i < 8; i++) if (b & (128 >> i)) fill(x + i * s, y + j * s, s, s, c); }
}

/* 16x16 icons, drawn at 32x32 with Scale2x */
static const char *ICONS[][17] = {
	{"wifi", "................", "....########....", "..##........##..", ".#............#.", "#....######....#", "...##......##...",
	 "..#..........#..", "......####......", ".....#....#.....", "................", ".......##.......", "......####......",
	 ".......##.......", "................", "................", "................"},
	{"ap", "................", "................", ".#............#.", "#..#........#..#", "#.#..........#.#", "#.#...####...#.#",
	 "#.#...####...#.#", "#..#...##...#..#", ".#.....##.....#.", ".......##.......", "......####......", "......#..#......",
	 ".....#....#.....", ".....#....#.....", "....##....##....", "................"},
	{"vpn", ".......##.......", ".....##..##.....", "...##......##...", ".##..........##.", ".#............#.", ".#.........##.#.",
	 ".#........##..#.", ".#..##...##...#.", ".#...##.##....#.", "..#...###....#..", "..#....#.....#..", "...#........#...",
	 "....#......#....", ".....##..##.....", ".......##.......", "................"},
	{"dns", "................", "................", "................", "................", "......####......", ".....#....#.....",
	 "..###......#....", ".#..........##..", "#.............#.", "#..............#", "#..............#", ".#............#.",
	 "..############..", "................", "................", "................"},
	{"usb", "................", ".....######.....", ".....#.##.#.....", ".....#.##.#.....", "...##########...", "...#........#...",
	 "...#........#...", "...#........#...", "....#......#....", ".....######.....", ".......##.......", ".......##.......",
	 ".......##.......", ".......##.......", ".......##.......", "................"},
	{"res", "................", "............###.", "............###.", "............###.", "........###.###.", "........###.###.",
	 "........###.###.", "....###.###.###.", "....###.###.###.", "....###.###.###.", "###.###.###.###.", "###.###.###.###.",
	 "###.###.###.###.", "################", "................", "................"},
	{"disp", ".......##.......", "..#....##....#..", "...#........#...", "......####......", ".....######.....", "....########....",
	 "##..########..##", "##..########..##", "....########....", ".....######.....", "......####......", "...#........#...",
	 "..#....##....#..", ".......##.......", "................", "................"},
	{"logs", "................", "................", "##..##########..", "##..##########..", "................", "................",
	 "##..########....", "##..########....", "................", "................", "##..##########..", "##..##########..",
	 "................", "................", "##..#######.....", "##..#######....."},
	{"sys", "......####......", "......####......", "..##..####..##..", "..############..", "...##########...", "..####....####..",
	 "####........####", "####........####", "####........####", "####........####", "..####....####..", "...##########...",
	 "..############..", "..##..####..##..", "......####......", "......####......"},
	{"qr", "#######..#######", "#.....#..#.....#", "#.###.#..#.###.#", "#.###.#..#.###.#", "#.###.#..#.###.#", "#.....#..#.....#",
	 "#######..#######", "................", "................", "#######..##..#.#", "#.....#...##..#.", "#.###.#..#..##.#",
	 "#.###.#..##..#..", "#.###.#...##.###", "#.....#..#..#..#", "#######..###.#.#"},
	{"ip", "................", ".....######.....", "...##..##..##...", "..#...#..#...#..", ".#...#....#...#.", ".##############.",
	 "#....#....#....#", "#....#....#....#", "#....#....#....#", "#....#....#....#", ".##############.", ".#...#....#...#.",
	 "..#...#..#...#..", "...##..##..##...", ".....######.....", "................"},
	{"user", "................", "......####......", ".....######.....", ".....######.....", ".....######.....", "......####......",
	 "................", "....########....", "...##########...", "..############..", "..############..", "..############..",
	 "................", "................", "................", "................"},
	{"power", "................", ".......##.......", "...#...##...#...", "..#....##....#..", ".#.....##.....#.", "#......##......#",
	 "#......##......#", "#..............#", "#..............#", ".#............#.", "..#..........#..", "...##......##...",
	 ".....######.....", "................", "................", "................"},
};
#define NICONS (int)(sizeof ICONS / sizeof ICONS[0])
static uint32_t icon_big[NICONS][32];
static void icons_init(void) {
	for (int n = 0; n < NICONS; n++) {
		uint16_t g[16];
		for (int j = 0; j < 16; j++) { g[j] = 0; for (int i = 0; i < 16; i++) if (ICONS[n][j + 1][i] == '#') g[j] |= 1u << (15 - i); }
		scale2x(g, 16, 16, icon_big[n]);
	}
}
static int icon_id(const char *name) {
	if (!name || !*name) return -1;
	for (int n = 0; n < NICONS; n++) if (!strcmp(ICONS[n][0], name)) return n;
	return -1;
}
static void icon(int x, int y, int n, uint32_t c) {
	for (int j = 0; j < 32; j++) { uint32_t b = icon_big[n][j]; for (int i = 0; i < 32; i++) if (b & (1u << (31 - i))) put(x + i, y + j, c); }
}
static void textn(int x, int y, const char *s, int n, int sc, uint32_t c) {
	for (int i = 0; i < n && s[i] && x + 8 * sc <= SW; i++, x += 8 * sc) glyph(x, y, (unsigned char)s[i], sc, c);
}
static void text(int x, int y, const char *s, int sc, uint32_t c) { textn(x, y, s, (int)strlen(s), sc, c); }
/* any size (nearest pixel), for text between scale 1 and 2 */
static void textwh(int x, int y, const char *s, int w, int h, uint32_t c) {
	for (; *s && x + w <= SW; s++, x += w)
		for (int j = 0; j < h; j++) { unsigned b = font8x16[(unsigned char)*s * 16 + j * 16 / h]; for (int i = 0; i < w; i++) if (b & (128 >> (i * 8 / w))) fill(x + i, y + j, 1, 1, c); }
}
/* word wrap; returns the height used */
static int wrap(const char *s, int x, int y, int w, int sc, uint32_t c, int draw) {
	int cols = w / (8 * sc), lh = 16 * sc + (sc > 1 ? 4 : 2), lines = 0;
	if (cols < 1) cols = 1;
	while (*s) {
		int n = (int)strlen(s), take = n;
		if (n > cols) { take = cols; for (int k = cols; k > cols / 2; k--) if (s[k] == ' ') { take = k; break; } }
		if (draw) textn(x, y + lines * lh, s, take, sc, c);
		lines++; s += take; while (*s == ' ') s++;
	}
	return (lines ? lines : 1) * lh;
}

/* ---- screen model ---- */
struct el { char t, *a, *b, *c, *d; int y, h, dirty; char val[160]; };
static struct el els[MAXEL];
static int nel, content_h, scroll, refresh_s, idle_s = 60;
static void set_deadline(void), set_bright(void);
static int dimmed, bright = 143;   /* backlight 0-255 from web.py */
static char resp[131072], screen_id[128] = "home", back[128], title[128];
static int busy, shown = 1, wakes;

static uint32_t tcolor(const char *c) {
	switch (c ? *c : 'n') { case 'g': return C_GRN; case 'y': return C_YEL; case 'r': return C_RED; case 'm': return C_MUT; default: return C_TXT; }
}
static int slider_val(const struct el *e, int *lo, int *hi) {
	*lo = e->c ? atoi(e->c) : 0; *hi = e->d ? atoi(e->d) : 100; if (*hi <= *lo) *hi = *lo + 1;
	int v = atoi(e->val); return v < *lo ? *lo : v > *hi ? *hi : v;
}
static int qr_dims(const char *q, int *cols, int *rows) {
	const char *e = strchr(q, ',');
	*cols = e ? (int)(e - q) : (int)strlen(q); *rows = 0;
	if (*cols <= 0) return 0;
	for (const char *p = q; *p; p++) if (*p == ',') (*rows)++;
	(*rows)++;
	int m = (SW - 2 * PAD) / (*cols + 8); return m > 8 ? 8 : m < 1 ? 1 : m;
}
static void layout(void) {
	int y = 8, w = SW - 2 * PAD;
	for (int i = 0; i < nel; i++) {
		struct el *e = &els[i]; e->y = y; e->h = 0;
		switch (e->t) {
		case 'M': e->h = wrap(e->a, 0, 0, w - 16, 2, 0, 0) + 20; break;
		case 'L': { char k = e->b ? *e->b : 'n'; int dot = k == 'g' || k == 'y' || k == 'r';   /* same width as when drawn */
			e->h = wrap(e->a, 0, 0, dot ? w - 26 : w, 2, 0, 0) + 6; break; }
		case 'l': e->h = wrap(e->a, 0, 0, w, 1, 0, 0); break;
		case 'B': e->h = (e->c && *e->c == 'i') ? 66 : 72; break;
		case 'S': case 'D': e->h = 72; break;
		case 'F': e->h = 22 + 54 + 12; break;
		case 'G': e->h = 18; break;
		case 'Q': { int c, r, m = qr_dims(e->a, &c, &r); e->h = (r + 8) * m + 12; break; }
		}
		y += e->h;
	}
	content_h = y + 24;
}
static int view_h(void);
static void clamp_scroll(void) { int m = content_h - view_h(); if (scroll > m) scroll = m; if (scroll < 0) scroll = 0; }

/* parse resp in place; keeps edited field values when the screen is the same */
static void parse(int keep_dirty) {
	static char kn[64][64], kv[64][160]; int nk = 0;
	for (int i = 0; i < nel && nk < 64; i++) if (els[i].t == 'F' && els[i].dirty) {
		snprintf(kn[nk], 64, "%s", els[i].a); snprintf(kv[nk], 160, "%s", els[i].val); nk++;
	}
	char old[128]; snprintf(old, sizeof old, "%s", screen_id);
	nel = 0; refresh_s = 0; back[0] = 0; title[0] = 0;
	char *p = resp;
	while (*p && nel < MAXEL) {
		char *nl = strchr(p, '\n'); if (nl) *nl = 0;
		char *fld[5] = {0}; int nf = 0;
		for (char *q = p; nf < 5;) { fld[nf++] = q; char *t = strchr(q, '\t'); if (!t) break; *t = 0; q = t + 1; }
		if (fld[0][0] == 'T') {
			snprintf(screen_id, sizeof screen_id, "%s", fld[1] ? fld[1] : "home");
			snprintf(title, sizeof title, "%s", fld[2] ? fld[2] : "");
			snprintf(back, sizeof back, "%s", fld[3] ? fld[3] : "");
		} else if (fld[0][0] == 'R') refresh_s = fld[1] ? atoi(fld[1]) : 0;
		else if (fld[0][0] == 'O') {   /* a new time applies at once */
			int o = fld[1] ? atoi(fld[1]) : 60;
			if (o != idle_s) { idle_s = o; set_deadline(); }
		}
		else if (fld[0][0] == 'V') {   /* brightness too */
			int v = fld[1] ? atoi(fld[1]) : 143;
			if (v < 13 || v > 255) v = 143;
			if (v != bright) { bright = v; if (shown && !dimmed) set_bright(); }
		}
		else if (fld[0][0] && (fld[1] || fld[0][0] == 'G')) {
			struct el *e = &els[nel++]; memset(e, 0, sizeof *e);
			e->t = fld[0][0]; e->a = fld[1] ? fld[1] : (char *)""; e->b = fld[2]; e->c = fld[3]; e->d = fld[4];
			if (e->t == 'F') snprintf(e->val, sizeof e->val, "%s", e->c ? e->c : "");
			if (e->t == 'D') snprintf(e->val, sizeof e->val, "%s", e->b ? e->b : "0");
		}
		if (!nl) break;
		p = nl + 1;
	}
	int same = !strcmp(old, screen_id);
	if (!same) scroll = 0;
	if (same && keep_dirty)
		for (int i = 0; i < nel; i++) if (els[i].t == 'F')
			for (int k = 0; k < nk; k++) if (!strcmp(kn[k], els[i].a)) { snprintf(els[i].val, sizeof els[i].val, "%s", kv[k]); els[i].dirty = 1; }
	layout(); clamp_scroll();
}

/* ---- keyboard ---- */
static int kb_open, kb_layer, kb_shift, kb_show; static struct el *kb_el; static char kb_buf[160];
static const char *KB[3][3] = {
	{"qwertyuiop", "asdfghjkl\xa4", "zxcvbnm"},
	{"1234567890", "@#$%&*-+()", "!\"':;/?"},
	{"[]{}<>^~`|", "\\_=\xa8\xad\xa0\x82\xa1\xa2\xa3", "\xa5\x81\xf8\xfa\xa6\xa7\x9c"},
};
#define KH 70
#define KBY (SH - 4 * KH)
#define PVH 84          /* preview bar above the keys */
static int view_h(void) { return (kb_open ? KBY - PVH : SH) - TOP; }

struct key { int x, y, w, h; int code; const char *label; };
enum { K_SHIFT = 256, K_BS, K_LAYER, K_LAYER2, K_OK, K_SPACE, K_CANCEL, K_SHOW };
static int keys(struct key *k) {
	int n = 0, y = KBY;
	static char lab[3][10][2];
	for (int r = 0; r < 3; r++, y += KH) {
		const char *row = KB[kb_layer][r]; int len = (int)strlen(row), x = r < 2 ? 0 : 72;
		if (r == 2) k[n++] = (struct key){0, y, 72, KH, kb_layer == 0 ? K_SHIFT : K_LAYER2, kb_layer == 0 ? "\x18" : kb_layer == 1 ? "#+=" : "123"};
		for (int i = 0; i < len; i++) {
			int c = (unsigned char)row[i];
			if (kb_layer == 0 && kb_shift) c = c == 0xa4 ? 0xa5 : (c >= 'a' && c <= 'z') ? c - 32 : c;
			lab[r][i][0] = (char)c; lab[r][i][1] = 0;
			k[n++] = (struct key){x, y, 48, KH, c, lab[r][i]}; x += 48;
		}
		if (r == 2) k[n++] = (struct key){SW - 72, y, 72, KH, K_BS, "\x1b"};
	}
	k[n++] = (struct key){0, y, 96, KH, K_LAYER, kb_layer ? "abc" : "123"};
	k[n++] = (struct key){96, y, 48, KH, ',', ","};
	k[n++] = (struct key){144, y, 192, KH, K_SPACE, "espacio"};
	k[n++] = (struct key){336, y, 48, KH, '.', "."};
	k[n++] = (struct key){384, y, SW - 384, KH, K_OK, "OK"};
	k[n++] = (struct key){SW - 64, KBY - PVH, 64, PVH, K_CANCEL, "X"};
	if (kb_el && kb_el->d && *kb_el->d == 'p') k[n++] = (struct key){SW - 136, KBY - PVH, 72, PVH, K_SHOW, kb_show ? "ocul" : "ver"};
	return n;
}
static int kb_down = -1;
static void draw_keyboard(void) {
	struct key k[64]; int n = keys(k);
	clip0 = 0; clip1 = SH;
	fill(0, KBY - PVH, SW, SH - KBY + PVH, C_BAR);
	text(PAD, KBY - PVH + 6, kb_el && kb_el->b ? kb_el->b : "", 1, C_MUT);
	char shown_txt[160]; int len = (int)strlen(kb_buf);
	if (kb_el && kb_el->d && *kb_el->d == 'p' && !kb_show) { memset(shown_txt, '*', len); shown_txt[len] = 0; }
	else snprintf(shown_txt, sizeof shown_txt, "%s", kb_buf);
	int cols = (SW - 150 - PAD) / 16; const char *t = shown_txt; if (len > cols - 1) t += len - (cols - 1);
	rrect(PAD - 4, KBY - PVH + 28, SW - 150, 48, 10, C_FLD);
	text(PAD, KBY - PVH + 36, t, 2, C_WHITE);
	glyph(PAD + 16 * (int)strlen(t), KBY - PVH + 36, '_', 2, C_ACC);
	for (int i = 0; i < n; i++) {
		if (k[i].code == K_CANCEL || k[i].code == K_SHOW) { int sc = 2; text(k[i].x + (k[i].w - (int)strlen(k[i].label) * 8 * sc) / 2, k[i].y + 26, k[i].label, sc, k[i].code == K_CANCEL ? C_RED : C_ACC); continue; }
		uint32_t bg = i == kb_down ? C_DOWN : (k[i].code >= 256 ? C_KEYS : C_KEY);
		if (k[i].code == K_OK) bg = i == kb_down ? C_DOWN : C_PRI;
		if (k[i].code == K_SHIFT && kb_shift) bg = C_ACC;
		rrect(k[i].x + 3, k[i].y + 4, k[i].w - 6, k[i].h - 8, 9, bg);
		int sc = strlen(k[i].label) > 3 ? 1 : 2, tw = (int)strlen(k[i].label) * 8 * sc;
		text(k[i].x + (k[i].w - tw) / 2, k[i].y + (k[i].h - 16 * sc) / 2, k[i].label, sc, k[i].code == K_OK ? C_BLACK : C_WHITE);
	}
}

/* ---- render ---- */
static int pressed = -1;
/* The display controller shows a new pan page only on the *next* pan, so page
 * flipping left every change one frame behind (visible only after the next
 * tap or refresh). Instead: draw into RAM and copy the finished frame onto
 * page 0, which the video-mode panel scans continuously. */
static uint32_t *backbuf;
static void show_page0(void) {
	for (int i = 0; i < 2; i++) {   /* twice: the first pan only arms it */
		v.yoffset = 0; v.activate = FB_ACTIVATE_NOW;
		if (ioctl(fb, FBIOPAN_DISPLAY, &v) < 0) perror("FBIOPAN_DISPLAY");
	}
}
static void present(void) { memcpy(mem, backbuf, (size_t)SH * f.line_length); }
/* the time zone can change while running (web.py rewrites /etc/j1/tz) */
static void tz_follow(void) {
	static time_t seen_t = -1; static ino_t seen_i;
	struct stat st; char tz[96];
	if (stat("/etc/j1/tz", &st) < 0 || (st.st_mtime == seen_t && st.st_ino == seen_i)) return;
	seen_t = st.st_mtime; seen_i = st.st_ino;
	FILE *f = fopen("/etc/j1/tz", "r");
	if (!f) return;
	if (fgets(tz, sizeof tz, f)) { tz[strcspn(tz, "\n")] = 0; if (*tz) { setenv("TZ", tz, 1); tzset(); } }
	fclose(f);
}
static void render(void) {
	buf = backbuf; clip0 = 0; clip1 = SH; fill(0, 0, SW, SH, C_BG);
	clip0 = TOP; clip1 = TOP + view_h();
	int w = SW - 2 * PAD;
	for (int i = 0; i < nel; i++) {
		struct el *e = &els[i]; int y = TOP + e->y - scroll;
		if (y + e->h < clip0 || y > clip1) continue;
		switch (e->t) {
		case 'M': {
			int err = e->b && *e->b == 'e';
			rrect(PAD, y, w, e->h - 8, 12, err ? C_DNG : C_OKB);
			wrap(e->a, PAD + 12, y + 6, w - 24, 2, err ? C_BLACK : C_GRN, 1); break; }
		case 'L': {
			/* status lines get a colored dot */
			char k = e->b ? *e->b : 'n';
			if (k == 'g' || k == 'y' || k == 'r') { rrect(PAD + 2, y + 10, 14, 14, 7, tcolor(e->b)); wrap(e->a, PAD + 26, y, w - 26, 2, k == 'y' || k == 'r' ? tcolor(e->b) : C_TXT, 1); }
			else wrap(e->a, PAD, y, w, 2, tcolor(e->b), 1);
			break; }
		case 'l': wrap(e->a, PAD, y, w, 1, tcolor(e->b), 1); break;
		case 'B': {
			char st = e->c ? *e->c : 'n'; uint32_t bg = st == 'p' ? C_PRI : st == 'd' ? C_DNG : st == 'i' ? C_ITM : C_BTN;
			if (i == pressed) bg = C_DOWN;
			rrect(PAD, y, w, e->h - 8, 14, bg);
			uint32_t fg = (st == 'p' || st == 'd') && i != pressed ? C_BLACK : C_WHITE;
			int ic = icon_id(e->d), ty = y + (e->h - 8 - 32) / 2;
			if (st == 'i') {
				int tx2 = PAD + 16;
				if (ic >= 0) { icon(tx2, ty, ic, i == pressed ? C_WHITE : C_ACC); tx2 += 46; }
				textn(tx2, ty, e->b ? e->b : "", (SW - PAD - 40 - tx2) / 16, 2, fg);
				text(SW - PAD - 30, ty, ">", 2, C_MUT);
			} else {
				int n = (int)strlen(e->b ? e->b : ""), iw = ic >= 0 ? 44 : 0, mx = (w - 16 - iw) / 16; if (n > mx) n = mx;
				int x0 = PAD + (w - n * 16 - iw) / 2;
				if (ic >= 0) icon(x0, ty, ic, fg);
				textn(x0 + iw, ty, e->b ? e->b : "", n, 2, fg);
			}
			break; }
		case 'S': {
			int on = e->c && *e->c == '1';
			rrect(PAD, y, w, e->h - 8, 14, i == pressed ? C_DOWN : C_ITM);
			textn(PAD + 16, y + 16, e->b ? e->b : "", (w - 124) / 16, 2, C_WHITE);
			int sx = SW - PAD - 96, sy = y + 14;
			rrect(sx, sy, 80, 36, 18, on ? C_ACC : C_KEYS);
			rrect(on ? sx + 46 : sx + 4, sy + 4, 28, 28, 14, C_WHITE);
			break; }
		case 'D': {   /* slider: track, filled part, knob, percentage */
			int lo, hi, v = slider_val(e, &lo, &hi), x0 = PAD + 24, x1 = SW - PAD - 104;
			int kx = x0 + (v - lo) * (x1 - x0) / (hi - lo);
			char pct[8]; snprintf(pct, sizeof pct, "%d%%", v * 100 / hi);
			rrect(PAD, y, w, e->h - 8, 14, C_ITM);
			rrect(x0, y + 26, x1 - x0, 12, 6, C_KEYS);
			if (kx - x0 >= 12) rrect(x0, y + 26, kx - x0, 12, 6, C_ACC);
			rrect(kx - 16, y + 16, 32, 32, 16, C_WHITE);
			text(SW - PAD - 80, y + 16, pct, 2, C_WHITE);
			break; }
		case 'F': {
			text(PAD + 4, y + 2, e->b ? e->b : "", 1, C_MUT);
			rrect(PAD, y + 22, w, 54, 12, e->dirty ? C_YEL : i == pressed ? C_DOWN : C_KEYS);
			rrect(PAD + 2, y + 24, w - 4, 50, 10, C_FLD);
			char tmp[160]; const char *s = e->val; int n = (int)strlen(s);
			if (e->d && *e->d == 'p') { memset(tmp, '*', n); tmp[n] = 0; s = tmp; }
			if (!n) text(PAD + 10, y + 33, "(tocar para escribir)", 2, C_MUT);
			else { int mx = (w - 20) / 16; textn(PAD + 10, y + 33, n > mx ? s + n - mx : s, mx, 2, C_WHITE); }
			break; }
		case 'Q': {
			int c, r, m = qr_dims(e->a, &c, &r), qw = (c + 8) * m, x0 = (SW - qw) / 2;
			rrect(x0, y, qw, (r + 8) * m, 12, C_WHITE);
			const char *p = e->a;
			for (int row = 0; row < r; row++) {
				for (int col = 0; col < c && *p && *p != ','; col++, p++) if (*p == '1') fill(x0 + (4 + col) * m, y + (4 + row) * m, m, m, C_BLACK);
				while (*p && *p != ',') p++;
				if (*p == ',') p++;
			}
			break; }
		}
	}
	clip0 = 0; clip1 = SH;
	/* scroll hint */
	if (content_h > view_h()) { int vh = view_h(), bh = vh * vh / content_h; if (bh < 30) bh = 30; rrect(SW - 6, TOP + (vh - bh) * scroll / (content_h - vh), 4, bh, 2, C_MUT); }
	fill(0, 0, SW, TOP, C_BAR);
	fill(0, TOP - 1, SW, 1, C_LINE);
	int tx = PAD;
	if (back[0]) { if (pressed == -2) rrect(6, 6, 60, TOP - 12, 12, C_DOWN); text(20, 14, "<", 2, C_ACC); tx = 76; }
	/* top right: battery and clock */
	char clock[16], bat[8] = "", st[16] = ""; time_t t = time(NULL);
	tz_follow();
	strftime(clock, sizeof clock, "%H:%M", localtime(&t));
	FILE *in = fopen("/sys/class/power_supply/battery/capacity", "r");
	if (in) { if (fgets(bat, sizeof bat, in)) bat[strcspn(bat, "\n")] = 0; fclose(in); }
	if ((in = fopen("/sys/class/power_supply/battery/status", "r"))) { if (!fgets(st, sizeof st, in)) st[0] = 0; fclose(in); }
	int chg = !strncmp(st, "Charging", 8) || !strncmp(st, "Full", 4), pct = atoi(bat);
	/* clock on top, battery under it; the title keeps the rest */
	int bx = SW - 8 - 92;
	textn(tx, 14, title, (bx - tx - 8) / 16, 2, C_WHITE);
	if (bat[0]) {
		char b[8]; snprintf(b, sizeof b, "%d%%", pct);
		uint32_t bc = pct <= 15 && !chg ? C_RED : chg ? C_GRN : C_MUT;
		rrect(bx, 36, 21, 16, 4, bc); rrect(bx + 2, 38, 17, 12, 3, C_BAR); if (pct > 0) rrect(bx + 3, 39, (pct * 15 + 99) / 100, 10, 2, bc); rrect(bx + 21, 40, 3, 8, 1, bc);
		textwh(bx + 26, 31, b, 13, 26, bc); if (chg) textwh(bx + 26 + 13 * (int)strlen(b), 31, "+", 13, 26, C_GRN);
	}
	textwh(bx + 92 - 65, 3, clock, 13, 26, C_MUT);  /* same size as the battery */
	if (busy) { rrect(60, SH / 2 - 50, SW - 120, 100, 18, C_YEL); text(SW / 2 - 5 * 16, SH / 2 - 16, "Un momento", 2, C_BLACK); }
	if (kb_open) draw_keyboard();
	present();
}

/* ---- web.py link ---- */
static int busy_pending, debug;
static int request(const char *q) {
	int s = socket(AF_UNIX, SOCK_STREAM, 0); if (s < 0) return -1;
	struct sockaddr_un a = {.sun_family = AF_UNIX}; snprintf(a.sun_path, sizeof a.sun_path, "%s", SOCK);
	struct timeval tv = {30, 0}; setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv); setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
	if (connect(s, (struct sockaddr *)&a, sizeof a) < 0) { close(s); return -1; }
	size_t len = strlen(q), off = 0; ssize_t r;
	while (off < len && (r = write(s, q + off, len - off)) > 0) off += r;
	shutdown(s, SHUT_WR);
	/* "Un momento" only when the answer is slow (scan, reboot...) */
	struct pollfd pw = {s, POLLIN, 0};
	if (busy_pending && poll(&pw, 1, 150) == 0) { busy = 1; render(); }
	size_t n = 0;
	while (n < sizeof resp - 1 && (r = read(s, resp + n, sizeof resp - 1 - n)) > 0) n += r;
	close(s); resp[n] = 0;
	return n ? 0 : -1;
}
static void enc(char *o, size_t cap, const char *s) {
	size_t n = strlen(o);
	for (; *s && n + 4 < cap; s++) {
		unsigned char c = (unsigned char)*s;
		if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.') o[n++] = c;
		else n += sprintf(o + n, "%%%02X", c);
	}
	o[n] = 0;
}
/* local screen when web.py does not answer */
static void fallback(void) {
	/* the screen starts before web.py: during boot this is normal, not an error */
	double up = 0; FILE *u = fopen("/proc/uptime", "r");
	if (u) { if (fscanf(u, "%lf", &up) != 1) up = 0; fclose(u); }
	int n = up < 120
		? snprintf(resp, sizeof resp, "T\thome\tJ1 · Iniciando\t\nR\t1\nM\tIniciando servicios...\to\n")
		: snprintf(resp, sizeof resp, "T\thome\tJ1 (sin servicio web)\t\nR\t3\nM\tEl servicio web no responde; reintentando\te\nB\tnav:home\tReintentar\tp\n");
	FILE *in = fopen("/run/appliance.log", "r");
	static char lines[40][200]; int count = 0; char b[200];
	if (in) { while (fgets(b, sizeof b, in)) { b[strcspn(b, "\r\n")] = 0; for (char *p = b; *p; p++) if (*p == '\t') *p = ' '; snprintf(lines[count % 40], 200, "%s", b); count++; } fclose(in); }
	for (int i = count - 1; i >= 0 && i >= count - 40 && n < (int)sizeof resp - 220; i--) n += snprintf(resp + n, sizeof resp - n, "l\t%s\tm\n", lines[i % 40]);
}
static double last_req;
static void poke(void);
static int drain_pending;
/* reply carries an error message (M line ending in kind e) */
static int has_error(void) {
	char *p = strstr(resp, "\nM\t"); if (!p) return 0;
	char *e = strchr(p + 1, '\n'); if (!e) e = p + strlen(p);
	return e - p > 3 && e[-1] == 'e' && e[-2] == '\t';
}
static void send_action(const char *action, int refresh) {
	static char q[16384]; q[0] = 0;
	strcat(q, "a="); enc(q, sizeof q, action); strcat(q, "&s="); enc(q, sizeof q, screen_id);
	if (!refresh) for (int i = 0; i < nel; i++) if (els[i].t == 'F') { strcat(q, "&f_"); enc(q, sizeof q, els[i].a); strcat(q, "="); enc(q, sizeof q, els[i].val); }
	double t0 = now();
	char act[48]; snprintf(act, sizeof act, "%s", action);  /* action may point into resp */
	busy_pending = !refresh;
	int ok = request(q) == 0;
	busy = busy_pending = 0;
	double t1 = now(); int bytes = (int)strlen(resp);
	if (!ok) fallback();
	/* an error message keeps what the user typed */
	parse(refresh || (ok && has_error()));
	if (!refresh) poke();
	last_req = now(); pressed = -1;
	if (!refresh) drain_pending = 1;
	if (shown) render();
	if (debug && (!refresh || t1 - t0 > 1)) fprintf(stderr, "%.3f %s %s: peticion %.1f ms, pintar %.1f ms, %d bytes\n", now(), refresh ? "refresco" : "accion", act, (t1 - t0) * 1000, (now() - t1) * 1000, bytes);
}

/* ---- backlight ---- */
static double deadline;
static void status(void) { FILE *o = fopen("/run/display.status", "w"); if (o) { fprintf(o, "visible=%d\nwake_events=%d\n", shown, wakes); fclose(o); } }
static double dim_until;
static void set_bright(void) { char b[8]; snprintf(b, sizeof b, "%d", bright); value("/sys/class/backlight/panel/brightness", b); }
static void light(int on) {
	if (debug) fprintf(stderr, "%.3f pantalla %s\n", now(), on ? "encendida" : "apagada");
	if (on) set_bright(); else value("/sys/class/backlight/panel/brightness", "0");
	shown = on; dimmed = 0; status();
	if (!on) {  /* nothing private stays in video memory */
		kb_open = 0; memset(mem, 0, f.smem_len);
	}
}
static double last_touch;
/* idle_s from web.py: 0 = always on; the keyboard gets at least 2 min.
 * The chosen time is when the screen goes off; its last third (10 s at most)
 * it is dimmed but still usable. deadline = start of the dimmed part. */
static int idle_eff(void) { return kb_open && idle_s < 120 ? 120 : idle_s; }
static int dim_len(void) { int d = idle_eff() / 3; return d > 10 ? 10 : d < 3 ? 3 : d; }
static void set_deadline(void) { deadline = idle_s ? last_touch + idle_eff() - dim_len() : 1e12; }
static void poke(void) {
	if (dimmed) { set_bright(); dimmed = 0; }
	last_touch = now();
	set_deadline();
}
/* nobody looking: status every 30 s at most */
static int refresh_every(void) { return refresh_s > 0 && refresh_s < 30 && now() - last_touch > 60 ? 30 : refresh_s; }
/* back where it was, except screens that show keys (QR) */
static void wake(void) {
	char nav[160]; snprintf(nav, sizeof nav, "nav:%s", strncmp(screen_id, "qr", 2) && strncmp(screen_id, "wifiqr", 6) && strcmp(screen_id, "power") ? screen_id : "home");
	wakes++; light(1); poke(); send_action(nav, 0);
}

/* ---- input ---- */
static int evkey = -1, evtouch = -1;
static int t_slot, t_id = -1, t_x, t_y, t_down, t_x0, t_y0, t_scroll0, dragging, ignore;
static double last_drag_render;
static int hit(int x, int y) {
	if (y < TOP) return (back[0] && x < 80) ? -2 : -1;
	if (y >= TOP + view_h()) return -1;
	int cy = y - TOP + scroll;
	for (int i = 0; i < nel; i++) {
		struct el *e = &els[i];
		if ((e->t == 'B' || e->t == 'S' || e->t == 'F' || e->t == 'D') && cy >= e->y && cy < e->y + e->h - 6) return i;
	}
	return -1;
}
static int kb_hit(int x, int y) {
	struct key k[64]; int n = keys(k);
	for (int i = 0; i < n; i++) if (x >= k[i].x && x < k[i].x + k[i].w && y >= k[i].y && y < k[i].y + k[i].h) return i;
	return -1;
}
static void kb_press(int i) {
	struct key k[64]; int n = keys(k); if (i < 0 || i >= n) return;
	int c = k[i].code, len = (int)strlen(kb_buf);
	if (c == K_OK) { snprintf(kb_el->val, sizeof kb_el->val, "%s", kb_buf); kb_el->dirty = 1; kb_open = 0; clamp_scroll(); }
	else if (c == K_CANCEL) { kb_open = 0; clamp_scroll(); }
	else if (c == K_SHOW) kb_show = !kb_show;
	else if (c == K_BS) { if (len) kb_buf[len - 1] = 0; }
	else if (c == K_SHIFT) kb_shift = !kb_shift;
	else if (c == K_LAYER) { kb_layer = kb_layer ? 0 : 1; kb_shift = 0; }
	else if (c == K_LAYER2) kb_layer = kb_layer == 1 ? 2 : 1;
	else if (len < (int)sizeof kb_buf - 1) {
		kb_buf[len] = (char)(c == K_SPACE ? ' ' : c); kb_buf[len + 1] = 0;
		if (kb_layer == 0) kb_shift = 0;
	}
	poke();
}
static void open_kb(struct el *e) {
	kb_el = e; kb_open = 1; kb_show = 0; kb_shift = 0;
	kb_layer = (e->d && (*e->d == 'n' || *e->d == 'i')) ? 1 : 0;
	snprintf(kb_buf, sizeof kb_buf, "%s", e->val);
	/* keep the field visible above the keyboard */
	int top = e->y, bottom = e->y + e->h;
	if (bottom - scroll > view_h()) scroll = bottom - view_h();
	if (top < scroll) scroll = top;
	poke();
}
/* tap = short contact that barely moves; anything else on a scrollable view scrolls */
#define TAP_MOVE 60
#define TAP_TIME 0.35
static int t_el, t_maxd;
static double t_time0;
static int sliding(void) { return t_el >= 0 && t_el < nel && els[t_el].t == 'D'; }
/* the finger moves the slider; brightness follows it live, web.py saves it on release */
static void slide(int x) {
	struct el *e = &els[t_el]; int lo, hi, x0 = PAD + 24, x1 = SW - PAD - 104;
	slider_val(e, &lo, &hi);
	int v = lo + (x - x0) * (hi - lo) / (x1 - x0); if (v < lo) v = lo; if (v > hi) v = hi;
	snprintf(e->val, sizeof e->val, "%d", v);
	if (!strcmp(e->a, "disp.bright") && v != bright) { bright = v; set_bright(); }
	if (now() - last_drag_render > 0.04) { render(); last_drag_render = now(); }
}
static void touch_down(int x, int y) {
	if (debug) fprintf(stderr, "%.3f dedo %d,%d%s\n", now(), x, y, shown ? "" : " (despierta)");
	if (!shown) { ignore = 1; wake(); return; }
	poke(); t_x0 = x; t_y0 = y; t_scroll0 = scroll; dragging = 0; t_maxd = 0; t_time0 = now();
	if (kb_open && y >= KBY - PVH) { kb_down = kb_hit(x, y); pressed = t_el = -1; }
	else pressed = t_el = hit(x, y);
	if (sliding()) { pressed = -1; last_drag_render = 0; slide(x); return; }
	render();
}
static void touch_move(int x, int y) {
	int d = abs(y - t_y0) > abs(x - t_x0) ? abs(y - t_y0) : abs(x - t_x0);
	if (d > t_maxd) t_maxd = d;
	if (kb_open && t_y0 >= KBY - PVH) return;
	if (sliding()) { slide(x); return; }
	if (!dragging && abs(y - t_y0) > 32 && content_h > view_h()) { dragging = 1; pressed = -1; }
	if (dragging) {
		scroll = t_scroll0 - (y - t_y0); clamp_scroll();
		if (now() - last_drag_render > 0.04) { render(); last_drag_render = now(); }
	}
}
static void touch_up(int x, int y) {
	double dur = now() - t_time0;
	if (ignore) { ignore = 0; if (debug) fprintf(stderr, "%.3f ignorado (despertar o pendiente)\n", now()); return; }
	if (kb_open && t_y0 >= KBY - PVH) {
		if (kb_down >= 0) kb_press(kb_down);
		kb_down = -1; render(); return;
	}
	if (sliding()) {
		char a[200]; struct el *e = &els[t_el]; snprintf(a, sizeof a, "%s:%s", e->a, e->val);
		t_el = -1; kb_open = 0; send_action(a, 0); return;
	}
	int tap = t_maxd < TAP_MOVE && dur < TAP_TIME;
	if (dragging && !tap) {
		dragging = 0; render();
		if (debug) fprintf(stderr, "%.3f arrastre %d px %.0f ms\n", now(), t_maxd, dur * 1000);
		return;
	}
	if (dragging) { scroll = t_scroll0; dragging = 0; }   /* a wobbly tap: undo the small scroll */
	int i = t_el; pressed = -1;
	if (debug) fprintf(stderr, "%.3f toque %d,%d -> %d,%d (%d px %.0f ms) elemento %d\n", now(), t_x0, t_y0, x, y, t_maxd, dur * 1000, i);
	if (i == -2) { if (kb_open) kb_open = 0; send_action(back, 0); return; }
	if (i < 0) { if (kb_open) { kb_open = 0; } render(); return; }
	struct el *e = &els[i];
	if (e->t == 'F') { open_kb(e); render(); return; }
	kb_open = 0;
	send_action(e->a, 0);
}
#define KEY_RECENTS 254   /* Samsung touch key */
/* Power: a short press turns the screen on/off, holding it opens the power menu */
#define PWR_LONG 1.5
static double pwr_at;      /* when Power went down, 0 = up */
static int pwr_woke;       /* that press turned the screen on: its release keeps it on */
static void power_key(int value) {
	if (value == 1) {
		pwr_at = now(); pwr_woke = !shown;
		if (!shown) wake();
	} else if (value == 0 && pwr_at) {
		pwr_at = 0;
		if (!pwr_woke && shown) light(0);
	}
}
/* called from the main loop once Power has been held PWR_LONG s */
static void power_held(void) {
	unsigned char keys[KEY_MAX / 8 + 1] = {0};
	pwr_at = 0;
	/* a release lost while draining input is not a long press */
	if (ioctl(evkey, EVIOCGKEY(sizeof keys), keys) >= 0 && !(keys[KEY_POWER / 8] & (1 << (KEY_POWER % 8)))) return;
	pwr_woke = 1;   /* the release must not turn the menu off */
	if (!shown) light(1);
	kb_open = 0; poke(); send_action("nav:power", 0);
}
/* hardware keys: Home, Back, Recents = resources, volume scrolls */
static void key(int c) {
	if (debug) fprintf(stderr, "%.3f tecla %d\n", now(), c);
	if (!shown) { wake(); return; }
	poke();
	if (c == KEY_VOLUMEUP) { scroll -= 300; clamp_scroll(); render(); }
	else if (c == KEY_VOLUMEDOWN) { scroll += 300; clamp_scroll(); render(); }
	else if (c == KEY_HOME) { kb_open = 0; send_action("nav:home", 0); }
	else if (c == KEY_BACK) { if (kb_open) { kb_open = 0; render(); } else if (back[0]) send_action(back, 0); }
	else if (c == KEY_RECENTS) { kb_open = 0; send_action("nav:res", 0); }
}
static void touch_events(int act) {
	struct input_event ev[64]; ssize_t n;
	while ((n = read(evtouch, ev, sizeof ev)) > 0)
		for (size_t i = 0; i < (size_t)n / sizeof ev[0]; i++) {
			struct input_event *e = &ev[i];
			if (e->type == EV_ABS) {
				if (e->code == ABS_MT_SLOT) t_slot = e->value;
				else if (t_slot == 0 && e->code == ABS_MT_TRACKING_ID) t_id = e->value;
				else if (t_slot == 0 && e->code == ABS_MT_POSITION_X) t_x = e->value;
				else if (t_slot == 0 && e->code == ABS_MT_POSITION_Y) t_y = e->value;
			} else if (e->type == EV_KEY && e->value == 1) {
				if (act && e->code != KEY_POWER) key(e->code);   /* capacitive Back / Recents */
			} else if (e->type == EV_SYN && e->code == SYN_REPORT) {
				int down = t_id >= 0;
				if (!act) { ignore = down; t_down = down; continue; }
				if (down && !t_down) touch_down(t_x, t_y);
				else if (down) touch_move(t_x, t_y);
				else if (t_down) touch_up(t_x, t_y);
				t_down = down;
			}
		}
}
static void key_events(int act) {
	struct input_event ev[16]; ssize_t n;
	while ((n = read(evkey, ev, sizeof ev)) > 0)
		for (size_t i = 0; i < (size_t)n / sizeof ev[0]; i++) {
			if (!act || ev[i].type != EV_KEY) continue;
			if (ev[i].code == KEY_POWER) power_key(ev[i].value);
			else if (ev[i].value == 1) key(ev[i].code);
		}
}
static void drain_input(void) { touch_events(0); key_events(0); }

static double next_clock;
static void set_next_clock(void) { next_clock = now() + 60 - time(NULL) % 60 + 0.05; }

/* event numbers change between boots: find devices by name */
static const char *find_input(const char *name, char *path) {
	snprintf(path, 64, "/dev/input/none");
	for (int i = 0; i < 16; i++) {
		char p[80], n[64] = ""; snprintf(p, sizeof p, "/sys/class/input/event%d/device/name", i);
		FILE *in = fopen(p, "r"); if (!in) continue;
		if (fgets(n, sizeof n, in)) n[strcspn(n, "\n")] = 0;
		fclose(in);
		if (!strcmp(n, name)) { snprintf(path, 64, "/dev/input/event%d", i); break; }
	}
	return path;
}

int main(void) {
	setpriority(PRIO_PROCESS, 0, 10);  /* WireGuard first */
	fb = open("/dev/fb0", O_RDWR); if (fb < 0) { perror("fb0"); return 1; }
	if (ioctl(fb, FBIOGET_VSCREENINFO, &v) || ioctl(fb, FBIOGET_FSCREENINFO, &f)) { perror("framebuffer info"); return 1; }
	if (v.bits_per_pixel != 32 || !v.xres || !v.yres) { fprintf(stderr, "unsupported framebuffer format\n"); return 1; }
	SW = (int)v.xres; SH = (int)v.yres; stride = (int)(f.line_length / 4);
	printf("framebuffer %dx%d virtual %ux%u\n", SW, SH, v.xres_virtual, v.yres_virtual); fflush(stdout);
	mem = mmap(NULL, f.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fb, 0); if (mem == MAP_FAILED) { perror("mmap"); return 1; }
	backbuf = malloc((size_t)SH * f.line_length); if (!backbuf) { perror("malloc"); return 1; }
	show_page0();
	C_BG = color(11, 20, 32); C_BAR = color(20, 33, 51); C_TXT = color(220, 232, 240); C_MUT = color(140, 165, 190);
	C_GRN = color(80, 230, 160); C_YEL = color(240, 200, 90); C_RED = color(240, 110, 110); C_BTN = color(48, 65, 88);
	/* accent: blue (icons, switches, primary buttons) */
	C_ACC = color(70, 165, 245);
	C_PRI = color(140, 200, 250); C_DNG = color(244, 180, 180); C_ITM = color(28, 44, 66); C_FLD = color(6, 12, 20);
	C_KEY = color(60, 78, 102); C_KEYS = color(38, 52, 72); C_DOWN = color(90, 130, 170); C_WHITE = color(240, 246, 250); C_BLACK = color(10, 20, 16);
	C_OKB = color(24, 52, 46); C_LINE = color(40, 58, 82);
	font_init(); icons_init();
	/* J1_UI_KEYS / J1_UI_TOUCH / J1_UI_DEBUG: other input devices and timings (testing) */
	char kdev[64], tdev[64];
	evkey = open(getenv("J1_UI_KEYS") ? getenv("J1_UI_KEYS") : find_input("sci-keypad", kdev), O_RDONLY | O_NONBLOCK);
	evtouch = open(getenv("J1_UI_TOUCH") ? getenv("J1_UI_TOUCH") : find_input("sec_touchscreen", tdev), O_RDONLY | O_NONBLOCK);
	/* no touch (charger boot: the Samsung driver skips it): keys still work */
	if (evtouch < 0) fprintf(stderr, "sin tactil (%s); solo botones\n", tdev);
	debug = getenv("J1_UI_DEBUG") != NULL;
	if (evkey < 0) { perror("teclas"); return 1; }
	struct pollfd p[2] = {{evkey, POLLIN, 0}, {evtouch, POLLIN, 0}};
	light(1); deadline = now() + 30; last_touch = now();
	/* J1_UI_START=nav:vpn J1_UI_KB=1: start on a screen / keyboard (testing) */
	send_action(getenv("J1_UI_START") ? getenv("J1_UI_START") : "nav:home", 1);
	if (!idle_s) poke();
	if (getenv("J1_UI_KB")) for (int i = 0; i < nel; i++) if (els[i].t == 'F') { open_kb(&els[i]); render(); break; }
	set_next_clock();
	for (;;) {
		int timeout = -1;
		if (shown) {
			double t = dimmed ? dim_until : deadline;
			if (refresh_every() > 0 && !kb_open && last_req + refresh_every() < t) t = last_req + refresh_every();
			if (next_clock < t) t = next_clock;
			timeout = t - now() > 3600 ? 3600000 : (int)((t - now()) * 1000) + 5; if (timeout < 0) timeout = 0;
		}
		if (pwr_at) { int w = (int)((pwr_at + PWR_LONG - now()) * 1000) + 5; if (w < 0) w = 0; if (timeout < 0 || w < timeout) timeout = w; }
		poll(p, 2, timeout);
		if (p[0].revents & POLLIN) key_events(1);
		if (p[1].revents & POLLIN) touch_events(1);
		if (pwr_at && now() >= pwr_at + PWR_LONG) power_held();
		/* events that arrived while web.py was busy belong to old taps */
		if (drain_pending) { drain_pending = 0; drain_input(); }
		if (!shown) continue;
		/* clock and battery in the title bar */
		if (now() >= next_clock) { render(); set_next_clock(); }
		if (!dimmed && now() >= deadline && !t_down) {
			value("/sys/class/backlight/panel/brightness", "12"); dimmed = 1; dim_until = now() + dim_len();
			if (debug) fprintf(stderr, "%.3f atenuada\n", now());
		}
		if (dimmed && now() >= dim_until && !t_down) { light(0); continue; }
		if (refresh_every() > 0 && !kb_open && !t_down && now() >= last_req + refresh_every()) { char nav[160]; snprintf(nav, sizeof nav, "nav:%s", screen_id); send_action(nav, 1); }
	}
}
