# LLM usage

| # | Stage | Model | Tokens | Cost |
|---|-------|-------|--------|------|
| 1 | spec authoring (writer agent, 2 iterations incl. SDK proof runs) | claude (lab session) | ~231k (harness-reported aggregate; in/out split not exposed) | — (flat-rate session) |
| 2 | spec review (reviewer agent, clean context) | claude (lab session) | ~153k (aggregate) | — |
| 3 | implementation (`go docs/spec/spec-v0.md`, prompt: docs/prompts/01-go-implementation.md) | claude-sonnet-5 (Claude Code CLI session) | unknown (harness does not expose in/out split for this session) | unknown |
| **Σ** | | | | |

Notes: rows 1–2 are the authoring cost of the specification itself, recorded
per the lab reporting standard; secrets and raw prompts containing runtime
data are never logged here. The implementation run appends its own rows with
exact input/output token counts and money cost from its harness.
