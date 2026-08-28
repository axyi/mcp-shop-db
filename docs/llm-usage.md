# LLM usage

| # | Stage | Model | Tokens | Cost |
|---|-------|-------|--------|------|
| 1 | spec authoring (writer agent, 2 iterations incl. SDK proof runs) | claude (lab session) | ~231k (harness-reported aggregate; in/out split not exposed) | — (flat-rate session) |
| 2 | spec review (reviewer agent, clean context) | claude (lab session) | ~153k (aggregate) | — |
| 3 | implementation (`go docs/spec/spec-v0.md`, prompt: docs/prompts/01-go-implementation.md) | claude-sonnet-5 (Claude Code CLI session) | in 13.75M (178 uncached + 211k cache-write + 13.54M cache-read), out 97.5k — measured from the local session transcript | ≈$4.21 (estimate at public API prices; actual billing: flat-rate subscription) |
| **Σ** | | | ~384k (spec) + 13.75M/97.5k (impl.) | ≈$4.21 (impl. estimate) |

Notes: rows 1–2 are the authoring cost of the specification itself, recorded
per the lab reporting standard; secrets and raw prompts containing runtime
data are never logged here. The harness does not expose token/cost counters
to the agent in-session; row 3 was measured afterwards from the local Claude
Code session transcript (per-request `usage` fields, deduplicated by request
id). Cost estimated at Anthropic's public API price list (claude-sonnet-5:
$2/$10 per MTok in/out, cache write ×1.25, cache read ×0.1); the session
actually ran on a flat-rate subscription.
