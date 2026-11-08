# Evals

Manual scripts that call a real model; pytest does not collect them.

## scene_eval.py

Runs 10 prompts (5 about this project, 5 concepts) in fresh mentor-mode Claude Code sessions with a fake page that validates scenes with `parse_scene`. Pass = a valid scene on the 1st or 2nd `present` call.

```
uv run --project server python server/evals/scene_eval.py [--only 1,6] [--model sonnet]
uv run --project server python server/evals/scene_eval.py --self-test   # offline, no model
```

Output: a Markdown table on stdout and a JSON file in `.impeccable/review/scene-eval/` (gitignored).
