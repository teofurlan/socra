# Agent instructions for Socra

These rules apply to any coding agent working in this repository (Claude Code, Pi, or others).

## Before merging a pull request

Every pull request that closes an issue goes through these steps, in this order. The maintainer merges only after all of them.

1. **CI is green.** Both jobs in `.github/workflows/ci.yml` pass.
2. **Spec verification.** An independent verifier that did not write the change reads the issue's specification and returns a verdict for each requirement (pass, fail, partial or unverifiable), with `path:line` evidence from the code and the test that pins it.
   - The specification is the feature document (`odd/tasks/<feature>.md`, local and gitignored) when there is one, or otherwise the issue's acceptance criteria.
   - A fail or partial verdict is fixed, with a test that reproduces it first, before the review in step 3.
3. **Native review by slices.** A Gentle AI native review of the change, run on slices so each one fits the reviewer's context:
   - One slice per task of the feature, or about 400 changed lines when there are no tasks. Review each slice against the commit before it, from a detached worktree under `.claude/worktrees/`.
   - Choose lenses by what the slice touches. Start from `resilience` and `reliability`; add `risk` for stored data, credentials or contracts others consume, and `readability` for public APIs, command output, messages or docs.
   - The maintainer answers the review's consent prompt for each slice; declining a slice is allowed and is reported in the pull request.
   - Blocking findings are corrected inside the review. Non-blocking findings are listed in the pull request and either fixed or filed as follow-up issues.
4. **Pull request updated.** The "Test plan" section of the pull request template records the outcome of steps 2 and 3.

A pull request that only changes documentation may skip steps 2 and 3; say so in the pull request.
