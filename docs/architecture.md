# Architecture

One CLI (`tiktok_ideas.py`) over a `pipeline/` package with one module per step. `runner.py` drives the per-clip loop; every step is a plain function, injected through `runner.Steps` so tests can swap in fakes.

## Per-clip flow

```mermaid
flowchart TD
    L["1. lister.list_clips<br/>yt-dlp flat listing, no download"] --> S["2. state.add_listed / to_process<br/>new + failed with attempts &lt; 3, newest first"]
    S --> D["3. downloader.download<br/>smallest format with short side &ge; 720 → work/&lt;id&gt;/video.*"]
    D --> F["4. frames.extract_frames<br/>ffmpeg fps + crop → PNGs, near-duplicates skipped"]
    F --> O["5. ocr.ocr_frame<br/>gray, 2x, Otsu → Tesseract, words &lt; min_confidence dropped"]
    O --> C["6. cleaner.clean_lines<br/>fragments dropped, near-duplicate and progressive lines merged"]
    C --> W["7. data/transcripts/&lt;account&gt;/&lt;id&gt;.txt + state.mark_done"]
    W --> X["finally: work/&lt;id&gt;/ removed"]
    D -. error .-> E["state.mark_failed (attempts + 1)"] --> X
```

Leftover clip folders (`work/<numeric id>/`) are also removed at the start of every `run`, so an interrupted run leaves nothing behind for long. Only numeric folders are touched, so a mistaken `work_dir` can't wipe unrelated files.

## Clip states

```mermaid
stateDiagram-v2
    [*] --> pending: listed
    pending --> done: transcript saved
    pending --> failed: error
    failed --> done: retried, succeeded
    failed --> failed: retried, failed again (attempts < 3)
    failed --> pending: reset --failed
    done --> exported: export
```

A clip with 3 failed attempts stays `failed` and is skipped until `reset --failed`.

## Page and ctl

```mermaid
flowchart LR
    P["Browser page<br/>app/static/index.html"] -- "command lines + token" --> S["app/server.py<br/>127.0.0.1"]
    C["tiktok_ideas_ctl.py"] -- "same lines, token from data/ctl.json" --> S
    S --> K["app/commands.py<br/>run · stop · wait · state · log · status · export · reset · exports · help"]
    K --> J["app/jobs.py<br/>one background run, log"] --> R["pipeline.runner.run_account"]
    K --> T["pipeline.report<br/>status / export / reset text"]
```

The page polls `GET /api/poll` (state + new log lines) every second; everything else goes through `POST /api/cmd`, so the page can do nothing the ctl can't.

## Data

`data/state.db` (SQLite), table `clips`: `id` (TikTok id, time-ordered), `account`, `url`, `title`, `published`, `status`, `error`, `attempts`, `chars` (transcript length, used for the "low text" flag), `updated_at`.

Exports are `data/exports/<account>-<date>-<time>[-N].txt`: a TASK line for Claude, a `# @account | N clips | date` header, then `[id]` blocks. Parts are split at clip boundaries to stay under `export_max_chars`.

## Notes

- yt-dlp needs browser impersonation for TikTok (`curl_cffi`, config `impersonate: chrome`). yt-dlp's automatic target breaks profile listing, so a target is always set explicitly.
- `curl_cffi` has no wheels for 32-bit Python on Windows: use 64-bit Python.
- OCR preprocessing defaults to `text_mask: white`: only near-white, unsaturated pixels count as text. TikTok captions are white with a dark outline, often karaoke-style with the current word on a colored box; a plain Otsu threshold loses that word (measured on @momentumcash: 88% → 95–97% word recall). `otsu` stays available for other caption styles.
- The cleaner also strips OCR specks at line ends, reads `0` inside a word as `O`, and drops lines that are pieces of a recent line.
- Frame de-duplication compares the busiest 20 px cell (on a 160 px-wide copy), not the whole-frame mean, so a one-word subtitle change on a static background still counts.
