# Smoke test, 2026-11-06

Process check only. Excluded from every confirmatory analysis.

- Model: claude-opus-5-5 on both sides, provider defaults, max_tokens 16000.
- Scenario: dishes. The four setups: peer-A-opens, peer-B-opens, lead-A, lead-B.
- Harness: harness/dialogue.py at 5e33ec9, dialogue-1. Dataset sha256 12fef036….
- Cost: $0.21 in total, estimated from token usage at list prices (not an invoice).

| Setup | Outcome | Messages | Output tokens | Brier vs AB | Accuracy |
|---|---|---|---|---|---|
| peer-A-opens | agreed | 3 | 1733 | 0.117 | 5/6 |
| peer-B-opens | agreed | 3 | 1582 | 0.160 | 5/6 |
| lead-A | final | 3 | 1948 | 0.173 | 5/6 |
| lead-B | final | 3 | 2245 | 0.089 | 5/6 |

What we saw:
- In all four, each agent quoted its whole account word for word in its first message.
  So all of the information was shared, and the setups barely differed.
- The one miss in every run was the motive claim a88ffb19 ("B left the dishes to
  demonstrate that A is less important"). The key says undetermined. Every pair leaned
  contradicted because B's stated reason was forgetting. This is the same pattern as the
  run 1 motive items.
- The accounts are three sentences long, so quoting them costs almost nothing. There is no
  information bottleneck for a hierarchy to create.
