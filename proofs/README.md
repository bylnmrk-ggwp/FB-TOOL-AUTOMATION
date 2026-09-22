# Proofs

Each `*.py` file here is executed by `verify.py` with three globals:
`failures` (append a string to fail the run), `step(name)` (prints a
header), and `ROOT` (project root). No pytest here on purpose - `python
verify.py` is the single proof command for this project.

## Layout

One folder per area of the app. Put a new proof in the folder that names
what it proves:

| folder | proves |
|---|---|
| `ui/` | the Tk desktop window: theme, effects, sidebar, tab wiring |
| `sheet/` | the Google Sheet roster: mirroring, writing, and behaving offline |
| `web/` | the FastAPI server, its routes, and the React frontend's store |
| `login/` | signing accounts in: batches, 2FA, checkpoints, captchas, verdicts |
| `profiles/` | browser choice and the profile directories behind each account |
| `actions/` | what the fleet does on Facebook: join, share, comment, like, queue |
| `watch/` | keeping profiles on a live broadcast until it ends |

## Naming

Name a proof `NN_feature.py`, taking the next free number. `verify.py`
sorts by file **name**, not by path, so the numbers are the run order
across every folder - `proofs/ui/01_theme.py` runs before
`proofs/watch/80_watch_to_the_end.py`. The numbers are chronological and
match the commit that added each proof; do not renumber them to close the
gaps.

A proof must not use `__file__` or a path relative to itself. Build every
path from the injected `ROOT`, so moving a proof between folders cannot
break it.
