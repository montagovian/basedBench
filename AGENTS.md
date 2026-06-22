# basedBench Agent Notes

## Benchmark Task Definition

basedBench evaluates whether a model **gets the joke** in a meme. It does not
evaluate whether a model can produce a psychological or aesthetic theory of why
something is funny.

When editing prompts, docs, evals, or review UI copy, preserve this distinction:

- Correct predictions identify the relevant people, events, memes, media,
  phrases, visual details, or cultural references.
- Correct predictions reconstruct the intended setup, implication, contrast,
  inversion, irony, wordplay, or other mechanism a viewer must notice to
  understand the meme.
- Judges should compare the model's explanation to the consensus ground truth
  and ask whether it got the same joke.
- Do not require models to explain why humor works, why humans feel amused, or
  any general theory of comedy.

The Reddit comments that create consensus are evidence that humans recovered the
intended joke. They are not expected to provide a formal account of humor.

## Development

- Use `uv` for Python package management and command execution.
- Run `uv run pytest` before release-facing changes.
- Keep local working data under `data/` and generated exports under `export/`;
  neither is a public repo artifact.
- Do not commit secrets, raw SQLite databases, local images, caches, or LLM call
  logs.
