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
#include "j1-ui-font.h"

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
static uint32_t C_ACC, C_OKB, C_LINE, C_BG, C_BAR, C_TXT, C_MUT, C_GRN, C_YEL, C_RED, C_BTN, C_PRI, C_DNG, C_DNGB, C_ITM, C_FLD, C_KEY, C_KEYS, C_DOWN, C_WHITE, C_BLACK;

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
	if (w <= 0) return;
	for (int j = 0; j < h; j++) {
		uint32_t *p = buf + (size_t)(y + j) * stride + x;
		if (!c) memset(p, 0, (size_t)w * 4); else for (int i = 0; i < w; i++) p[i] = c;   /* black background: memset */
	}
}
static void put(int x, int y, uint32_t c) {
	if (x >= 0 && x < SW && y >= clip0 && y < clip1) buf[(size_t)y * stride + x] = c;
}
/* mix two colors, a = 0..256 parts of c1 (antialiased corners) */
/* R and B (bytes 0 and 2) blended together, then G: 2 multiplies per color pair */
static uint32_t mix(uint32_t c1, uint32_t c2, int a) {
	uint32_t b = 256 - a;
	uint32_t rb = (((c1 & 0xff00ffu) * a + (c2 & 0xff00ffu) * b) >> 8) & 0xff00ffu;
	uint32_t g = (((c1 & 0xff00u) * a + (c2 & 0xff00u) * b) >> 8) & 0xff00u;
	return rb | g | (c1 & 0xff000000u);
}
#if R_OFF + G_OFF + B_OFF != 24 || G_OFF != 8
#error mix() expects R, G, B in the three low bytes
#endif
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
/* ---- text and icons: antialiased masks from j1-ui-font.h (gen-font.py) ---- */
/* c over the pixels with coverage 0-255; clipped once per glyph, not per pixel */
static void mask(int x, int y, int w, int h, const uint8_t *a, uint32_t c) {
	int i0 = x < 0 ? -x : 0, i1 = x + w > SW ? SW - x : w;
	int j0 = y < clip0 ? clip0 - y : 0, j1 = y + h > clip1 ? clip1 - y : h;
	for (int j = j0; j < j1; j++) {
		const uint8_t *r = a + (size_t)j * w; uint32_t *p = buf + (size_t)(y + j) * stride + x;
		for (int i = i0; i < i1; i++) { int v = r[i]; if (v) p[i] = v == 255 ? c : mix(c, p[i], v + (v >> 7)); }
	}
}
static int fwidth(const struct font *f, const char *s, int n) {
	int w = 0; for (int i = 0; i < n && s[i]; i++) w += f->g[(unsigned char)s[i]].adv; return w;
}
/* base = baseline; returns the x after the text */
static int fdraw(const struct font *f, int x, int base, const char *s, int n, uint32_t c) {
	for (int i = 0; i < n && s[i]; i++) {
		const struct glyph *g = &f->g[(unsigned char)s[i]];
		if (g->w) mask(x + g->ox, base + g->oy, g->w, g->h, f->a + g->off, c);
		x += g->adv;
	}
	return x;
}
/* at most maxw px: what does not fit is cut with "..." */
static void fdraw_fit(const struct font *f, int x, int base, const char *s, int maxw, uint32_t c) {
	int n = (int)strlen(s);
	if (fwidth(f, s, n) > maxw) {
		int dots = fwidth(f, "...", 3);
		while (n > 0 && fwidth(f, s, n) + dots > maxw) n--;
		fdraw(f, fdraw(f, x, base, s, n, c), base, "...", 3, c); return;
	}
	fdraw(f, x, base, s, n, c);
}
/* size 2 = normal text in a 32 px line, 1 = small print in a 16 px line; y = top of the line */
static const struct font *FONT(int sc) { return sc > 1 ? &f_md : &f_sm; }
static int BASE(int sc) { return sc > 1 ? 24 : 14; }
static int LINE(int sc) { return sc > 1 ? 32 : 22; }
static int tw(const char *s, int sc) { return fwidth(FONT(sc), s, (int)strlen(s)); }
static void text(int x, int y, const char *s, int sc, uint32_t c) { fdraw(FONT(sc), x, y + BASE(sc), s, (int)strlen(s), c); }
static void text_fit(int x, int y, const char *s, int maxw, int sc, uint32_t c) { fdraw_fit(FONT(sc), x, y + BASE(sc), s, maxw, c); }
static void text_mid(int cx, int y, const char *s, int sc, uint32_t c) { text(cx - tw(s, sc) / 2, y, s, sc, c); }
/* word wrap in w px (center: each line centered on x + w / 2); returns the height used */
static int wrap2(const char *s, int x, int y, int w, int sc, uint32_t c, int draw, int center) {
	const struct font *f = FONT(sc); int lines = 0;
	while (*s) {
		int n = (int)strlen(s), take, sp = -1, used = 0;
		for (take = 0; take < n; take++) {
			int a = f->g[(unsigned char)s[take]].adv;
			if (take && used + a > w) break;
			if (s[take] == ' ') sp = take;
			used += a;
		}
		if (take < n && sp > 0) take = sp;
		if (draw) { int lw = fwidth(f, s, take); fdraw(f, center ? x + (w - lw) / 2 : x, y + lines * LINE(sc) + BASE(sc), s, take, c); }
		lines++; s += take; while (*s == ' ') s++;
	}
	return (lines ? lines : 1) * LINE(sc);
}
static int wrap(const char *s, int x, int y, int w, int sc, uint32_t c, int draw) { return wrap2(s, x, y, w, sc, c, draw, 0); }

/* icons: Material Icons at 30 px (lists) and 46 px (home tiles) */
#define NICONS (int)(sizeof ICON_DEFS / sizeof ICON_DEFS[0])
static const int ICON_PX[] = ICON_SIZES;
static int icon_id(const char *name) {
	if (!name || !*name) return -1;
	for (int n = 0; n < NICONS; n++) if (!strcmp(ICON_DEFS[n].name, name)) return n;
	return -1;
}
static void icon_sz(int x, int y, int n, int big, uint32_t c) { int s = ICON_PX[big]; mask(x, y, s, s, ICON_DEFS[n].a[big], c); }
static void icon(int x, int y, int n, uint32_t c) { icon_sz(x + 1, y + 1, n, 0, c); }
/* each section has its own color, as on the home screen */
static uint32_t icon_color(const char *name);

/* ---- screen model ---- */
/* a-d point into resp, which the next request overwrites: a field keeps its own name in key */
struct el { char t, *a, *b, *c, *d; int y, h, dirty, col, pg; char key[64], val[160]; };
/* field kinds p (password) and q (numeric code) are shown as asterisks */
static int secret(const struct el *e) { return e->d && (*e->d == 'p' || *e->d == 'q'); }
/* home tiles (C): two per row */
#define TGAP 12
#define TILE_H 136      /* tallest; shorter when more status lines are above */
#define TILE_MIN 104
static int tile_h = TILE_H;
static int tile_w(void) { return (SW - 2 * PAD - TGAP) / 2; }
/* the tiles go in pages swiped sideways; page_dx = finger offset while dragging */
#define DOTS_H 26
static int page, npages = 1, page_dx, tiles_y, tiles_h;
static int tile_x(const struct el *e) { return PAD + e->col * (tile_w() + TGAP) + (e->pg - page) * SW + page_dx; }
static struct el els[MAXEL];
static int nel, content_h, scroll, refresh_s, idle_s = 60;
static void set_deadline(void), set_bright(void), poke(void);
static int dimmed, bright = 143;   /* backlight 0-255 from web.py */
static char resp[131072], screen_id[128] = "home", back[128], title[128];
static int busy, shown = 1, wakes;
/* lock screen (K line from web.py): set when the screen goes off, a swipe opens it */
static int lock_on, locked, lock_drag, lock_x;
/* optional code (K line, 3rd field): after the swipe a keypad asks for it;
 * web.py checks it (the J1 keeps only a hash) and limits the attempts */
static int lock_pin, lock_blocked, lock_stage, pin_down = -1;   /* blocked: too many misses, only the web panel opens it */
static char pin_buf[9], pin_msg[80];

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
/* height of an element (tiles are laid out apart) */
static int el_h(struct el *e, int w) {
	switch (e->t) {
	case 'M': return wrap(e->a, 0, 0, w - 16, 2, 0, 0) + 20;
	case 'L': { char k = e->b ? *e->b : 'n'; int dot = k == 'g' || k == 'y' || k == 'r';   /* same width as when drawn */
		return wrap(e->a, 0, 0, dot ? w - 26 : w, 2, 0, 0) + 6; }
	case 'l': return wrap(e->a, 0, 0, w, 1, 0, 0) + 4;
	case 'P': return 26;
	case 'B': return (e->c && *e->c == 'i') ? 66 : 72;
	case 'S': case 'D': return 72;
	case 'F': return 22 + 54 + 12;
	case 'G': return 18;
	case 'Q': { int c, r, m = qr_dims(e->a, &c, &r); return (r + 8) * m + 12; }
	}
	return 0;
}
static void layout(void) {
	int y = 8, w = SW - 2 * PAD;
	npages = 1; tiles_h = 0;
	for (int i = 0; i < nel; i++) {
		struct el *e = &els[i]; e->y = y; e->h = 0; e->col = e->pg = 0;
		if (e->t == 'C') {   /* a run of tiles: the home screen never scrolls, so they fit */
			int n = 0; while (i + n < nel && els[i + n].t == 'C') n++;
			/* what comes after the tiles (footer) must fit too; 3 rows, shorter tiles if needed */
			int after = 0; for (int k = i + n; k < nel; k++) after += el_h(&els[k], w);
			int avail = SH - TOP - y - after - 24 - DOTS_H, rows = 3;
			tile_h = avail / 3 - TGAP; if (tile_h > TILE_H) tile_h = TILE_H;
			if (tile_h < TILE_MIN) { tile_h = TILE_MIN; rows = avail / (tile_h + TGAP); if (rows < 1) rows = 1; }
			npages = (n + 2 * rows - 1) / (2 * rows);
			if (npages == 1) rows = (n + 1) / 2;
			for (int k = 0; k < n; k++) {
				struct el *t = &els[i + k];
				t->pg = k / (2 * rows); t->col = k % 2; t->y = y + (k % (2 * rows)) / 2 * (tile_h + TGAP); t->h = tile_h + TGAP;
			}
			tiles_y = y; tiles_h = rows * (tile_h + TGAP);
			y += tiles_h + (npages > 1 ? DOTS_H : 0); i += n - 1;
			if (page >= npages) page = npages - 1;
			continue;
		}
		e->h = el_h(e, w);
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
		snprintf(kn[nk], 64, "%s", els[i].key); snprintf(kv[nk], 160, "%s", els[i].val); nk++;
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
			if (o != idle_s) { int was = idle_s; idle_s = o; if (!was) poke(); else set_deadline(); }
		}
		else if (fld[0][0] == 'V') {   /* brightness too */
			int v = fld[1] ? atoi(fld[1]) : 143;
			if (v < 13 || v > 255) v = 143;
			if (v != bright) { bright = v; if (shown && !dimmed) set_bright(); }
		}
		else if (fld[0][0] == 'K') { lock_on = fld[1] && *fld[1] == '1'; lock_pin = lock_on && fld[2] && *fld[2] == '1'; lock_blocked = lock_pin && fld[3] && *fld[3] == '1'; if (!lock_on) locked = 0; }
		else if (fld[0][0] && (fld[1] || fld[0][0] == 'G')) {
			struct el *e = &els[nel++]; memset(e, 0, sizeof *e);
			e->t = fld[0][0]; e->a = fld[1] ? fld[1] : (char *)""; e->b = fld[2]; e->c = fld[3]; e->d = fld[4];
			if (e->t == 'F') { snprintf(e->val, sizeof e->val, "%s", e->c ? e->c : ""); snprintf(e->key, sizeof e->key, "%s", e->a); }
			if (e->t == 'D') snprintf(e->val, sizeof e->val, "%s", e->b ? e->b : "0");
		}
		if (!nl) break;
		p = nl + 1;
	}
	int same = !strcmp(old, screen_id);
	if (!same) scroll = page = page_dx = 0;
	if (same && keep_dirty)
		for (int i = 0; i < nel; i++) if (els[i].t == 'F')
			for (int k = 0; k < nk; k++) if (!strcmp(kn[k], els[i].a)) { snprintf(els[i].val, sizeof els[i].val, "%.159s", kv[k]); els[i].dirty = 1; }
	layout(); clamp_scroll();
}

/* ---- keyboard ---- */
static int kb_open, kb_layer, kb_shift, kb_show, kb_was_dirty; static struct el *kb_el; static char kb_buf[160], kb_orig[160];
static const char *KB[3][3] = {
	{"qwertyuiop", "asdfghjkl\xa4", "zxcvbnm"},
	{"1234567890", "@#$%&*-+()", "!\"':;/?"},
	{"[]{}<>^~`|", "\\_=\xa8\xad\xa0\x82\xa1\xa2\xa3", "\xa5\x81\xf8\xfa\xa6\xa7\x9c"},
};
#define KH 70
#define KBY (SH - 4 * KH)
#define PVH 52          /* bar above the keys: field name, ver, X */
static int view_h(void) { return (kb_open ? KBY - PVH : SH) - TOP; }

struct key { int x, y, w, h; int code; const char *label; };
enum { K_SHIFT = 256, K_BS, K_LAYER, K_LAYER2, K_OK, K_SPACE, K_CANCEL, K_SHOW };
/* code fields (kind q): only digits, a phone-style 3 x 4 pad */
static int digits_only(void) { return kb_el && kb_el->d && *kb_el->d == 'q'; }
static int keys(struct key *k) {
	int n = 0, y = KBY;
	static char lab[3][10][2];
	if (digits_only()) {
		static const char *pad[12] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "\x1b", "0", "OK"};
		for (int i = 0; i < 12; i++) {
			int c = i == 9 ? K_BS : i == 11 ? K_OK : pad[i][0], x = i % 3 * (SW / 3);
			k[n++] = (struct key){x, KBY + i / 3 * KH, i % 3 == 2 ? SW - x : SW / 3, KH, c, pad[i]};
		}
		k[n++] = (struct key){SW - 64, KBY - PVH, 64, PVH, K_CANCEL, "X"};
		k[n++] = (struct key){SW - 136, KBY - PVH, 72, PVH, K_SHOW, kb_show ? "ocul" : "ver"};
		return n;
	}
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
	if (kb_el && secret(kb_el)) k[n++] = (struct key){SW - 136, KBY - PVH, 72, PVH, K_SHOW, kb_show ? "ocul" : "ver"};
	return n;
}
static int kb_down = -1;
static void draw_keyboard(void) {
	struct key k[64]; int n = keys(k);
	clip0 = 0; clip1 = SH;
	fill(0, KBY - PVH, SW, SH - KBY + PVH, C_BAR);
	fill(0, KBY - PVH, SW, 1, C_LINE);
	/* the text goes into the field itself; this bar only says which one */
	text_fit(PAD, KBY - PVH + 16, kb_el && kb_el->b ? kb_el->b : "", SW - 150 - PAD, 1, C_MUT);
	for (int i = 0; i < n; i++) {
		if (k[i].code == K_CANCEL || k[i].code == K_SHOW) { text_mid(k[i].x + k[i].w / 2, k[i].y + (k[i].h - 32) / 2, k[i].label, 2, k[i].code == K_CANCEL ? C_RED : C_ACC); continue; }
		uint32_t bg = i == kb_down ? C_DOWN : (k[i].code >= 256 ? C_KEYS : C_KEY);
		if (k[i].code == K_OK) bg = i == kb_down ? C_DOWN : C_ACC;
		if (k[i].code == K_SHIFT && kb_shift) bg = C_ACC;
		rrect(k[i].x + 3, k[i].y + 4, k[i].w - 6, k[i].h - 8, 9, bg);
		int sc = strlen(k[i].label) > 3 ? 1 : 2;
		text_mid(k[i].x + k[i].w / 2, k[i].y + (k[i].h - (sc > 1 ? 32 : 18)) / 2, k[i].label, sc, C_WHITE);
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
/* lock screen: drawn here; web.py is not asked anything until it is unlocked */
#define LK_H 84         /* slide track */
#define LK_K 76         /* knob */
static int lock_y(void) { return SH - 200; }
static int lock_range(void) { return SW - 2 * PAD - 8 - LK_K; }
static int battery(int *chg) {
	char bat[8] = "", st[16] = ""; FILE *in = fopen("/sys/class/power_supply/battery/capacity", "r");
	if (in) { if (!fgets(bat, sizeof bat, in)) bat[0] = 0; fclose(in); }
	if ((in = fopen("/sys/class/power_supply/battery/status", "r"))) { if (!fgets(st, sizeof st, in)) st[0] = 0; fclose(in); }
	*chg = !strncmp(st, "Charging", 8) || !strncmp(st, "Full", 4);
	return bat[0] ? atoi(bat) : -1;
}
/* keypad: 1-9, Borrar, 0, OK in three columns */
#define PIN_R 44
static void pin_key_pos(int k, int *cx, int *cy) { *cx = SW / 2 + (k % 3 - 1) * 130; *cy = 330 + k / 3 * 105; }
static int pin_key_at(int x, int y) {
	for (int k = 0; k < 12; k++) { int cx, cy; pin_key_pos(k, &cx, &cy); if (abs(x - cx) < 60 && abs(y - cy) < 50) return k; }
	return -1;
}
static char pin_key_char(int k) { return k < 9 ? (char)('1' + k) : k == 9 ? '<' : k == 10 ? '0' : '>'; }
static void render_pin(void) {
	if (lock_blocked) {
		icon_sz(SW / 2 - 23, 150, icon_id("lock"), 1, C_RED);
		text_mid(SW / 2, 220, "Pantalla bloqueada", 2, C_RED);
		wrap2("Demasiados c\xa2" "digos err\xa2" "neos. Desbloqu\x82" "ala desde el panel web (Pantalla de bloqueo).", PAD + 20, 280, SW - 2 * PAD - 40, 2, C_TXT, 1, 1);
		text_mid(SW / 2, SH - 70, "Cancelar", 2, C_ACC);
		return;
	}
	text_mid(SW / 2, 90, "Introduce el c\xa2" "digo", 2, C_WHITE);
	int n = (int)strlen(pin_buf), dx = SW / 2 - (n * 30 - 14) / 2;
	for (int i = 0; i < n; i++) rrect(dx + i * 30, 160, 16, 16, 8, C_WHITE);
	if (!n) text_mid(SW / 2, 152, "4 a 8 cifras", 1, C_MUT);
	if (pin_msg[0]) wrap2(pin_msg, PAD, 196, SW - 2 * PAD, 1, C_RED, 1, 1);
	for (int k = 0; k < 12; k++) {
		int cx, cy; pin_key_pos(k, &cx, &cy); char c = pin_key_char(k), s[2] = {c, 0};
		uint32_t bg = k == pin_down ? C_DOWN : c == '>' ? C_ACC : C_ITM;
		rrect(cx - PIN_R, cy - PIN_R, 2 * PIN_R, 2 * PIN_R, PIN_R, bg);
		if (c == '<') text_mid(cx, cy - 11, "Borrar", 1, C_WHITE);
		else text_mid(cx, cy - 16, c == '>' ? "OK" : s, 2, C_WHITE);
	}
	text_mid(SW / 2, SH - 70, "Cancelar", 2, C_ACC);
}
static void render_lock(void) {
	buf = backbuf; clip0 = 0; clip1 = SH; fill(0, 0, SW, SH, C_BG);
	if (lock_stage) { render_pin(); present(); return; }
	char clock[16], date[16], line[40]; time_t t = time(NULL); int chg, pct = battery(&chg);
	tz_follow();
	strftime(clock, sizeof clock, "%H:%M", localtime(&t));
	strftime(date, sizeof date, "%d/%m/%Y", localtime(&t));
	fdraw(&f_xl, (SW - fwidth(&f_xl, clock, 5)) / 2, SH / 5 + 100, clock, 5, C_WHITE);
	text_mid(SW / 2, SH / 5 + 130, date, 2, C_MUT);
	if (pct >= 0) { snprintf(line, sizeof line, "Bater\xa1" "a %d%%%s", pct, chg ? " \xfa cargando" : ""); text_mid(SW / 2, SH / 5 + 170, line, 2, C_MUT); }
	int y = lock_y(), x0 = PAD + 4, kx = x0 + lock_x;
	rrect(PAD, y, SW - 2 * PAD, LK_H, LK_H / 2, C_ITM);
	if (lock_x > 0) rrect(x0, y + 4, lock_x + LK_K, LK_K, LK_K / 2, C_ACC);
	else text_mid(x0 + LK_K + lock_range() / 2, y + 26, "Desliza para desbloquear", 2, C_MUT);
	rrect(kx, y + 4, LK_K, LK_K, LK_K / 2, C_WHITE);
	icon_sz(kx + (LK_K - 30) / 2, y + 4 + (LK_K - 30) / 2, icon_id("lock"), 0, C_BLACK);
	present();
}
/* each section has its own color (home tiles and list icons) */
static uint32_t icon_color(const char *name) {
	static const struct { const char *n; unsigned char r, g, b; } P[] = {
		{"wifi", 48, 209, 88}, {"ap", 100, 210, 255}, {"vpn", 255, 159, 10}, {"dns", 10, 132, 255},
		{"usb", 191, 90, 242}, {"res", 255, 55, 95}, {"disp", 255, 214, 10}, {"logs", 94, 92, 230},
		{"sys", 152, 152, 157}, {"qr", 235, 235, 245}, {"ip", 100, 210, 255}, {"user", 10, 132, 255},
		{"power", 255, 69, 58}, {"panel", 90, 200, 250}, {"speed", 48, 209, 88}, {"tz", 255, 159, 10}, {"lock", 152, 152, 157}};
	for (size_t i = 0; name && i < sizeof P / sizeof P[0]; i++) if (!strcmp(P[i].n, name)) return color(P[i].r, P[i].g, P[i].b);
	return C_ACC;
}
static void render(void) {
	if (locked) { render_lock(); return; }
	buf = backbuf; clip0 = 0; clip1 = SH; fill(0, 0, SW, SH, C_BG);
	clip0 = TOP; clip1 = TOP + view_h();
	int w = SW - 2 * PAD;
	for (int i = 0; i < nel; i++) {
		struct el *e = &els[i]; int y = TOP + e->y - scroll;
		if (y + e->h < clip0 || y > clip1) continue;
		switch (e->t) {
		case 'M': {
			int err = e->b && *e->b == 'e';
			rrect(PAD, y, w, e->h - 8, 14, err ? C_DNG : C_OKB);
			wrap(e->a, PAD + 14, y + 6, w - 28, 2, err ? C_RED : C_GRN, 1); break; }
		case 'L': {
			/* status lines get a colored dot */
			char k = e->b ? *e->b : 'n';
			if (k == 'g' || k == 'y' || k == 'r') { rrect(PAD + 3, y + 11, 11, 11, 6, tcolor(e->b)); wrap(e->a, PAD + 24, y, w - 24, 2, k == 'y' || k == 'r' ? tcolor(e->b) : C_TXT, 1); }
			else wrap(e->a, PAD, y, w, 2, tcolor(e->b), 1);
			break; }
		case 'l': wrap(e->a, PAD, y, w, 1, tcolor(e->b), 1); break;
		case 'P': {   /* table row: name, then two right-aligned columns */
			uint32_t c = tcolor(e->d); const char *b = e->b ? e->b : "", *cc = e->c ? e->c : "";
			int c3 = SW - PAD - 4, c2 = c3 - 150;
			text_fit(PAD, y, e->a, c2 - 110 - PAD, 1, c);
			text(c2 - tw(b, 1), y, b, 1, C_MUT); text(c3 - tw(cc, 1), y, cc, 1, c);
			break; }
		case 'C': {   /* home tile: colored icon over its name */
			int x = tile_x(e), tw0 = tile_w(), ic = icon_id(e->c);
			if (x >= SW || x + tw0 <= 0) break;   /* on another page */
			rrect(x, y, tw0, tile_h, 20, i == pressed ? C_DOWN : C_ITM);
			const char *s = e->b ? e->b : "";
			/* icon and name centered as a block, whatever the tile height */
			int lines = wrap2(s, 0, 0, tw0 - 20, 2, 0, 0, 1) / LINE(2), top = y + (tile_h - 46 - 8 - lines * LINE(2)) / 2;
			if (ic >= 0) icon_sz(x + (tw0 - 46) / 2, top, ic, 1, icon_color(e->c));
			wrap2(s, x + 10, top + 54, tw0 - 20, 2, C_TXT, 1, 1);
			break; }
		case 'B': {
			char st = e->c ? *e->c : 'n'; uint32_t bg = st == 'p' ? C_ACC : st == 'd' ? C_DNGB : st == 'i' ? C_ITM : C_BTN;
			if (i == pressed) bg = C_DOWN;
			rrect(PAD, y, w, e->h - 8, 16, bg);
			uint32_t fg = st == 'd' && i != pressed ? C_RED : C_WHITE;
			int ic = icon_id(e->d), ty = y + (e->h - 8 - 32) / 2;
			const char *s = e->b ? e->b : "";
			if (st == 'i') {
				int tx2 = PAD + 18;
				if (ic >= 0) { icon(tx2, ty, ic, i == pressed ? C_WHITE : icon_color(e->d)); tx2 += 48; }
				text_fit(tx2, ty, s, SW - PAD - 44 - tx2, 2, fg);
				icon(SW - PAD - 38, ty, icon_id("more"), C_MUT);
			} else {
				int iw = ic >= 0 ? 42 : 0, room = w - 24 - iw, n = tw(s, 2) < room ? tw(s, 2) : room;
				int x0 = PAD + (w - n - iw) / 2;
				if (ic >= 0) icon(x0, ty, ic, fg);
				text_fit(x0 + iw, ty, s, room, 2, fg);
			}
			break; }
		case 'S': {
			int on = e->c && *e->c == '1';
			rrect(PAD, y, w, e->h - 8, 16, i == pressed ? C_DOWN : C_ITM);
			text_fit(PAD + 18, y + 16, e->b ? e->b : "", w - 130, 2, C_WHITE);
			int sx = SW - PAD - 96, sy = y + 14;
			rrect(sx, sy, 80, 36, 18, on ? C_GRN : C_KEYS);
			rrect(on ? sx + 46 : sx + 4, sy + 4, 28, 28, 14, C_WHITE);
			break; }
		case 'D': {   /* slider: track, filled part, knob, percentage */
			int lo, hi, v = slider_val(e, &lo, &hi), x0 = PAD + 24, x1 = SW - PAD - 104;
			int kx = x0 + (v - lo) * (x1 - x0) / (hi - lo);
			char pct[8]; snprintf(pct, sizeof pct, "%d%%", v * 100 / hi);
			rrect(PAD, y, w, e->h - 8, 16, C_ITM);
			rrect(x0, y + 28, x1 - x0, 8, 4, C_KEYS);
			if (kx - x0 >= 8) rrect(x0, y + 28, kx - x0, 8, 4, C_ACC);
			rrect(kx - 15, y + 17, 30, 30, 15, C_WHITE);
			text(SW - PAD - 76, y + 16, pct, 2, C_WHITE);
			break; }
		case 'F': {
			text(PAD + 4, y, e->b ? e->b : "", 1, C_MUT);
			int editing = kb_open && e == kb_el;
			rrect(PAD, y + 22, w, 54, 12, editing || i == pressed ? C_ACC : e->dirty ? C_YEL : C_KEYS);
			rrect(PAD + 2, y + 24, w - 4, 50, 10, C_FLD);
			char tmp[160]; const char *s = e->val; int n = (int)strlen(s);
			if (secret(e) && !(editing && kb_show)) { memset(tmp, '*', n); tmp[n] = 0; s = tmp; }
			/* the end (where the cursor is) stays visible */
			while (*s && tw(s, 2) > w - 30) s++;
			if (!n && !editing) text(PAD + 12, y + 33, "Tocar para escribir", 2, C_MUT);
			else text(PAD + 12, y + 33, s, 2, C_WHITE);
			if (editing) fill(PAD + 13 + tw(s, 2), y + 35, 2, 30, C_ACC);   /* cursor */
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
	if (npages > 1) {   /* page dots under the tiles */
		int dy = TOP + tiles_y + tiles_h - scroll + 6, dx = SW / 2 - (npages * 22 - 12) / 2;
		for (int p = 0; p < npages; p++) rrect(dx + p * 22, dy, 10, 10, 5, p == page ? C_WHITE : C_KEY);
	}
	clip0 = 0; clip1 = SH;
	/* scroll hint */
	if (content_h > view_h()) { int vh = view_h(), bh = vh * vh / content_h; if (bh < 30) bh = 30; rrect(SW - 6, TOP + (vh - bh) * scroll / (content_h - vh), 4, bh, 2, C_MUT); }
	fill(0, 0, SW, TOP, C_BAR);
	fill(0, TOP - 1, SW, 1, C_LINE);
	int tx = PAD;
	if (back[0]) { if (pressed == -2) rrect(6, 8, 56, TOP - 16, 12, C_DOWN); icon_sz(18, (TOP - 30) / 2, icon_id("back"), 0, C_ACC); tx = 68; }
	/* top right: clock and battery on one line; the title keeps the rest */
	char clock[16], b[12]; time_t t = time(NULL); int chg, pct = battery(&chg);
	tz_follow();
	strftime(clock, sizeof clock, "%H:%M", localtime(&t));
	int base = 38, rx = SW - PAD;
	if (pct >= 0) {
		uint32_t bc = pct <= 15 && !chg ? C_RED : chg ? C_GRN : C_TXT;
		snprintf(b, sizeof b, "%d%%", pct);
		rx -= fwidth(&f_st, b, (int)strlen(b)); fdraw(&f_st, rx, base, b, 8, bc);
		rx -= 34;   /* battery outline, fill and tip */
		rrect(rx, base - 14, 26, 14, 4, C_MUT); rrect(rx + 2, base - 12, 22, 10, 3, C_BAR);
		if (pct > 0) rrect(rx + 3, base - 11, (pct * 20 + 99) / 100, 8, 2, bc);
		rrect(rx + 26, base - 10, 3, 6, 1, C_MUT);
		rx -= 12;
	}
	rx -= fwidth(&f_st, clock, 5); fdraw(&f_st, rx, base, clock, 5, C_TXT);
	fdraw_fit(&f_tt, tx, base + 1, title, rx - tx - 12, C_WHITE);
	if (busy) { rrect(60, SH / 2 - 50, SW - 120, 100, 20, C_BTN); text_mid(SW / 2, SH / 2 - 16, "Un momento...", 2, C_WHITE); }
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
	if (!refresh) for (int i = 0; i < nel; i++) if (els[i].t == 'F') { strcat(q, "&f_"); enc(q, sizeof q, els[i].key); strcat(q, "="); enc(q, sizeof q, els[i].val); }
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
		if (lock_on) { locked = 1; lock_drag = lock_x = 0; }
		lock_stage = 0; pin_buf[0] = pin_msg[0] = 0; pin_down = -1;
	}
}
static double last_touch;
/* idle_s from web.py: 0 = always on; the keyboard gets at least 2 min.
 * The chosen time is when the screen goes off; its last third (10 s at most)
 * it is dimmed but still usable. deadline = start of the dimmed part. */
static int idle_eff(void) { return locked ? 10 : kb_open && idle_s < 120 ? 120 : idle_s; }   /* lock screen: 10 s */
static int dim_len(void) { int d = idle_eff() / 3; return d > 10 ? 10 : d < 3 ? 3 : d; }
static void set_deadline(void) { deadline = idle_s || locked ? last_touch + idle_eff() - dim_len() : 1e12; }
static void poke(void) {
	if (dimmed) { set_bright(); dimmed = 0; }
	last_touch = now();
	set_deadline();
}
/* nobody looking: status every 30 s at most */
static int refresh_every(void) { return refresh_s > 0 && refresh_s < 30 && now() - last_touch > 60 ? 30 : refresh_s; }
/* back where it was, except screens that show keys (QR) */
static void resume(void) {
	char nav[160]; snprintf(nav, sizeof nav, "nav:%s", strncmp(screen_id, "qr", 2) && strncmp(screen_id, "wifiqr", 6) && strcmp(screen_id, "power") ? screen_id : "home");
	send_action(nav, 0);
}
/* lock state from the K line of a reply, without touching the current screen */
static void scan_k(void) {
	char *k = strstr(resp, "\nK\t"); if (!k) return;
	char line[32]; int n = (int)strcspn(k + 1, "\n"); snprintf(line, sizeof line, "%.*s", n, k + 1);
	lock_pin = line[2] == '1' && line[3] == '\t' && line[4] == '1';
	lock_blocked = lock_pin && line[5] == '\t' && line[6] == '1';
}
static void pin_state(void) { if (request("a=lock.state&s=home") == 0) scan_k(); }
/* web.py checks the code; its error message (wrong, too many tries) is shown */
static int pin_check(void) {
	char q[96]; snprintf(q, sizeof q, "a=lock.try&s=home&f_pin=%s", pin_buf);
	busy_pending = 1; int ok = request(q) == 0; busy = busy_pending = 0;
	if (!ok) { snprintf(pin_msg, sizeof pin_msg, "Sin respuesta; vuelve a intentarlo"); return 0; }
	scan_k();
	if (!has_error()) return 1;
	char *m = strstr(resp, "\nM\t"); pin_msg[0] = 0;
	if (m) { m += 3; int n = (int)strcspn(m, "\t\n"); snprintf(pin_msg, sizeof pin_msg, "%.*s", n, m); }
	return 0;
}
static void pin_tap(int x, int y, int y0) {
	int k = pin_down; pin_down = -1;
	if (y0 > SH - 110 && y > SH - 110) { lock_stage = 0; pin_buf[0] = pin_msg[0] = 0; render(); return; }   /* Cancelar */
	if (lock_blocked || k < 0 || k != pin_key_at(x, y)) { render(); return; }
	char c = pin_key_char(k); int n = (int)strlen(pin_buf);
	if (c >= '0' && c <= '9' && n < 8) { pin_buf[n] = c; pin_buf[n + 1] = 0; pin_msg[0] = 0; }
	else if (c == '<' && n) pin_buf[n - 1] = 0;
	else if (c == '>' && n >= 4) {
		if (pin_check()) { locked = lock_stage = 0; pin_buf[0] = pin_msg[0] = 0; resume(); return; }
		pin_buf[0] = 0;
	}
	render();
}
static void wake(void) {
	wakes++; light(1); poke();
	if (locked) render(); else resume();
}

/* ---- input ---- */
static int evkey = -1, evtouch = -1;
static int t_slot, t_id = -1, t_x, t_y, t_down, t_x0, t_y0, t_scroll0, dragging, ignore;
static double last_drag_render;
/* while a finger drags: a new frame at most every 16 ms (~60 per second) */
#define FRAME 0.016
static void frame(void) { if (now() - last_drag_render > FRAME) { render(); last_drag_render = now(); } }
static int hdrag;   /* sideways drag of the tile pages */
static int hit(int x, int y) {
	if (y < TOP) return (back[0] && x < 80) ? -2 : -1;
	if (y >= TOP + view_h()) return -1;
	int cy = y - TOP + scroll;
	for (int i = 0; i < nel; i++) {
		struct el *e = &els[i];
		if (e->t == 'C' && cy >= e->y && cy < e->y + tile_h && x >= tile_x(e) && x < tile_x(e) + tile_w()) return i;
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
	if (c == K_OK) { kb_open = 0; clamp_scroll(); }   /* the field already has the text */
	else if (c == K_CANCEL) {   /* X: undo what was typed in this field */
		snprintf(kb_el->val, sizeof kb_el->val, "%s", kb_orig); kb_el->dirty = kb_was_dirty; kb_open = 0; clamp_scroll();
	}
	else if (c == K_SHOW) kb_show = !kb_show;
	else if (c == K_BS) { if (len) kb_buf[len - 1] = 0; }
	else if (c == K_SHIFT) kb_shift = !kb_shift;
	else if (c == K_LAYER) { kb_layer = kb_layer ? 0 : 1; kb_shift = 0; }
	else if (c == K_LAYER2) kb_layer = kb_layer == 1 ? 2 : 1;
	else if (len < (digits_only() ? 8 : (int)sizeof kb_buf - 1)) {   /* a code has at most 8 digits */
		kb_buf[len] = (char)(c == K_SPACE ? ' ' : c); kb_buf[len + 1] = 0;
		if (kb_layer == 0) kb_shift = 0;
	}
	/* every key goes straight into the field: nothing to confirm */
	if (kb_open && (c == K_BS || c < 256 || c == K_SPACE) && strcmp(kb_el->val, kb_buf)) { snprintf(kb_el->val, sizeof kb_el->val, "%s", kb_buf); kb_el->dirty = 1; }
	poke();
}
static void open_kb(struct el *e) {
	kb_el = e; kb_open = 1; kb_show = 0; kb_shift = 0;
	kb_layer = (e->d && (*e->d == 'n' || *e->d == 'i' || *e->d == 'q')) ? 1 : 0;
	snprintf(kb_buf, sizeof kb_buf, "%s", e->val); snprintf(kb_orig, sizeof kb_orig, "%s", e->val); kb_was_dirty = e->dirty;
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
	frame();
}
static void touch_down(int x, int y) {
	if (debug) fprintf(stderr, "%.3f dedo %d,%d%s\n", now(), x, y, shown ? "" : " (despierta)");
	if (!shown) { ignore = 1; wake(); return; }
	poke(); t_x0 = x; t_y0 = y; t_scroll0 = scroll; dragging = hdrag = 0; t_maxd = 0; t_time0 = now();
	/* locked: only a drag that starts on the knob counts */
	if (locked && lock_stage) { pin_down = pin_key_at(x, y); render(); return; }
	if (locked) { lock_drag = y > lock_y() - 30 && y < lock_y() + LK_H + 30 && x < PAD + 4 + LK_K + 40; lock_x = 0; return; }
	if (kb_open && y >= KBY - PVH) { kb_down = kb_hit(x, y); pressed = t_el = -1; }
	else pressed = t_el = hit(x, y);
	if (sliding()) { pressed = -1; last_drag_render = 0; slide(x); return; }
	render();
}
static void touch_move(int x, int y) {
	int d = abs(y - t_y0) > abs(x - t_x0) ? abs(y - t_y0) : abs(x - t_x0);
	if (d > t_maxd) t_maxd = d;
	if (locked) {
		if (lock_stage || !lock_drag) return;
		lock_x = x - t_x0; if (lock_x < 0) lock_x = 0; if (lock_x > lock_range()) lock_x = lock_range();
		frame();
		return;
	}
	if (kb_open && t_y0 >= KBY - PVH) return;
	if (sliding()) { slide(x); return; }
	/* sideways on the tiles: change page */
	int ty = t_y0 - TOP + scroll, on_tiles = npages > 1 && !kb_open && ty >= tiles_y && ty < tiles_y + tiles_h + DOTS_H;
	if (!dragging && !hdrag && on_tiles && abs(x - t_x0) > 24 && abs(x - t_x0) > abs(y - t_y0)) { hdrag = 1; pressed = -1; }
	if (hdrag) {
		page_dx = x - t_x0;
		if ((page == 0 && page_dx > 0) || (page == npages - 1 && page_dx < 0)) page_dx /= 3;   /* no more pages: it resists */
		frame(); return;
	}
	if (!dragging && abs(y - t_y0) > 32 && content_h > view_h()) { dragging = 1; pressed = -1; }
	if (dragging) {
		scroll = t_scroll0 - (y - t_y0); clamp_scroll();
		frame();
	}
}
static void touch_up(int x, int y) {
	double dur = now() - t_time0;
	if (ignore) { ignore = 0; if (debug) fprintf(stderr, "%.3f ignorado (despertar o pendiente)\n", now()); return; }
	if (locked && lock_stage) { pin_tap(x, y, t_y0); return; }
	if (locked) {   /* knob almost at the end: unlocked (or the keypad); otherwise it goes back */
		int open = lock_drag && lock_x >= lock_range() * 9 / 10;
		if (debug) fprintf(stderr, "%.3f bloqueo: arrastre %d de %d%s\n", now(), lock_x, lock_range(), open ? (lock_pin ? " -> pide el codigo" : " -> desbloqueada") : "");
		lock_drag = lock_x = 0;
		if (open && lock_pin) { pin_state(); lock_stage = 1; pin_buf[0] = pin_msg[0] = 0; if (!lock_pin) { locked = lock_stage = 0; resume(); } else render(); }
		else if (open) { locked = 0; resume(); } else render();
		return;
	}
	if (kb_open && t_y0 >= KBY - PVH) {
		if (kb_down >= 0) kb_press(kb_down);
		kb_down = -1; render(); return;
	}
	if (sliding()) {
		char a[200]; struct el *e = &els[t_el]; snprintf(a, sizeof a, "%s:%s", e->a, e->val);
		t_el = -1; kb_open = 0; send_action(a, 0); return;
	}
	if (hdrag) {   /* past a fifth of the width, or a quick flick: next page; then it slides into place */
		int quick = dur < 0.25 && abs(page_dx) > 40;
		int dir = page_dx < -SW / 5 || (quick && page_dx < 0) ? 1 : page_dx > SW / 5 || (quick && page_dx > 0) ? -1 : 0;
		if (page + dir < 0 || page + dir >= npages) dir = 0;
		page += dir; hdrag = 0;
		int off = page_dx + dir * SW;   /* same picture, counted from the new page */
		double t0 = now(), len = 0.18;
		for (double p = 0; p < 1; p = (now() - t0) / len) { page_dx = (int)(off * (1 - p) * (1 - p)); render(); }
		page_dx = 0; render();
		if (debug) fprintf(stderr, "%.3f pagina %d de %d\n", now(), page + 1, npages);
		return;
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
	if (locked && lock_pin) { if (!shown) light(1); poke(); render(); return; }   /* the code cannot be skipped */
	locked = 0;   /* holding Power is deliberate: the menu opens even when locked */
	kb_open = 0; poke(); send_action("nav:power", 0);
}
/* hardware keys: Home, Back, Recents = resources, volume scrolls */
static void key(int c) {
	if (debug) fprintf(stderr, "%.3f tecla %d\n", now(), c);
	if (!shown) { wake(); return; }
	poke();
	if (locked) return;
	if (c == KEY_VOLUMEUP) { scroll -= 300; clamp_scroll(); render(); }
	else if (c == KEY_VOLUMEDOWN) { scroll += 300; clamp_scroll(); render(); }
	else if (c == KEY_HOME) { kb_open = 0; send_action("nav:home", 0); }
	else if (c == KEY_BACK) { if (kb_open) { kb_open = 0; render(); } else if (back[0]) send_action(back, 0); else if (page) { page = 0; render(); } }
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
	/* black background with gray cards (dark system palette) */
	C_BG = color(0, 0, 0); C_BAR = color(0, 0, 0); C_TXT = color(235, 235, 245); C_MUT = color(142, 142, 147);
	C_GRN = color(48, 209, 88); C_YEL = color(255, 214, 10); C_RED = color(255, 69, 58); C_BTN = color(44, 44, 46);
	/* accent: blue (primary buttons, sliders, cursor) */
	C_ACC = color(10, 132, 255);
	C_PRI = C_ACC; C_DNG = color(58, 20, 20); C_DNGB = color(58, 22, 22); C_ITM = color(28, 28, 30); C_FLD = color(10, 10, 12);
	C_KEY = color(58, 58, 60); C_KEYS = color(44, 44, 46); C_DOWN = color(72, 72, 74); C_WHITE = color(255, 255, 255); C_BLACK = color(0, 0, 0);
	C_OKB = color(16, 44, 26); C_LINE = color(28, 28, 30);
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
	if (lock_pin) { locked = 1; poke(); render(); }   /* with a code the J1 starts locked */
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
		if (refresh_every() > 0 && !kb_open && !locked && !t_down && now() >= last_req + refresh_every()) { char nav[160]; snprintf(nav, sizeof nav, "nav:%s", screen_id); send_action(nav, 1); }
	}
}
