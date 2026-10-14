# Aura apps

The Python scraper remains the content-ingestion service under `src/scraper`.
The product UI lives in this workspace:

```text
apps/
  web/       React + Vite responsive desktop/tablet/mobile feed
packages/
  shared/    feed types, scraped-document adapter, Interest DNA logic, demo data
```

## Run the web app

From the repository root:

```bash
pnpm install
pnpm dev:web
```

The dev server is available at `http://localhost:5173`. Create a production
bundle with `pnpm build:web`; run the shared package typecheck with
`pnpm typecheck:shared`.

## Prototype boundaries

- The Interest DNA mapper is a small, deterministic keyword model. It is
  intentionally dependency-free so a future mobile client can reuse it; it is
  not a hosted embedding model or an LLM call.
- The browser demo stores its editable profile, locally created posts, and
  collection in `localStorage`.
- `mapScrapedDocumentToPost()` adapts the existing scraper's canonical
  `ContentDocument` shape. The current Python repository has a CLI and MongoDB
  store, but no HTTP feed API, account service, or OpenGraph proxy; this patch
  does not pretend those services exist.
- Link previews detect Substack, X, and Reddit from a valid URL and show a
  platform-styled fallback card. Real OpenGraph/OEmbed metadata needs a
  server-side preview endpoint before it can be fetched reliably.

The web app is a demo-ready surface; the Expo client, account sync, remote
writes, real AI explanations, and server-generated embed metadata remain later
work.
