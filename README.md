# tiktok-ideas-extractor

One command on Windows takes every clip of a TikTok account, reads the on-screen subtitles with OCR and writes a compact text file. Paste that file into Claude to extract the suggestions. No video or image stays on disk.

## Install (once, PowerShell)

```powershell
winget install Gyan.FFmpeg UB-Mannheim.TesseractOCR
# 64-bit Python 3.12+ is required (curl_cffi has no 32-bit wheels)
py -3 -c "import struct; print(struct.calcsize('P') * 8)"   # must print 64
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Open a new terminal afterwards so `ffmpeg` is on PATH. If Tesseract is not found, set `tesseract_cmd` in `config.yaml`.

## Use the page

```powershell
.\.venv\Scripts\python.exe tiktok_ideas.py ui
```

The page opens in your browser. Enter the account, press **Run** (optionally with a limit), watch the progress, press **Export** at the end and **Copy** to paste the export into Claude. **Stop** finishes the current clip and ends the run. Keep the terminal window open while you use the page; Ctrl+C there closes it. Add `&a=<account>` to the link to open it with the account filled in.

## Use the terminal

In PowerShell an unquoted `@name` is dropped (splatting), so write the account without `@` or quote it: `'@name'`.

| Command | What it does |
|---|---|
| `.\.venv\Scripts\python.exe tiktok_ideas.py run name` | Process every new clip of the account |
| `... run name --limit 5` | Only the 5 newest unprocessed clips (testing, crop calibration) |
| `... export name` | Write unexported transcripts to `data/exports/` and mark them exported |
| `... status name` | Counts: listed, processed (low text), unexported, exported, failed, pending |
| `... reset name --failed` | Put failed clips back in the queue |

Ctrl+C is safe: the current clip stays queued and `work/` is emptied on the next run.

## Configure

Everything that varies between accounts is in `config.yaml` (subtitle `crop`, `fps`, `min_confidence`, ...). To calibrate the crop, run with `--limit 5`, read the transcripts in `data/transcripts/<account>/`, adjust `crop` and run again on fresh clips.

## When TikTok breaks

1. `.\.venv\Scripts\python.exe -m pip install -U "yt-dlp[default,curl-cffi]"`
2. Set `cookies_from_browser: chrome` (or another browser) in `config.yaml`.

## Drive it by script (ctl)

Start the page with `ui --ctl`, then send command lines from another terminal:

```powershell
.\.venv\Scripts\python.exe tiktok_ideas_ctl.py "run youraccount 5" wait "status youraccount"
```

`help` lists the commands. The page's buttons send the same lines. Details: `.claude/skills/tiktok-ideas/SKILL.md`.

## Develop

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Tests that need ffmpeg or Tesseract are skipped when the tool is missing. See [docs/architecture.md](docs/architecture.md).
