# Agent instructions for Socra

These rules apply to any coding agent working in this repository (Claude Code, Pi, or others).

## Before merging a pull request

Every pull request that closes an issue goes through these steps, in this order. Steps 1 to 3 run automatically: the agent starts them without asking, fixes what they confirm, and records the outcome in the pull request. The maintainer only answers native review consent (step 4, when it applies) and decides the merge.

1. **CI is green.** Both jobs in `.github/workflows/ci.yml` pass.
2. **Spec verification.** An independent verifier that did not write the change reads the issue's specification and returns a verdict for each requirement (pass, fail, partial or unverifiable), with `path:line` evidence from the code and the test that pins it.
   - The specification is the feature document (`odd/tasks/<feature>.md`, local and gitignored) when there is one, or otherwise the issue's acceptance criteria.
   - A fail or partial verdict is fixed, with a test that reproduces it first.
3. **Code review by subagents.** One or two independent reviewer subagents read the diff for resilience (errors, disconnects, ordering between server and page) and reliability (logic and the tests that pin it).
   - A finding is a hypothesis: write a test that reproduces it first. Fix it when the test fails; when the test passes, keep it as a regression pin and report the finding as false.
   - Findings not fixed in the pull request are filed as one follow-up issue.
4. **Native review, only when it applies.** Run a Gentle AI native review when its risk assessment (`gentle_review` assess) says a review is due (high risk: stored data, security, contracts others consume, concurrency, delivery), or when the maintainer asks for one.
   - Run it on slices so each one fits the reviewer's context: one slice per task of the feature, or about 400 changed lines. Review each slice against the commit before it, from a detached worktree under `.claude/worktrees/`.
   - Choose lenses by what the slice touches. Start from `resilience` and `reliability`; add `risk` for stored data, credentials or contracts others consume, and `readability` for public APIs, command output, messages or docs.
   - The maintainer answers the review's consent prompt for each slice; it cannot be pre-authorized. Declining a slice is allowed and is reported in the pull request.
5. **Pull request updated.** The "Test plan" section of the pull request template records the outcome of steps 2 to 4.

A pull request that only changes documentation may skip steps 2 to 4; say so in the pull request.
