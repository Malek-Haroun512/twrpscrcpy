/*
 * fbstream - tiny freestanding ARM64/ARM helper for TWRP recovery.
 *
 * Why: recovery has no surfaceflinger, no screencap and the framebuffer
 * device usually does not support read() at all (Samsung decon returns 0
 * bytes).  So we mmap /dev/graphics/fb0 and stream a downscaled, RLE
 * compressed frame over stdout.  The same binary can inject evdev events
 * read from stdin (writing to /dev/input/event* works without uinput).
 *
 * Build: see build.sh (clang, -nostdlib -static, no libc).
 *
 * Frame packet (little endian):
 *   u32 magic   'T','W','F','1'  changed frame
 *               'T','W','F','2'  keepalive, no payload
 *   u32 width   (scaled pixels)
 *   u32 height  (scaled pixels)
 *   u32 runs    number of RLE runs that follow
 *   u32 scale   downscale factor used
 *   u32 yoffset framebuffer y offset of the captured buffer
 *   then runs * (u16 count, u16 rgb565)
 *
 * Injection mode:
 *   fbstream --inject /dev/input/eventN
 *   reads 24 byte struct input_event chunks from stdin and writes them
 *   to the event device (kernel side struct size is always 24 on 64 bit).
 *
 * This file is self contained: it talks to the kernel with raw syscalls.
 */

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long u64;
typedef long i64;

#if defined(__aarch64__)
#define SYS_read 63
#define SYS_write 64
#define SYS_close 57
#define SYS_ioctl 29
#define SYS_openat 56
#define SYS_mmap 222
#define SYS_nanosleep 101
#define SYS_exit 93
#define SYS_exit_group 94
#define AT_FDCWD (-100)
#define O_RDONLY 0
#define O_WRONLY 1
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_SHARED 1
#define MAP_ANONYMOUS 0x20

static inline long syscall6(long n, long a, long b, long c, long d, long e, long f)
{
	register long x0 asm("x0") = a;
	register long x1 asm("x1") = b;
	register long x2 asm("x2") = c;
	register long x3 asm("x3") = d;
	register long x4 asm("x4") = e;
	register long x5 asm("x5") = f;
	register long x8 asm("x8") = n;
	asm volatile("svc #0"
		     : "+r"(x0)
		     : "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5), "r"(x8)
		     : "memory");
	return x0;
}
#define SYSCALL(n, a, b, c, d, e, f) syscall6(n, (long)(a), (long)(b), (long)(c), (long)(d), (long)(e), (long)(f))

__asm__(".global _start\n"
	"_start:\n"
	"  mov x0, sp\n"
	"  bl cstart\n"
	"  mov x0, #0\n"
	"  mov x8, #93\n"
	"  svc #0\n");

#elif defined(__arm__)
#define SYS_read 3
#define SYS_write 4
#define SYS_close 6
#define SYS_ioctl 54
#define SYS_open 5
#define SYS_mmap2 192
#define SYS_nanosleep 162
#define SYS_exit 1
#define SYS_exit_group 248
#define AT_FDCWD (-100)
#define O_RDONLY 0
#define O_WRONLY 1
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_SHARED 1
#define MAP_ANONYMOUS 0x20

static inline long syscall6(long n, long a, long b, long c, long d, long e, long f)
{
	register long r0 asm("r0") = a;
	register long r1 asm("r1") = b;
	register long r2 asm("r2") = c;
	register long r3 asm("r3") = d;
	register long r4 asm("r4") = e;
	register long r5 asm("r5") = f;
	register long r7 asm("r7") = n;
	asm volatile("svc #0"
		     : "+r"(r0)
		     : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r5), "r"(r7)
		     : "memory");
	return r0;
}
#define SYSCALL(n, a, b, c, d, e, f) syscall6(n, (long)(a), (long)(b), (long)(c), (long)(d), (long)(e), (long)(f))

__asm__(".global _start\n"
	"_start:\n"
	"  mov r0, sp\n"
	"  bl cstart\n"
	"  mov r0, #0\n"
	"  mov r7, #1\n"
	"  svc #0\n");
#endif

#if defined(__arm__)
/* libgcc/compiler-rt division helpers (no libc is linked on arm builds) */
unsigned __aeabi_uidiv(unsigned n, unsigned d)
{
	unsigned q = 0, r = 0;
	int i;
	if (!d)
		return 0;
	for (i = 31; i >= 0; i--) {
		r = (r << 1) | ((n >> i) & 1u);
		if (r >= d) {
			r -= d;
			q |= (1u << i);
		}
	}
	return q;
}

unsigned __aeabi_uidivmod(unsigned n, unsigned d)
{
	unsigned q = __aeabi_uidiv(n, d);
	return q;
}
#endif

#define FBIOGET_VSCREENINFO 0x4600
#define FBIOGET_FSCREENINFO 0x4602

struct fb_bitfield {
	u32 offset;
	u32 length;
	u32 msb_right;
};

struct fb_var_screeninfo {
	u32 xres;
	u32 yres;
	u32 xres_virtual;
	u32 yres_virtual;
	u32 xoffset;
	u32 yoffset;
	u32 bits_per_pixel;
	u32 grayscale;
	struct fb_bitfield red;
	struct fb_bitfield green;
	struct fb_bitfield blue;
	struct fb_bitfield transp;
	u32 nonstd;
	u32 activate;
	u32 height;
	u32 width;
	u32 accel_flags;
	u32 pixclock;
	u32 left_margin;
	u32 right_margin;
	u32 upper_margin;
	u32 lower_margin;
	u32 hsync_len;
	u32 vsync_len;
	u32 sync;
	u32 vmode;
	u32 rotate;
	u32 colorspace;
	u32 reserved[4];
};

struct fb_fix_screeninfo {
	char id[16];
	u64 smem_start;
	u32 smem_len;
	u32 type;
	u32 type_aux;
	u32 visual;
	u16 xpanstep;
	u16 ypanstep;
	u16 ywrapstep;
	u16 __pad;
	u32 line_length;
	u64 mmio_start;
	u32 mmio_len;
	u32 accel;
	u16 capabilities;
	u16 reserved[2];
};

struct timespec {
	i64 tv_sec;
	i64 tv_nsec;
};

/* ---- libc-less helpers ------------------------------------------------ */

static u64 slen(const char *s)
{
	u64 n = 0;
	while (s[n])
		n++;
	return n;
}

static void put(const char *s)
{
	SYSCALL(SYS_write, 2, s, slen(s), 0, 0, 0);
}

static long open_ro(const char *path)
{
#if defined(__aarch64__)
	return SYSCALL(SYS_openat, AT_FDCWD, path, O_RDONLY, 0, 0, 0);
#else
	return SYSCALL(SYS_open, path, O_RDONLY, 0, 0, 0, 0);
#endif
}

static long open_wo(const char *path)
{
#if defined(__aarch64__)
	return SYSCALL(SYS_openat, AT_FDCWD, path, O_WRONLY, 0, 0, 0);
#else
	return SYSCALL(SYS_open, path, O_WRONLY, 0, 0, 0, 0);
#endif
}

static void *mem_map(u64 len, long prot, long flags, long fd)
{
#if defined(__aarch64__)
	long r = SYSCALL(SYS_mmap, 0, len, prot, flags, fd, 0);
#else
	long r = SYSCALL(SYS_mmap2, 0, len, prot, flags, fd, 0);
#endif
	if (r < 0)
		return 0;
	return (void *)r;
}

static i64 parse_int(const char *s, i64 def)
{
	i64 v = 0;
	int any = 0;
	if (!s)
		return def;
	while (*s == ' ')
		s++;
	while (*s >= '0' && *s <= '9') {
		v = v * 10 + (*s - '0');
		s++;
		any = 1;
	}
	return any ? v : def;
}

static int str_eq(const char *a, const char *b)
{
	while (*a && *a == *b) {
		a++;
		b++;
	}
	return *a == *b;
}

static int str_pref(const char *a, const char *p)
{
	while (*p) {
		if (*a != *p)
			return 0;
		a++;
		p++;
	}
	return 1;
}

/* ---- injection -------------------------------------------------------- */

static int read_full(long fd, u8 *buf, u64 len)
{
	u64 got = 0;
	while (got < len) {
		long r = SYSCALL(SYS_read, fd, buf + got, len - got, 0, 0, 0);
		if (r <= 0)
			return r < 0 ? -1 : (int)got;
		got += (u64)r;
	}
	return (int)got;
}

static int write_full(long fd, const u8 *buf, u64 len)
{
	u64 done = 0;
	while (done < len) {
		long r = SYSCALL(SYS_write, fd, buf + done, len - done, 0, 0, 0);
		if (r <= 0)
			return -1;
		done += (u64)r;
	}
	return 0;
}

static int inject_mode(const char *path)
{
	u8 buf[24];
	long fd = open_wo(path);
	if (fd < 0) {
		put("fbstream: cannot open input device\n");
		return 1;
	}
	for (;;) {
		/* one event at a time keeps latency low */
		int n = read_full(0, buf, 24);
		if (n <= 0)
			break;
		if (n != 24)
			break;
		if (write_full(fd, buf, 24) < 0) {
			/* The panel may have been suspended and the node invalidated.
			 * Reopen it and retry, otherwise we would drop half a gesture
			 * and leave TWRP with a phantom finger. */
			SYSCALL(SYS_close, fd, 0, 0, 0, 0, 0);
			fd = open_wo(path);
			if (fd < 0)
				break;
			if (write_full(fd, buf, 24) < 0)
				break;
		}
	}
	SYSCALL(SYS_close, fd, 0, 0, 0, 0, 0);
	return 0;
}

/* ---- capture ---------------------------------------------------------- */

static u8 outbuf[1 << 20];
static u64 outlen;
static long out_fd = 1;

static int out_flush(void)
{
	if (outlen) {
		if (write_full(out_fd, outbuf, outlen) < 0)
			return -1;
		outlen = 0;
	}
	return 0;
}

static int out_raw(const void *p, u64 n)
{
	const u8 *s = (const u8 *)p;
	if (n > sizeof(outbuf)) {
		if (out_flush() < 0)
			return -1;
		return write_full(out_fd, s, n);
	}
	if (outlen + n > sizeof(outbuf)) {
		if (out_flush() < 0)
			return -1;
	}
	u8 *d = outbuf + outlen;
	const u8 *q = s;
	for (u64 i = 0; i < n; i++)
		d[i] = q[i];
	outlen += n;
	return 0;
}

static int out_u32(u32 v)
{
	u8 b[4];
	b[0] = (u8)(v);
	b[1] = (u8)(v >> 8);
	b[2] = (u8)(v >> 16);
	b[3] = (u8)(v >> 24);
	return out_raw(b, 4);
}

static int out_u16(u16 v)
{
	u8 b[2];
	b[0] = (u8)(v);
	b[1] = (u8)(v >> 8);
	return out_raw(b, 2);
}

static u32 scale_bits(u32 px, const struct fb_bitfield *bf, u32 out_bits)
{
	u32 v;
	if (!bf->length)
		return 0;
	v = (px >> bf->offset) & ((1u << bf->length) - 1u);
	if (bf->length > out_bits)
		v >>= (bf->length - out_bits);
	else if (bf->length < out_bits)
		v <<= (out_bits - bf->length);
	return v;
}

static u16 to565(u32 px, const struct fb_var_screeninfo *vi)
{
	u32 r, g, b;
	if (vi->bits_per_pixel == 16)
		return (u16)px;
	r = scale_bits(px, &vi->red, 5);
	g = scale_bits(px, &vi->green, 6);
	b = scale_bits(px, &vi->blue, 5);
	return (u16)((r << 11) | (g << 5) | b);
}

static void sleep_ms(u32 ms)
{
	struct timespec ts;
	ts.tv_sec = ms / 1000;
	ts.tv_nsec = (i64)(ms % 1000) * 1000000;
	SYSCALL(SYS_nanosleep, &ts, 0, 0, 0, 0, 0);
}

static int capture_mode(const char *fbpath, int scale, int fps)
{
	long fd = open_ro(fbpath);
	struct fb_var_screeninfo vi;
	struct fb_fix_screeninfo fi;
	long r;
	u64 maplen;
	u8 *mem;
	u32 ow, oh;
	u16 *cur;
	u16 *prev;
	u64 hash = 0;
	int have_prev = 0;

	if (fd < 0) {
		put("fbstream: cannot open framebuffer\n");
		return 1;
	}

	/* zero both structs (no memset in freestanding code) */
	{
		u8 *p = (u8 *)&vi;
		for (u64 i = 0; i < sizeof(vi); i++)
			p[i] = 0;
		p = (u8 *)&fi;
		for (u64 i = 0; i < sizeof(fi); i++)
			p[i] = 0;
	}

	r = SYSCALL(SYS_ioctl, fd, FBIOGET_VSCREENINFO, &vi, 0, 0, 0);
	if (r < 0) {
		put("fbstream: FBIOGET_VSCREENINFO failed\n");
		return 1;
	}
	r = SYSCALL(SYS_ioctl, fd, FBIOGET_FSCREENINFO, &fi, 0, 0, 0);
	if (r < 0) {
		put("fbstream: FBIOGET_FSCREENINFO failed\n");
		return 1;
	}
	if (vi.bits_per_pixel != 32 && vi.bits_per_pixel != 16) {
		put("fbstream: unsupported bpp\n");
		return 1;
	}
	if (!fi.smem_len || !fi.line_length) {
		put("fbstream: framebuffer has no memory info\n");
		return 1;
	}
	if (scale < 1)
		scale = 1;
	if (scale > 8)
		scale = 8;
	ow = vi.xres / (u32)scale;
	oh = vi.yres / (u32)scale;
	if (!ow || !oh) {
		put("fbstream: bad geometry\n");
		return 1;
	}

	maplen = (u64)fi.smem_len;
	maplen = (maplen + 4095) & ~4095ULL;
	mem = (u8 *)mem_map(maplen, PROT_READ, MAP_SHARED, fd);
	if (!mem) {
		put("fbstream: mmap failed\n");
		return 1;
	}

	{
		u64 bytes = (u64)ow * oh * 2;
		cur = (u16 *)mem_map((bytes + 4095) & ~4095ULL,
				     PROT_READ | PROT_WRITE,
				     MAP_SHARED | MAP_ANONYMOUS, -1);
		prev = (u16 *)mem_map((bytes + 4095) & ~4095ULL,
				      PROT_READ | PROT_WRITE,
				      MAP_SHARED | MAP_ANONYMOUS, -1);
		if (!cur || !prev) {
			put("fbstream: scratch mmap failed\n");
			return 1;
		}
	}

	for (;;) {
		u32 yoff;
		u8 *base;
		u32 y, x;
		u32 pxb = vi.bits_per_pixel / 8;
		u32 nrun = 0;
		u16 runpix = 0;
		u32 runlen = 0;
		int changed = 0;

		/* current buffer (minui double buffers by changing yoffset) */
		if (SYSCALL(SYS_ioctl, fd, FBIOGET_VSCREENINFO, &vi, 0, 0, 0) < 0)
			break;
		yoff = vi.yoffset;
		if (yoff >= vi.yres_virtual)
			yoff = 0;
		base = mem + (u64)yoff * fi.line_length;

		for (y = 0; y < oh; y++) {
			u8 *row = base + (u64)(y * (u32)scale) * fi.line_length;
			u16 *dst = cur + (u64)y * ow;
			for (x = 0; x < ow; x++) {
				u32 sx = x * (u32)scale;
				u32 px;
				if (pxb == 4) {
					u32 *p32 = (u32 *)(row + (u64)sx * 4);
					px = *p32;
				} else {
					u16 *p16 = (u16 *)(row + (u64)sx * 2);
					px = *p16;
				}
				dst[x] = to565(px, &vi);
			}
		}

		if (!have_prev) {
			changed = 1;
		} else {
			for (u64 i = 0; i < (u64)ow * oh; i++) {
				if (cur[i] != prev[i]) {
					changed = 1;
					break;
				}
			}
		}
		(void)hash;

		if (!changed) {
			out_u32(0x32465754u); /* TWF2 */
			out_u32(ow);
			out_u32(oh);
			out_u32(0);
			out_u32((u32)scale);
			out_u32(yoff);
			out_u32(vi.xres);
			out_u32(vi.yres);
			if (out_flush() < 0)
				break;
			sleep_ms(fps > 0 ? (u32)(1000 / fps) : 30);
			continue;
		}

		/* RLE encode */
		for (u64 i = 0; i < (u64)ow * oh; i++) {
			u16 c = cur[i];
			if (runlen && c == runpix && runlen < 65535) {
				runlen++;
			} else {
				if (runlen)
					nrun++;
				runpix = c;
				runlen = 1;
			}
		}
		if (runlen)
			nrun++;

		out_u32(0x31465754u); /* TWF1 */
		out_u32(ow);
		out_u32(oh);
		out_u32(nrun);
		out_u32((u32)scale);
		out_u32(yoff);
		out_u32(vi.xres);
		out_u32(vi.yres);

		runpix = 0;
		runlen = 0;
		for (u64 i = 0; i <= (u64)ow * oh; i++) {
			u16 c = (i == (u64)ow * oh) ? 0xffff : cur[i]; /* sentinel */
			int end = (i == (u64)ow * oh);
			if (!end && (runlen == 0 || (c == runpix && runlen < 65535))) {
				runpix = c;
				runlen++;
			} else {
				out_u16((u16)runlen);
				out_u16(runpix);
				runpix = c;
				runlen = 1;
			}
		}
		if (out_flush() < 0)
			break;

		{
			u64 n = (u64)ow * oh;
			for (u64 i = 0; i < n; i++)
				prev[i] = cur[i];
		}
		have_prev = 1;
		sleep_ms(fps > 0 ? (u32)(1000 / fps) : 30);
	}
	return 0;
}

/* ---- entry ------------------------------------------------------------ */

void cstart(u64 *sp)
{
	int argc = (int)sp[0];
	char **argv = (char **)(sp + 1);
	const char *fbpath = "/dev/graphics/fb0";
	int scale = 2;
	int fps = 30;
	int i;

	for (i = 1; i < argc; i++) {
		if (str_eq(argv[i], "--inject")) {
			if (i + 1 < argc) {
				SYSCALL(SYS_exit, inject_mode(argv[i + 1]), 0, 0, 0, 0, 0);
				return;
			}
		} else if (str_pref(argv[i], "--scale=")) {
			scale = (int)parse_int(argv[i] + 8, 2);
		} else if (str_pref(argv[i], "--fps=")) {
			fps = (int)parse_int(argv[i] + 6, 30);
		} else if (str_pref(argv[i], "--fb=")) {
			fbpath = argv[i] + 5;
		}
	}

	SYSCALL(SYS_exit, capture_mode(fbpath, scale, fps), 0, 0, 0, 0, 0);
}
