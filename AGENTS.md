# AGENTS.md — fmhistory

A decoder for Football Manager 26 save files. This fork exists to make **career
history** readable from a save itself, rather than from screenshots of the UI.

## Mission

Decode FM26's history sections (`tc_*_history*`, `hall_of_fame`,
`tc_record_man`, …) into programmatic records so a save like
`Karl Hudgell - UnemployedNew.fm` can answer: *league positions, honours,
cup runs, awards, transfers — per season, for the manager and their clubs.*

## Working rules (standing, from the project owner)

1. **The 421 screenshots in `/mnt/SharedDownloads/BACKUP/screens/` are
   ground truth for CALIBRATION ONLY.** Never build the analysis from images.
   Every fact must be derived from the save's decoded sections and validated
   against the screenshots afterwards.
2. **Push as we go** — when a decoder lands, commit and push to `origin
   history-decoders` (`git@github.com:karl0ss/fmhistory.git`).
3. **Checkpoint at every good stopping point**: update the current section in
   `docs/history-re.md` (or add a new one) with what is solved, what was ruled
   out (dead ends save future sessions real time), and the concrete next steps,
   then commit + push. A resumed session should never redo ruled-out work.
4. Autonomy: the owner says "keep going" and means it — work down the roadmap
   in `docs/history-re.md` without waiting for direction.
5. Git attribution: end commit messages with
   `Co-Authored-By: Claude Code <noreply@anthropic.com>`; PR descriptions end
   with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Where the knowledge lives

- `docs/history-re.md` — reverse-engineering notes: the main working document.
  Each section's byte layout, pointers to the row anchors found in the
  ground-truth save, dead ends, and the "Remaining plan" that a resumed session
  executes first (currently: league history, checkpoint 2).
- `docs/ground-truth.md` — the career facts the screenshots pin down, used
  only to validate decoded values.
- `docs/reference/` — decoded record format references for what's integrated.
- `src/fmsave/readers/career_history.py` + `src/fmsave/models/career_history.py`
  — the pattern of an integrated decoder: model + reader +
  `register_field_statuses(..., unconfirmed=...)`.
- Analysis section extracts live OUTSIDE the repo under
  `/home/karl/fm26-career/sections*/` (never commit binary save data). Scratch
  scripts and interim findings notes also belong there, never in the repo tree.

## Environment

- Run every Python command through the project venv:
  `.venv/bin/python` (3.13, matches `pyproject.toml`'s ≥3.12 requirement).
  This includes pytest (`.venv/bin/python -m pytest -q`) and section analysis
  scripts.
- Never run fmsave code with the system interpreter (3.11): the codebase uses
  modern type syntax (`type X = ...`, PEP 695 generics) that only parses on
  3.12+. One session hit the resulting `SyntaxError` and "fixed" it by
  rewriting source files into old `typing` style — that must not happen again;
  switch to the venv, never edit the code to suit an older interpreter.
- Never push (or commit) a fix that downgrades code for an older Python.

## Decoder integration checklist

When a section's layout is proven on the ground-truth save:

1. Model dataclass in `src/fmsave/models/`, every unverified field marked
   unconfirmed via `register_field_statuses`.
2. Reader in `src/fmsave/readers/`, wired into `src/fmsave/_save.py` with a
   `Save.` method.
3. CLI access if user-facing; docs in `docs/reference/` and a status update in
   `docs/history-re.md`.
4. Tests in `tests/` (full pytest run; see CONTRIBUTING for env setup).
5. Commit + push.

Anything not in the checklist above is an open question — ask, don't guess
beyond the working rules.