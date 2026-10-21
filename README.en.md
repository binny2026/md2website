# md-to-vitepress

Turn a Markdown documentation project (multi-chapter tutorials, notes, course materials, handbooks) into a VitePress static site, with one-command deployment to a remote server.

## Why a dedicated tool

VitePress compiles every `.md` file as a **Vue Single-File Component**. Real-world Markdown notes almost always contain patterns that Vue misinterprets:

| Pattern | What Vue does | Result |
| --- | --- | --- |
| `<https://example.com>` | Treated as a component tag | `Element is missing end tag` |
| `{{ value }}` | Treated as interpolation | Compile error / lost content |
| `<img src="assets/x.png">` | Vite treats it as a **module import** | `Rollup failed to resolve import` |
| Wrong image extension | Path resolution fails | Build failure or silently missing images |

These are handled automatically: the generated `config.mjs` escapes Vue-conflicting syntax, and `fix.py` rewrites raw HTML image tags.

## Requirements

- **Python 3.8+**
- **Node.js 18+** (required for building)
- `tar`, `ssh`, `scp` (only for deployment)

## Install

```bash
git clone <repo-url> md-to-vitepress
cd md-to-vitepress
./install.sh
```

Installs to `~/.workbuddy/skills/md-to-vitepress` by default. Use `--dir <path>` to change, `--check` to only verify the environment, `--uninstall` to remove.

Run a quick self-check anytime:

```bash
python3 scripts/_env.py
```

## Quick start

### One-click (recommended)

```bash
# After installing, copy the entry point into your Markdown folder
cp assets/build.sh ~/my-notes/
cd ~/my-notes && ./build.sh        # or double-click it in Finder
```

It runs the whole pipeline: environment check → chapter scan → site generation → `npm install` → build → open browser. No arguments, no config.

Want to choose the title and output location? Use `./build.sh --wizard`.

### Step by step

```bash
SKILL=~/.workbuddy/skills/md-to-vitepress

# 1. Inspect the source docs (read-only)
python3 $SKILL/scripts/scan.py ~/my-notes

# 2. Generate the site
python3 $SKILL/scripts/init.py ~/my-notes --out ./my-doc-site --title "My Docs"

# 3. Build and preview
cd my-doc-site
npm install
npm run dev        # http://127.0.0.1:5174
```

Your source Markdown directory is **never modified** — everything is written to the output directory.

## What you get

- Sidebar navigation generated from chapter directories
- Per-page table of contents (h2 / h3)
- Local full-text search (`⌘K` / `Ctrl+K`)
- Syntax highlighting, line numbers, copy button for code blocks
- Light / dark theme
- Click-to-zoom images
- Prev / next page navigation

## Deployment

Server credentials are **not stored in the project**. Each project keeps a one-line `.deploy-profile` pointing to a profile in `~/.workbuddy/deploy-profiles/` (mode 600), so multiple projects stay isolated and nothing sensitive ends up in git.

```bash
# Create a profile
python3 $SKILL/scripts/profile.py set --name my-doc \
    HOST="doc.example.com" USER="root" \
    REMOTE_DIR="/www/wwwroot/doc.example.com" SITE_BASE="/"

# Bind it to this project
python3 $SKILL/scripts/profile.py bind --project . --name my-doc

# Verify, then deploy
./deploy.sh --dry-run
./deploy.sh
```

One-time key setup:

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub root@doc.example.com
```

`deploy.sh` builds, packs with tar, uploads via scp, extracts remotely, and cleans only files recorded in the previous deployment manifest — anything else you put on the server is left alone.

Options: `--profile <name>` (use another server), `--no-build`, `--dry-run`.

## Scripts

| Script | Purpose | Modifies files |
| --- | --- | --- |
| `scan.py` | Detect Vue syntax conflicts and missing images | No |
| `fix.py` | Rewrite `<img>` tags, correct image paths | Yes (`--dry-run` to preview) |
| `init.py` | Generate a complete VitePress project | Only the new output dir |
| `profile.py` | Manage deployment profiles | `~/.workbuddy/deploy-profiles/` |
| `_env.py` | Environment detection (Python / Node) | No |
| `assets/build.sh` | One-click entry: scan → generate → install → build → preview | Output dir only |
| `assets/deploy.sh` | Build, pack, upload, extract | Local temp package |

## Key concept: SITE_BASE

Generated assets use absolute paths (`/assets/...`):

| Deployment location | SITE_BASE |
| --- | --- |
| `https://doc.example.com/` | `/` (default) |
| `https://example.com/docs/` | `/docs/` (rebuild required) |

Wrong value means pages load but styles and images 404.

## License

MIT
