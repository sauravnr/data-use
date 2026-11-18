// Sends one push notification to a Firebase topic. Run by
// .github/workflows/send-push.yml, which the admin page starts.
// Needs the FIREBASE_SERVICE_ACCOUNT secret (a push-only service account).
// No packages: the Google access token is made with Node's own crypto.
import crypto from 'node:crypto';
import { parseAction } from './noticesCore.mjs';

const TOPICS = ['test', 'all', 'ne', 'en'];
// Our pictures only: data-use/images on jsDelivr, at main or pinned to a commit
// (the admin page pins a just-uploaded picture so it works at once).
const IMAGE_RE = /^https:\/\/cdn\.jsdelivr\.net\/gh\/sauravnr\/data-use@(main|[0-9a-f]{7,40})\/images\/[A-Za-z0-9/_.-]+\.(webp|jpg|jpeg|png)$/;

function fail(msg) {
  console.log(`::error::${msg}`);
  process.exit(1);
}

const topic = (process.env.PUSH_TOPIC || '').trim();
const title = (process.env.PUSH_TITLE || '').trim();
const body = (process.env.PUSH_BODY || '').trim();
const image = (process.env.PUSH_IMAGE || '').trim();
const action = (process.env.PUSH_ACTION || '').trim();

if (!TOPICS.includes(topic)) fail(`topic must be one of ${TOPICS.join(', ')}`);
if (!title || title.length > 100) fail('title must be 1 to 100 characters');
if (!body || body.length > 500) fail('text must be 1 to 500 characters');
if (image && (!IMAGE_RE.test(image) || image.includes('..'))) fail('the picture must be one of ours on data-use');
if (action && !parseAction(action)) fail(`not an allowed action: ${action}`);

let sa;
try {
  sa = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT || '');
} catch (e) {
  fail('the FIREBASE_SERVICE_ACCOUNT secret is missing or broken');
}

const b64url = (buf) => Buffer.from(buf).toString('base64url');
const now = Math.floor(Date.now() / 1000);
const header = b64url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
const claims = b64url(JSON.stringify({
  iss: sa.client_email,
  scope: 'https://www.googleapis.com/auth/firebase.messaging',
  aud: 'https://oauth2.googleapis.com/token',
  iat: now,
  exp: now + 600,
}));
const signature = crypto.createSign('RSA-SHA256').update(`${header}.${claims}`).sign(sa.private_key);
const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion: `${header}.${claims}.${b64url(signature)}`,
  }),
});
if (!tokenRes.ok) fail(`Google login failed: ${tokenRes.status}`);
const { access_token: accessToken } = await tokenRes.json();

const message = {
  topic,
  notification: { title, body, ...(image ? { image } : {}) },
  android: {
    priority: 'normal',
    notification: { channel_id: 'announcements', ...(image ? { image } : {}) },
  },
  ...(action ? { data: { action } } : {}),
};
const res = await fetch(`https://fcm.googleapis.com/v1/projects/${sa.project_id}/messages:send`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ message }),
});
const text = await res.text();
if (!res.ok) fail(`Firebase refused it (${res.status}): ${text.slice(0, 300)}`);
console.log(`Sent to topic "${topic}": ${JSON.parse(text).name}`);
console.log(`### Sent to "${topic}"\n\n**${title}**\n\n${body}` + (action ? `\n\nTap: \`${action}\`` : ''));
