Closes #<!-- issue number -->

## PR type
<!-- Check one; add the matching label to the PR. -->
- [ ] New feature (`type:feature`)
- [ ] Bug fix (`type:bug`)
- [ ] Chore, docs or refactor

## Summary
<!-- What changed and why, in a few bullets. Lead with the behavior a user or reviewer will notice. -->
-

## Unchanged
<!-- Optional. What this PR deliberately leaves alone: protocol, modes, pages, files. Delete if not needed. -->
-

## Notes for reviewers
<!-- Optional. Decisions, trade-offs, renamed strings, follow-ups left out on purpose. Delete if not needed. -->
-

## Test plan
<!-- Commands run and their observed results, plus any manual check. Unchecked items mean not run. -->
- [ ] `uv run pytest -q` (server):
- [ ] `npx vitest run` (web):
- [ ] `npx tsc -b` and `npx oxlint` (web):
- [ ] Manual check:
- [ ] Spec verification (see `AGENTS.md`): <!-- verdict per requirement; fixes made -->
- [ ] Code review by subagents (see `AGENTS.md`): <!-- findings confirmed by a test and fixed, false ones pinned, rest filed -->
- [ ] Native review (see `AGENTS.md`): <!-- not due (assessed risk), or slices, lenses and outcome -->
