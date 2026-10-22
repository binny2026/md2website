# md2website

Turn a Markdown documentation project (multi-chapter tutorials, notes, course materials, handbooks) into a static documentation site, with one-command deployment to a remote server.

## Install from a desktop agent

In Trae CN, Codex, Claude Code or any similar desktop agent, just send the repository URL:

```
Install this skill: https://github.com/binny2026/md2website
```

The agent clones the repo and runs `./install.sh`. Without a TTY the script installs into **every detected agent directory**, so the calling agent can load it too.

Start a new session (or refresh the skill list) after installation.

Or hand it the full command:

```bash
git clone git@github.com:binny2026/md2website.git ~/md2website && cd ~/md2website && ./install.sh --all
```

## Why a dedicated tool

The site engine compiles every `.md` file as a **Vue Single-File Component**. Real-world Markdown notes almost always contain patterns that Vue misinterprets:

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
git clone <repo-url> md2website
cd md2website
./install.sh
```

`install.sh` detects installed desktop agents and lets you pick one or more targets:

```
  1  Trae CN      ~/.trae-cn/skills
  2  Trae         ~/.trae/skills
  3  Codex        ~/.codex/skills
  4  Claude Code  ~/.claude/skills
  5  WorkBuddy    ~/.workbuddy/skills
  6  Custom Path
```

- Multi-select with `1 3 5`, `1,3,5` or a range such as `1-3`; `a` = all, `q` = cancel.
- **Enter** updates the directories that are already installed (on a fresh machine it defaults to every usable directory).
- Agents whose `skills` directory does not exist are skipped — the installer never creates directories behind your back.
- Each selected directory receives a full copy of the skill.

Non-interactive runs (agents, CI, pipes) without arguments install into **every detected agent directory** (equivalent to `--all`), so the agent that ran the installer can load the skill too. Use `--dir` to target a single directory.

Other flags:

```bash
./install.sh --all              # install into every detected agent, no prompt
./install.sh --list             # show detected agents and status only
./install.sh --dir <path>       # explicit target, repeatable
./install.sh --yes              # skip the confirmation prompt
./install.sh --check            # verify the environment only
```

Uninstall:

```bash
./install.sh --uninstall                       # remove the current copy
./install.sh --uninstall --all                 # remove every detected copy
./install.sh --uninstall --dir <path>          # remove one explicit directory
```

`--uninstall --all` only scans the five known agent directories; custom `--dir` copies must be removed explicitly. Deployment profiles in `~/.workbuddy/deploy-profiles/` are never deleted.

The examples below use `~/.workbuddy/skills/md2website`; replace it with your actual install path (printed at the end of installation).

Run a quick self-check anytime:

```bash
python3 scripts/_env.py
```

## Quick start

### Use from an agent (recommended)

After installing and starting a new session, just tell the agent "turn this folder into a documentation site" (or name the source explicitly):

```
Use Skill: md2website /path/to/md-folder generate the site
```

The agent handles scan → generate → build → preview for you.

### One-click (script)

```bash
# After installing, copy the entry point into your Markdown folder
cp assets/build.sh ~/my-notes/
cd ~/my-notes && ./build.sh        # or double-click it in Finder
```

It runs the whole pipeline: environment check → chapter scan → site generation → `npm install` → build → open browser. No arguments, no config.

Want to choose the title and output location? Use `./build.sh --wizard`.

### Step by step

```bash
SKILL=~/.workbuddy/skills/md2website

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

Server credentials are stored **per site** in `.deploy-local.yml` inside the generated site directory (mode 600, ignored by `.gitignore`). Nothing sensitive is committed or uploaded.

```bash
# Generate the site, then configure it interactively
cd ~/notes/demo-site
python3 ~/.workbuddy/skills/md2website/scripts/profile.py wizard --project "$(pwd)"

# Verify, then deploy (deploy.sh also starts the wizard when no config exists)
./deploy.sh --dry-run
./deploy.sh
```

The wizard has **no prefilled defaults**: host, user, SSH port, remote directory and site base must all be entered explicitly. Provide either a password or an SSH key.

One-time key setup (replace the user and host with your own):

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@doc.example.com
```

`deploy.sh` builds, packs with tar, uploads via scp, extracts remotely, and cleans only files recorded in the previous deployment manifest — anything else you put on the server is left alone.

Options: `--profile <name>` (use another server), `--no-build`, `--dry-run`.

## Updating an existing site

Say "update the site" to your agent, or run:

```bash
python3 ~/.workbuddy/skills/md2website/scripts/sites.py list   # discover sites
python3 ~/.workbuddy/skills/md2website/scripts/update.py       # pick interactively when several exist
python3 ~/.workbuddy/skills/md2website/scripts/update.py "<site-dir>" --deploy
```

Each site records its source directory in `.md2website.json`; the global registry lives in `~/.md2website/sites.json`. Updates rebuild in place (new chapters are added to the sidebar automatically), back up `docs/.vitepress` to `.backup/`, and keep `.deploy-local.yml` plus `node_modules`. Building is the default; `--deploy` publishes.

## Scripts

| Script | Purpose | Modifies files |
| --- | --- | --- |
| `scan.py` | Detect Vue syntax conflicts and missing images | No |
| `fix.py` | Rewrite `<img>` tags, correct image paths | Yes (`--dry-run` to preview) |
| `init.py` | Generate a complete documentation site project | Only the new output dir |
| `sites.py` | Find generated sites (`list` / `select`) | No |
| `update.py` | Rebuild an existing site from its recorded source, then build | Site dir, backup in `.backup/` |
| `profile.py` | Manage per-site config and optional deployment profiles | `.deploy-local.yml` or `~/.workbuddy/deploy-profiles/` |
| `_env.py` | Environment detection (Python / Node) | No |
| `assets/build.sh` | One-click entry: scan → generate → install → build → preview | Output dir only |
| `assets/deploy.sh` | Build, pack, upload, extract | Local temp package |

## Key concept: SITE_BASE

Generated assets use absolute paths (`/assets/...`):

| Deployment location | SITE_BASE |
| --- | --- |
| `https://doc.example.com/` | `/` (required, no default) |
| `https://example.com/docs/` | `/docs/` (pass `--base` at generation time) |

Wrong value means pages load but styles and images 404.

## License

MIT
