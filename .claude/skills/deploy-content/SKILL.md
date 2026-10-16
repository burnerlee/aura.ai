---
name: deploy-content
description: >-
  Deploy files or directories to the GCP content host via SSH/rsync.
  Use when the user says deploy, ship content, upload to GCP, push a video/site/artifact
  to the content server, or mentions content_aviral / 34.14.185.173.
---

# Deploy content (GCP)

All content ships to one host. Prefer `rsync` over `scp` (resume, deletes, dry-run).

## Host

| | |
|---|---|
| SSH | `ssh content_aviral@34.14.185.173` |
| User | `content_aviral` (passwordless sudo via `google-sudoers`) |
| Content root | `/home/content_aviral/content/` |
| Auth | Local SSH key; use `BatchMode=yes` in scripts |

Alias for commands below:

```bash
HOST=content_aviral@34.14.185.173
ROOT=/home/content_aviral/content
```

## Layout

```
~/content/
  <slug>/           # one folder per artifact or project
    ...files...
```

Pick a short slug (`brag-aura`, `demo-site`, `launch-mp4`). Never dump loose files into `~/content/` itself.

## Deploy workflow

1. Confirm what to ship and the remote slug.
2. Dry-run, then sync.
3. Verify with an SSH `ls` (and a public URL check if something is serving it).
4. Tell the user the remote path (and URL if known).

### Sync a directory

```bash
# dry-run first
rsync -avz --delete --dry-run ./local-dir/ "$HOST:$ROOT/<slug>/"

# real sync
rsync -avz --delete ./local-dir/ "$HOST:$ROOT/<slug>/"
```

Trailing slashes matter: `./local-dir/` → contents into `<slug>/`.

### Sync a single file

```bash
ssh "$HOST" "mkdir -p $ROOT/<slug>"
rsync -avz ./brag.mp4 "$HOST:$ROOT/<slug>/brag.mp4"
```

### Verify

```bash
ssh -o BatchMode=yes "$HOST" "ls -lah $ROOT/<slug>"
```

## What to exclude

Never sync secrets or junk:

- `.env`, `.env.*`, `*.pem`, `*.key`, credentials / service-account JSON
- `.git/`, `node_modules/`, `__pycache__/`, `.DS_Store`
- Local-only work dirs (`work/` frames, temp renders) unless the user asks

Example:

```bash
rsync -avz --delete \
  --exclude '.git' --exclude 'node_modules' --exclude '.env' --exclude 'work' \
  ./site/ "$HOST:$ROOT/<slug>/"
```

## Serving (optional)

The box may have no web server yet. If the user needs a URL:

1. Prefer whatever is already listening / reverse-proxied on the VM.
2. Otherwise ask before installing packages. With approval, nginx (or Caddy) can serve `$ROOT` under a path or vhost; user has passwordless `sudo`.
3. Quick one-off smoke test (not for production):

```bash
ssh "$HOST" "cd $ROOT/<slug> && python3 -m http.server 8080 --bind 127.0.0.1"
```

Do not leave ad-hoc servers running unless asked.

## Rules

- Always deploy under `$ROOT/<slug>/`, never system paths unless the user names one.
- Always dry-run destructive syncs (`--delete`) when replacing an existing slug.
- Do not commit deploy credentials; SSH agent / keys stay on the machine.
- After deploy, report: slug, remote path, byte/file summary from rsync, and any URL.
