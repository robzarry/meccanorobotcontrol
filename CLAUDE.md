# Meccano Robot Control

Control a Meccanoid G15 over Bluetooth LE from a Raspberry Pi, with a web
control panel. See README.md for setup and docs/STORY.md for the history.

## Commands

- Tests: `uv run pytest`
- Panel with the mock robot: `uv run meccanoid-web`
- Rebuild the story PDF: `uv run --group docs scripts/build_story_pdf.py`

## Development story (keep it current)

`docs/STORY.md` is the project's development story and `docs/STORY.pdf` is
generated from it. Every pull request must update both:

1. Add or extend the milestone section for the change: what was built, why,
   problems hit, and the proof (tests, hardware results).
2. Refresh "Last updated", "Current status", the "At a glance" table,
   "Where things stand" and the Timeline.
3. Record bumps and lessons honestly in "Bumps in the road".
4. Rebuild the PDF with the command above and commit both files.

Write it in plain language for a non-specialist reader.

## Working style

- One pull request per change, with tests.
- Ask before every push, merge, deploy or publish.
- Stacked PRs: retarget to `main` *before* deleting the branch underneath,
  or GitHub closes the stacked PR.
