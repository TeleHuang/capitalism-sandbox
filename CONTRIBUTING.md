# Contributing / Development Workflow

## Ownership

| Artifact | Owner | Rule |
|---|---|---|
| `02_需求定义文档.md` | Human | The Code Bot proposes changes, never edits silently. |
| `03_架构设计文档.md` | Code Bot | Must describe the mechanisms actually implemented in `src/ecosim/`. |
| `src/`, `tests/`, `scripts/` | Code Bot | Code changes must keep the architecture document truthful. |
| `docs/REQUIREMENTS_REVIEW.md` | Code Bot | Conflict log with options for the human. |
| `04_开发日志文档.md` | Code Bot | Append a short entry per milestone. |

## The loop

1. Read `02_需求定义文档.md`. If a mechanism is underspecified, design it in the architecture
   document first.
2. If a requirement is economically/historically implausible or internally inconsistent:
   - add an entry to `docs/REQUIREMENTS_REVIEW.md`;
   - present 2–4 concrete options with a recommendation;
   - do **not** change `02_需求定义文档.md` until the human chooses.
3. Implement the chosen design in `src/ecosim/`.
4. Add or update a deterministic regression test in `tests/`.
5. Update `03_架构设计文档.md` in the same change.
6. Append a line to `04_开发日志文档.md`.
7. Run:
   ```powershell
   $env:PYTHONPATH = "src"
   python -m unittest discover -s tests -v
   python -m ecosim --months 240 --seed 1
   ```

## Definition of done

- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] A 240-month run with a fixed seed completes without warnings/errors.
- [ ] Money is conserved (the audit delta is below 0.01).
- [ ] No core sector has zero output for three consecutive months unless the scenario intentionally
      leaves it uninitialised.
- [ ] The architecture document names the modules, formulas and decisions that exist in the code.
- [ ] Any requirement conflict is recorded with options, not hidden in code.
