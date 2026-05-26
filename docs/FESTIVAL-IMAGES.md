# Adding festival images and descriptions

This guide explains how to replace the placeholder thumbnails with real festival images, and how to add new festivals with content.

## Where everything lives

| File | What it does |
|---|---|
| `src/data/festivals.json` | Festival **dates** — when each festival occurs, whether it's a holiday |
| `src/data/festivalContent.json` | Festival **content** — image URLs, descriptions, sources |
| `src/utils/festivalContent.js` | Maps a festival entry → its content (via slug or `nameEn` lookup) |

`festivals.json` stays light (dates only). All the heavy content sits in `festivalContent.json`, keyed by **slug**. One slug is shared across all yearly occurrences — e.g. all Dashain dates point to the single `dashain` content entry.

## Image hosting — the recommended path

Use **GitHub + jsDelivr**. It's free, fast, globally CDN-cached, no infrastructure to maintain.

### Step 1 — get the image

Download a festival photo you have rights to use. Good sources:

- **Wikimedia Commons** — `https://commons.wikimedia.org/` — search "Dashain", "Tihar", etc. Most photos are CC-BY-SA (free with attribution).
- **Unsplash** — `https://unsplash.com/` — search "festival", "diwali", "nepal". Free, no attribution required.
- **Your own photos** — best long-term: photograph festivals yourself.

### Step 2 — resize it

Two sizes per festival:

| Use | Size | File-size budget | Where it appears |
|---|---|---|---|
| Thumbnail | 400×400 (square) | ~30 KB | DayDetail festival banner |
| Hero | 1600×900 (landscape) | ~150 KB | FestivalDetailScreen (Phase 2) |

Save as **.jpg quality 80–85**. Tools that work:

- **squoosh.app** (free, browser-based, very good)
- **ImageMagick** CLI: `magick input.jpg -resize 400x400^ -gravity center -crop 400x400+0+0 -quality 82 dashain-thumb.jpg`
- **TinyPNG / TinyJPG** — even smaller without quality loss

### Step 3 — upload to the data-use repo

Your data-use GitHub repo (`https://github.com/sauravnr/data-use`) is what the app already fetches data from. Add an `images/festivals/` folder there:

```
data-use/
└── images/
    └── festivals/
        ├── dashain-thumb.jpg
        ├── dashain-hero.jpg
        ├── tihar-thumb.jpg
        ├── tihar-hero.jpg
        └── ...
```

Commit and push. **Done — no build step.** jsDelivr automatically serves them.

### Step 4 — get the public URL

jsDelivr URL pattern:

```
https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/images/festivals/<filename>
```

Example for `dashain-thumb.jpg`:

```
https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/images/festivals/dashain-thumb.jpg
```

Open it in a browser — should show the image. If you get 404, the file isn't on `main` yet (push didn't go through).

**Cache warning:** jsDelivr caches for ~12 hours per file path. If you replace an image, either:
- Wait 12 hours, OR
- Bump the URL with a version suffix: `dashain-thumb-v2.jpg`, OR
- Use the explicit purge URL: `https://purge.jsdelivr.net/gh/sauravnr/data-use@main/images/festivals/dashain-thumb.jpg`

### Step 5 — update festivalContent.json

Open `src/data/festivalContent.json` in the app repo. Find the festival's slug and replace the `thumbnail` and `hero` URLs:

```json
"dashain": {
  "slug": "dashain",
  "thumbnail": "https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/images/festivals/dashain-thumb.jpg",
  "hero": "https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/images/festivals/dashain-hero.jpg",
  ...
}
```

Bump the top-level `version` field by 1 so cached copies refresh:

```json
{
  "version": 2,
  ...
}
```

Commit + push. Next time users open the app, they get the new images (currently the app uses bundled content, so technically a release is needed — see "Remote vs bundled" below).

## Adding a brand-new festival

If the festival is already in `festivals.json` (just missing content) — skip to step 3.

### 1. Add the date to `src/data/festivals.json`

```json
{
  "bsYear": 2083,
  "bsMonth": 7,
  "bsDay": 15,
  "name": "नयाँ चाड",
  "nameEn": "New Festival",
  "type": "festival",
  "holiday": false
}
```

### 2. Pick a slug

Lowercase, hyphens for spaces, ASCII only. Examples:

- "Buddha Jayanti" → `buddha-jayanti`
- "Maha Shivaratri" → `maha-shivaratri`
- "Janai Purnima / Raksha Bandhan" → `janai-purnima`

Use the **same slug for every yearly occurrence**. The mapping table in `src/utils/festivalContent.js` handles multi-day festivals like Dashain and Tihar — point all sub-day entries to the parent slug.

### 3. Add a content block to `src/data/festivalContent.json`

```json
"new-festival": {
  "slug": "new-festival",
  "thumbnail": "https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/images/festivals/new-festival-thumb.jpg",
  "hero": "https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/images/festivals/new-festival-hero.jpg",
  "description": {
    "ne": "नेपालीमा विवरण...",
    "en": "Description in English..."
  },
  "sources": [
    { "label": "Wikipedia", "url": "https://en.wikipedia.org/wiki/..." }
  ]
}
```

### 4. Add slug mapping in `src/utils/festivalContent.js`

Open the `NAME_TO_SLUG` table and add the festival's `nameEn` → slug:

```js
const NAME_TO_SLUG = {
  ...
  'New Festival': 'new-festival',
};
```

This is what bridges the date in `festivals.json` to the content in `festivalContent.json`.

## Description guidelines

- **Length:** 2–4 sentences. The DayDetail banner shows the full text. Long enough to be useful, short enough not to overwhelm.
- **Both languages:** always provide `ne` and `en`. If you only have one, the app falls back automatically, but write both when you can.
- **Tone:** factual, no opinion, no "celebrate joyfully!" filler.
- **Cover:** what the festival commemorates, when it happens, one or two key rituals.

## Sources

Always cite a source (`sources` array). The UI shows a small "Wikipedia · ..." line at the bottom of the description card. Phase 2 will turn these into tappable links.

## Remote vs bundled content

Right now `festivalContent.json` is **bundled in the app build**. Updates require an app release.

Phase 2 plan (not built yet):
- Same pattern as `festivalsStore.js` — bundle a baseline, fetch a newer version from `https://cdn.jsdelivr.net/gh/sauravnr/data-use@main/data/festivalContent.json` on launch, cache in AsyncStorage.
- Bumping the top-level `version` field is what triggers users to download the new copy.

Until that's wired up, treat `festivalContent.json` like code: changes need a release.

## Testing locally

1. Edit `festivalContent.json` (or upload an image and update its URL).
2. Reload the app (Metro bundler picks up JSON changes on save).
3. Open a day that has the festival.
4. The banner should show the new thumbnail. If it shows the colored fallback icon, the slug isn't mapped — check `NAME_TO_SLUG` in `festivalContent.js`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Banner shows colored icon, not image | Slug not in `NAME_TO_SLUG` or content entry missing |
| Image area shows gray box, no image | Wrong URL — open it in browser to confirm |
| Image broken after re-upload | jsDelivr cache — wait 12 h, version the filename, or use `purge.jsdelivr.net` |
| Description doesn't show | `description.ne` or `description.en` field missing |
| Description shows English in Nepali mode | `description.ne` not provided — fix in JSON |
