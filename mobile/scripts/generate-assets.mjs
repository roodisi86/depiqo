#!/usr/bin/env node
// Generates PLACEHOLDER app icons, adaptive icons, splash and notification icon in assets/, using only
// Node's built-in modules (a minimal PNG encoder on top of zlib). The Depiqo mark (brand/depiqo-mark.svg:
// a ring, a vertical bar and a teal dot) is drawn with 4x4 supersampling on deep navy.
// Development and staging icons get a coloured band with DEV / STG so you can tell the apps apart.
//
// These are placeholders. Replace them with designed assets before a store release (see docs/STORE-CHECKLIST.md).
//
//   node scripts/generate-assets.mjs
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateSync } from 'node:zlib';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'assets');
mkdirSync(OUT, { recursive: true });

const NAVY = [0x10, 0x21, 0x39, 255];
const WHITE = [255, 255, 255, 255];
const TEAL_ON_DARK = [0x22, 0xb8, 0xa8, 255];
const TEAL = [0x13, 0x8e, 0x83, 255];
const AMBER = [0xf5, 0xa6, 0x23, 255];
const CLEAR = [0, 0, 0, 0];

// ------------------------------------------------------------ PNG encoder

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

/** RGBA by default; opaque=true writes RGB without an alpha channel (Apple rejects app icons with alpha). */
function encodePng(width, height, rgba, opaque = false) {
  const channels = opaque ? 3 : 4;
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = opaque ? 2 : 6; // RGB or RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const stride = width * channels + 1;
  const raw = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y += 1) {
    raw[y * stride] = 0; // filter: none
    for (let x = 0; x < width; x += 1) {
      const src = (y * width + x) * 4;
      const dst = y * stride + 1 + x * channels;
      raw[dst] = rgba[src];
      raw[dst + 1] = rgba[src + 1];
      raw[dst + 2] = rgba[src + 2];
      if (!opaque) raw[dst + 3] = rgba[src + 3];
    }
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// ------------------------------------------------------------ drawing

function canvas(w, h, bg) {
  const px = Buffer.alloc(w * h * 4);
  for (let i = 0; i < w * h; i += 1) px.set(bg, i * 4);
  return { w, h, px };
}

function blend(c, x, y, color, alpha) {
  if (alpha <= 0) return;
  const i = (y * c.w + x) * 4;
  const a = (color[3] / 255) * alpha;
  const da = c.px[i + 3] / 255;
  const outA = a + da * (1 - a);
  for (let k = 0; k < 3; k += 1) {
    const v = outA > 0 ? (color[k] * a + c.px[i + k] * da * (1 - a)) / outA : 0;
    c.px[i + k] = Math.round(v);
  }
  c.px[i + 3] = Math.round(outA * 255);
}

/** Fill a shape given by inside(x, y) in canvas pixels, with 4x4 supersampling. */
function fill(c, inside, color, box = [0, 0, c.w, c.h]) {
  const [x0, y0, x1, y1] = box.map((v) => Math.max(0, Math.round(v)));
  const S = 4;
  for (let y = y0; y < Math.min(y1, c.h); y += 1) {
    for (let x = x0; x < Math.min(x1, c.w); x += 1) {
      let hit = 0;
      for (let sy = 0; sy < S; sy += 1) for (let sx = 0; sx < S; sx += 1) if (inside(x + (sx + 0.5) / S, y + (sy + 0.5) / S)) hit += 1;
      blend(c, x, y, color, hit / (S * S));
    }
  }
}

/** The mark in viewBox units (0..64), drawn so its content box (11..53 x 6..58) is `size` px high, centred at (cx, cy). */
function drawMark(c, cx, cy, size, ink, dot) {
  const s = size / 52;
  const ox = cx - 32 * s;
  const oy = cy - 32 * s;
  const u = (x, y) => [(x - ox) / s, (y - oy) / s];
  const box = [ox + 8 * s, oy + 3 * s, ox + 56 * s, oy + 61 * s];
  fill(c, (x, y) => {
    const [vx, vy] = u(x, y);
    const d = Math.hypot(vx - 30, vy - 39);
    if (Math.abs(d - 15) <= 4) return true; // ring, stroke 8
    const cyy = Math.min(Math.max(vy, 10), 54); // bar from y 10 to 54, round caps
    return Math.hypot(vx - 49, vy - cyy) <= 4;
  }, ink, box);
  if (dot) {
    fill(c, (x, y) => {
      const [vx, vy] = u(x, y);
      return Math.hypot(vx - 30, vy - 39) <= 5.5;
    }, dot, box);
  }
}

// 5x7 bitmap letters for the DEV / STG badge.
const FONT = {
  D: ['11110', '10001', '10001', '10001', '10001', '10001', '11110'],
  E: ['11111', '10000', '10000', '11110', '10000', '10000', '11111'],
  V: ['10001', '10001', '10001', '10001', '10001', '01010', '00100'],
  S: ['01111', '10000', '10000', '01110', '00001', '00001', '11110'],
  T: ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
  G: ['01111', '10000', '10000', '10011', '10001', '10001', '01111'],
};

function drawText(c, text, cx, cy, cell, color) {
  const width = text.length * 6 * cell - cell;
  let x0 = Math.round(cx - width / 2);
  const y0 = Math.round(cy - 3.5 * cell);
  for (const ch of text) {
    const rows = FONT[ch];
    rows.forEach((row, ry) => {
      [...row].forEach((bit, rx) => {
        if (bit !== '1') return;
        for (let y = 0; y < cell; y += 1) for (let x = 0; x < cell; x += 1) blend(c, x0 + rx * cell + x, y0 + ry * cell + y, color, 1);
      });
    });
    x0 += 6 * cell;
  }
}

function band(c, color, label) {
  const h = Math.round(c.h * 0.2);
  fill(c, () => true, color, [0, c.h - h, c.w, c.h]);
  drawText(c, label, c.w / 2, c.h - h / 2, Math.round(h / 11), NAVY);
}

function save(name, c, opaque = false) {
  writeFileSync(join(OUT, name), encodePng(c.w, c.h, c.px, opaque));
  console.log(`assets/${name} ${c.w}x${c.h}${opaque ? ' (RGB, no alpha)' : ''}`);
}

// ------------------------------------------------------------ the assets

function icon(variant) {
  const c = canvas(1024, 1024, NAVY);
  const shift = variant ? -70 : 0;
  drawMark(c, 512, 512 + shift, variant ? 480 : 560, WHITE, TEAL_ON_DARK);
  if (variant === 'dev') band(c, TEAL_ON_DARK, 'DEV');
  if (variant === 'staging') band(c, AMBER, 'STG');
  return c;
}

function adaptive(variant) {
  // Foreground only; the background colour (navy) comes from app.config.ts. Keep the mark inside the
  // 66% safe zone, because launchers crop the outer part.
  const c = canvas(1024, 1024, CLEAR);
  drawMark(c, 512, variant ? 470 : 512, 400, WHITE, TEAL_ON_DARK);
  if (variant) {
    const label = variant === 'dev' ? 'DEV' : 'STG';
    drawText(c, label, 512, 700, 14, variant === 'dev' ? TEAL_ON_DARK : AMBER);
  }
  return c;
}

save('icon.png', icon(null), true);
save('icon-dev.png', icon('dev'), true);
save('icon-staging.png', icon('staging'), true);
save('adaptive-icon.png', adaptive(null));
save('adaptive-icon-dev.png', adaptive('dev'));
save('adaptive-icon-staging.png', adaptive('staging'));

const splash = canvas(512, 512, CLEAR);
drawMark(splash, 256, 256, 300, WHITE, TEAL_ON_DARK);
save('splash-icon.png', splash);

// Android notification icon: white silhouette on transparent (Android tints it with TEAL).
const notif = canvas(96, 96, CLEAR);
drawMark(notif, 48, 48, 72, WHITE, null);
save('notification-icon.png', notif);

// A small preview for docs and stores' internal testing pages.
const preview = canvas(256, 256, NAVY);
drawMark(preview, 128, 128, 140, WHITE, TEAL_ON_DARK);
save('favicon.png', preview, true);

void TEAL;
