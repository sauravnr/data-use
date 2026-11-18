// Notices (in-app announcements) and push actions: the rules shared by the app
// (announcementsStore.js) and the publishing script (scripts/notices.mjs).
// Plain JavaScript with no React Native imports, so Node can load it too.
//
// File: data-use/data/announcements.json
//   { "version": 3, "updatedAt": "2026-12-20", "items": [ …notice… ], "signature": "…" }
// The signature is Ed25519 over canonicalJson({ version, updatedAt, items }),
// made with the private key that only exists on the owner's PC. The app holds
// the public key and ignores a file whose signature doesn't match.
//
// A notice:
//   id            "maghe-2083"           lowercase letters, digits, dashes
//   kind          "line" | "banner" | "popup"
//   start, end    "2083-09-28"           BS dates in Nepal, both days included
//   title         { "ne": "…", "en": "…" }   at least one language
//   body          { "ne": "…", "en": "…" }   banner and popup only (optional)
//   button        { "ne": "…", "en": "…" }   link text on a banner, button on a popup
//   image         "images/banners/maghe-2083.webp"   banner and popup only
//   tone          "holiday"              line only: red, for holidays
//   style         "picture"              popup only: the picture fills the popup (a poster,
//                                        4:5) with a close button and the link button; the
//                                        title isn't shown, it labels the popup for screen readers
//   action        "day:2083/9/14" | "festival:Maghe Sankranti" | "screen:weather" | "web:/privacy"
//   lang          "all" | "ne" | "en"    who sees it, by app language (default all)
//   minAppVersion "1.6.0"                older apps skip it

export const NOTICE_KINDS = ['line', 'banner', 'popup'];

// Screens a notice or a push can open. Names match MoreScreen's sub-screens,
// plus the bottom tabs.
export const NOTICE_SCREENS = [
  'calendar', 'rashifal', 'news', 'more',
  'converter', 'weather', 'goldSilver', 'unit', 'fuel', 'vegetables', 'forex',
  'muhurat', 'upcoming', 'radio', 'reminders', 'settings',
];

export const WEB_ORIGIN = 'https://sahajpatro.web.app';
export const IMAGE_BASE = 'https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/';

export const LIMITS = { title: 80, body: 300, button: 30, items: 20, festival: 60 };

const ID_RE = /^[a-z0-9][a-z0-9-]{0,47}$/;
const IMAGE_RE = /^images\/banners\/[a-z0-9][a-z0-9-]{0,80}\.(webp|jpg|jpeg|png)$/;
const BS_RE = /^(\d{4})-(\d{1,2})-(\d{1,2})$/;
const VERSION_RE = /^\d+\.\d+\.\d+$/;
const WEB_PATH_RE = /^\/[A-Za-z0-9._~\-/]*$/;
const KNOWN_KEYS = new Set([
  'id', 'kind', 'start', 'end', 'title', 'body', 'button', 'image', 'tone',
  'action', 'lang', 'minAppVersion', 'style',
]);

// ---------- dates ----------

// "2083-09-28" -> 20830928, or null.
export function bsKey(s) {
  const m = typeof s === 'string' ? BS_RE.exec(s) : null;
  if (!m) return null;
  const y = +m[1], mo = +m[2], d = +m[3];
  if (y < 2000 || y > 2200 || mo < 1 || mo > 12 || d < 1 || d > 32) return null;
  return y * 10000 + mo * 100 + d;
}

export function bsKeyOf({ year, month, day }) {
  return year * 10000 + month * 100 + day;
}

// ---------- actions ----------

// "screen:weather" -> { type: 'screen', screen: 'weather' }, or null when it
// isn't one of the allowed forms. Never a free URL.
export function parseAction(str) {
  if (typeof str !== 'string') return null;
  const i = str.indexOf(':');
  if (i < 1) return null;
  const type = str.slice(0, i).trim();
  const arg = str.slice(i + 1).trim();
  if (type === 'day') {
    const m = /^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/.exec(arg);
    if (!m) return null;
    const year = +m[1], month = +m[2], day = +m[3];
    if (month < 1 || month > 12 || day < 1 || day > 32) return null;
    return { type, year, month, day };
  }
  if (type === 'festival') {
    if (!arg || arg.length > LIMITS.festival) return null;
    return { type, name: arg };
  }
  if (type === 'screen') {
    return NOTICE_SCREENS.includes(arg) ? { type, screen: arg } : null;
  }
  if (type === 'web') {
    if (!WEB_PATH_RE.test(arg) || arg.includes('..') || arg.includes('//')) return null;
    return { type, url: WEB_ORIGIN + arg };
  }
  return null;
}

// ---------- text ----------

// The text for this language, falling back to the other one.
export function pickText(obj, lang) {
  if (!obj || typeof obj !== 'object') return '';
  const other = lang === 'ne' ? 'en' : 'ne';
  return (typeof obj[lang] === 'string' && obj[lang]) || (typeof obj[other] === 'string' && obj[other]) || '';
}

function textProblem(obj, max, field, allowNewlines) {
  if (obj === undefined) return null;
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return `${field} must be { "ne": "…", "en": "…" }`;
  const langs = Object.keys(obj);
  if (!langs.length) return `${field} is empty`;
  for (const k of langs) {
    if (k !== 'ne' && k !== 'en') return `${field} has an unknown language "${k}"`;
    const v = obj[k];
    if (typeof v !== 'string' || !v.trim()) return `${field}.${k} is empty`;
    if (v.length > max) return `${field}.${k} is ${v.length} characters (at most ${max})`;
    // eslint-disable-next-line no-control-regex
    const bad = allowNewlines ? /[\u0000-\u0009\u000B-\u001F]/ : /[\u0000-\u001F]/;
    if (bad.test(v)) return `${field}.${k} has a control character${allowNewlines ? '' : ' or a line break'}`;
    if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(^|[^\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(v)) {
      return `${field}.${k} has a broken character`;
    }
  }
  return null;
}

// ---------- validation ----------

// Problems with one notice, as readable sentences (empty when it's fine).
export function noticeProblems(item) {
  const p = [];
  if (!item || typeof item !== 'object' || Array.isArray(item)) return ['a notice must be an object'];
  if (!ID_RE.test(item.id || '')) p.push('id must be lowercase letters, digits and dashes (at most 48)');
  if (!NOTICE_KINDS.includes(item.kind)) p.push(`kind must be one of ${NOTICE_KINDS.join(', ')}`);
  const s = bsKey(item.start), e = bsKey(item.end);
  if (s == null) p.push('start must be a BS date like 2083-09-28');
  if (e == null) p.push('end must be a BS date like 2083-09-28');
  if (s != null && e != null && s > e) p.push('start is after end');
  if (item.title === undefined) p.push('title is missing');
  for (const [field, max, nl] of [['title', LIMITS.title, false], ['body', LIMITS.body, true], ['button', LIMITS.button, false]]) {
    const t = textProblem(item[field], max, field, nl);
    if (t) p.push(t);
  }
  if (item.image !== undefined) {
    if (item.kind === 'line') p.push('a line notice has no picture');
    else if (!IMAGE_RE.test(item.image)) p.push('image must be like images/banners/maghe-2083.webp');
  }
  if (item.body !== undefined && item.kind === 'line') p.push('a line notice has no body, only a title');
  if (item.style !== undefined) {
    if (item.kind !== 'popup' || item.style !== 'picture') p.push('style is only for popups: "picture"');
    else if (item.image === undefined) p.push('a picture popup needs a picture');
  }
  if (item.tone !== undefined && !(item.kind === 'line' && (item.tone === 'holiday' || item.tone === 'teal'))) {
    p.push('tone is only for line notices: "holiday" or "teal"');
  }
  if (item.action !== undefined && !parseAction(item.action)) {
    p.push('action must be day:2083/9/14, festival:<English name>, screen:<name> or web:/<path>');
  }
  if (item.lang !== undefined && !['all', 'ne', 'en'].includes(item.lang)) p.push('lang must be all, ne or en');
  if (item.minAppVersion !== undefined && !VERSION_RE.test(item.minAppVersion)) p.push('minAppVersion must be like 1.6.0');
  for (const k of Object.keys(item)) if (!KNOWN_KEYS.has(k)) p.push(`unknown field "${k}"`);
  return p;
}

// Problems with the whole file (without the signature check).
export function fileProblems(file) {
  const p = [];
  if (!file || typeof file !== 'object' || Array.isArray(file)) return ['the file must be a JSON object'];
  if (!Number.isInteger(file.version) || file.version < 1) p.push('version must be a whole number from 1');
  if (typeof file.updatedAt !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(file.updatedAt)) p.push('updatedAt must be like 2026-12-20');
  if (!Array.isArray(file.items)) return [...p, 'items must be a list'];
  if (file.items.length > LIMITS.items) p.push(`at most ${LIMITS.items} notices`);
  const ids = new Set();
  file.items.forEach((item, i) => {
    noticeProblems(item).forEach(x => p.push(`notice ${i + 1} (${item && item.id ? item.id : 'no id'}): ${x}`));
    if (item && item.id) {
      if (ids.has(item.id)) p.push(`notice id "${item.id}" is used twice`);
      ids.add(item.id);
    }
  });
  return p;
}

// ---------- which notices to show ----------

export function compareVersions(a, b) {
  const pa = String(a).split('.').map(n => parseInt(n, 10) || 0);
  const pb = String(b).split('.').map(n => parseInt(n, 10) || 0);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) < (pb[i] || 0) ? -1 : 1;
  }
  return 0;
}

// Notices that apply today, in file order. Items that fail validation are
// skipped one by one, so one bad notice can't hide the others.
export function activeNotices(items, { todayKey, lang, appVersion }) {
  if (!Array.isArray(items)) return [];
  return items.filter(item => {
    if (noticeProblems(item).length) return false;
    if (todayKey < bsKey(item.start) || todayKey > bsKey(item.end)) return false;
    if (item.lang && item.lang !== 'all' && item.lang !== lang) return false;
    if (item.minAppVersion && appVersion && compareVersions(appVersion, item.minAppVersion) < 0) return false;
    return !!pickText(item.title, lang);
  });
}

// ---------- signing ----------

// JSON with object keys sorted at every level and no spaces, so the signer and
// the app produce the same bytes. Only whole numbers are allowed.
export function canonicalJson(v) {
  if (v === null) return 'null';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') {
    if (!Number.isInteger(v)) throw new Error('only whole numbers can be signed');
    return String(v);
  }
  if (typeof v === 'string') return JSON.stringify(v);
  if (Array.isArray(v)) return '[' + v.map(canonicalJson).join(',') + ']';
  if (typeof v === 'object') {
    const keys = Object.keys(v).filter(k => v[k] !== undefined).sort();
    return '{' + keys.map(k => JSON.stringify(k) + ':' + canonicalJson(v[k])).join(',') + '}';
  }
  throw new Error(`can't sign a ${typeof v}`);
}

export function signedText(file) {
  return canonicalJson({ version: file.version, updatedAt: file.updatedAt, items: file.items });
}

export function utf8Bytes(str) {
  const out = [];
  for (let i = 0; i < str.length; i++) {
    let c = str.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < str.length) {
      const n = str.charCodeAt(i + 1);
      if (n >= 0xdc00 && n <= 0xdfff) { c = 0x10000 + ((c - 0xd800) << 10) + (n - 0xdc00); i++; }
    }
    if (c < 0x80) out.push(c);
    else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
    else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
  }
  return Uint8Array.from(out);
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

export function toBase64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i], b = bytes[i + 1], c = bytes[i + 2];
    s += B64[a >> 2] + B64[((a & 3) << 4) | ((b ?? 0) >> 4)]
      + (b === undefined ? '=' : B64[((b & 15) << 2) | ((c ?? 0) >> 6)])
      + (c === undefined ? '=' : B64[c & 63]);
  }
  return s;
}

// null when the text isn't valid base64.
export function fromBase64(str) {
  if (typeof str !== 'string' || str.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(str)) return null;
  const out = [];
  for (let i = 0; i < str.length; i += 4) {
    const n = [0, 1, 2, 3].map(k => (str[i + k] === '=' ? 0 : B64.indexOf(str[i + k])));
    const v = (n[0] << 18) | (n[1] << 12) | (n[2] << 6) | n[3];
    out.push((v >> 16) & 255);
    if (str[i + 2] !== '=') out.push((v >> 8) & 255);
    if (str[i + 3] !== '=') out.push(v & 255);
  }
  return Uint8Array.from(out);
}

// True when `file` carries a valid signature from `publicKeyB64`.
// `nacl` is the tweetnacl module (passed in so this file stays plain JS).
export function verifySignature(nacl, file, publicKeyB64) {
  try {
    const sig = fromBase64(file && file.signature);
    const key = fromBase64(publicKeyB64);
    if (!sig || sig.length !== 64 || !key || key.length !== 32) return false;
    return nacl.sign.detached.verify(utf8Bytes(signedText(file)), sig, key);
  } catch (e) {
    return false;
  }
}
