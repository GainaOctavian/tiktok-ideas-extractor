---
name: tiktok-ideas
description: Drive the TikTok Ideas Extractor (run, stop, export, status of a TikTok account) by script through tiktok_ideas_ctl.py instead of the web page. Use when asked to run or check an extraction in this repo.
---

# tiktok-ideas ctl

## Start
The app must be running with the ctl enabled (it writes `data/ctl.json`):

```powershell
.\.venv\Scripts\python.exe tiktok_ideas.py ui --ctl --no-browser      # background
```
For tests or experiments use a scratch config: `--config <tmp>\config.yaml` on both commands.

## Send lines
```powershell
.\.venv\Scripts\python.exe tiktok_ideas_ctl.py "run youraccount 5" wait "status youraccount"
.\.venv\Scripts\python.exe tiktok_ideas_ctl.py -f script.txt
```
Exit codes: 0 ok, 1 stopped at an error (`error at line N (<line>): <reason>`), 2 no app listening.

## Commands
| Line | Answer |
|---|---|
| `run <account> [limit]` | `started @acc` — runs in the background, one run at a time |
| `stop` | finishes the current clip, then ends the run |
| `wait` | blocks until the run ends; prints its last line |
| `state` | `idle` (+ `last: …`) or `running @acc i/n` (+ `(stopping)`) |
| `log [n]` | last n log lines (default 20) |
| `status <account>` | counts, failures, low-text clips, skipped photo posts |
| `export <account>` | writes unexported transcripts to `data/exports/`, prints paths |
| `reset <account>` | requeue failed clips (refused during a run) |
| `exports` | export files, newest first |
| `help` | the list |

Accounts: `name`, `@name` (quote it in PowerShell) or a profile URL. `#` starts a comment.

## Example
```
run youraccount 3
wait
status youraccount
export youraccount
```
The page (`tiktok_ideas.py ui`) sends exactly these lines, so anything the buttons do works here too.
