# tiktok-ideas-extractor

Windows CLI that lists every clip of a TikTok account, OCRs the on-screen subtitles and writes a compact text export to paste into Claude. Spec and plans: `docs/claude-plans/` (gitignored). Architecture: `docs/architecture.md`.

## Code map

- `tiktok_ideas.py`: CLI (`run`, `export`, `status`, `reset`, global `--config`). Exit codes 0 ok, 1 fatal, 2 usage, 130 Ctrl+C.
- `pipeline/config.py`: `Config` + `load_config` (unknown keys rejected, dirs relative to the config file).
- `pipeline/state.py`: SQLite `State`, `ClipInfo`, `ClipRow`. Statuses: pending, done, failed, exported, skipped (photo posts). Old DBs migrate on open.
- `pipeline/lister.py` / `downloader.py`: yt-dlp Python API; `base_options` holds the shared options (silent logger, cookies, impersonation).
- `pipeline/frames.py`, `ocr.py`, `cleaner.py`, `exporter.py`: one step each.
- `pipeline/runner.py`: per-clip loop; steps injected via `Steps` (fakes in `tests/test_runner.py`); `should_stop` for cooperative stop.
- `pipeline/report.py`: status/export/reset answers shared by CLI, page and ctl.
- `app/commands.py`: the line-based command language (the ctl). Page buttons and `tiktok_ideas_ctl.py` both send these lines to `POST /api/cmd`. A new feature = a new command here + help text + test + the skill.
- `app/jobs.py`: one background run, in-memory log. `app/server.py`: 127.0.0.1 server, token on every request, `ctl.json` only with `--ctl`. `app/static/index.html`: the page.
- `.claude/skills/tiktok-ideas/SKILL.md`: ctl cheat sheet, keep it in sync with `COMMANDS`.

## Running

- Use the 64-bit venv: `.\.venv\Scripts\python.exe` (the 32-bit system Python can't install `curl_cffi`, which TikTok needs).
- Tests: `.\.venv\Scripts\python.exe -m pytest`. ffmpeg/Tesseract tests skip if the tool is missing; a shell opened before the winget install needs its PATH refreshed.
- Manual runs go against a scratch config (`data_dir`/`work_dir` in a temp folder), never the repo's `data/`.
- PowerShell drops an unquoted `@name`: pass `name` or `'@name'`.

## Personal conventions

- Claude doesn't commit by default (side sessions and worktrees included) and doesn't offer to. When work is ready, give the user the commit message; the user commits, and Claude may check the result with read-only git (`git log`, `git show`, `git status`). Only when the user explicitly asks Claude to commit does Claude make that commit. Never push or merge. No `Co-Authored-By` or any Claude attribution in messages.
- Commit messages: `feat(<area>): ...`, `fix(<area>): ...`. Branches: `<area>/<feature>`, PRs into `main`.
- Claude may create and switch branches itself, from up-to-date `main`. Branches are broad and long-lived (several features/phases), not one per feature: the user commits on them at each milestone and merges rarely. Claude never merges; suggest a merge into `main` only at a real milestone (a coherent set of features done and verified), not after every feature.
- Planning stays out of the repo: per-feature plans go in `docs/claude-plans/` (gitignored), starting from `00-overview.md`. Update them as work happens (status, decisions, deviations).
- Documentation that helps a reader of the code goes IN the repo, under `docs/`: diagrams (Mermaid preferred, renders on GitHub), architecture notes, data models. Every few features, propose a new or updated diagram/doc when the structure changed.
- Keep `CLAUDE.md` files current as the code changes.
- Before handing a feature over for testing, run it end-to-end in the real app and click through it, not just type-check/build. Then list the exact steps the user must run.
- Tests and test data never touch the user's real data/files: separate buckets/DBs/folders, never bulk-clean shared storage.
- Everything user-facing is English (UI copy, messages, new code comments). Chat with the user may be in Romanian.
- Every app we build together has a ctl (`<app>-ctl`): a line-based command language over the app's own commands, plus built-ins for what needs a dialog or the mouse, a local opt-in endpoint (127.0.0.1 + token), a CLI and a repo skill (`.claude/skills/<app>/SKILL.md`). Build it with the first features and keep it current with every feature, in the same change: the feature must work from a script, `help` and the skill list it, and the ctl tests cover it. A feature isn't done until the ctl can drive it.
