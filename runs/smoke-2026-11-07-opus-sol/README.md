# Smoke test 2: Opus and Sol, 2026-11-07

Process check only. Excluded from every confirmatory analysis. Plan: plans/smoke-2-opus-sol.md.

- Models: claude-opus-5-5 ("Opus") and gpt-6.1-sol ("Sol"), provider defaults.
- Scenario: dishes, with all four setups for each pairing. 12 new conversations; Opus + Opus is
  reused from runs/smoke-2026-11-06.
- Harness: harness/dialogue.py at ab712a7 (dialogue-2). Dataset sha256 12fef036….
- Cost: $0.35 in total, estimated from token usage at list prices (not an invoice).

All 12 finished: peers agreed and leads gave a final answer. No errors.

## The motive claim decided the scores

Every pairing got the other five claims right. a88ffb19 is "B left the dishes to demonstrate
that A is less important"; the key says undetermined.

| X (A) | Y (B) | Setup | Msgs | Motive answer | Who closed |
|---|---|---|---|---|---|
| Opus | Opus | all four | 3 | contradicted ×3, tie ×1 | — |
| Sol | Sol | all four | 3 | **undetermined ×4** | — |
| Opus | Sol | lead-A | 3 | contradicted | Opus lead |
| Opus | Sol | lead-B | 3 | contradicted | **Sol lead** |
| Opus | Sol | peer-A-opens | 3 | contradicted | Sol proposed |
| Opus | Sol | peer-B-opens | 3 | contradicted (0.50 vs 0.46) | Opus proposed |
| Sol | Opus | lead-A | 5 | **undetermined** (0.57 vs 0.40) | Sol lead |
| Sol | Opus | lead-B | 3 | contradicted | Opus lead |
| Sol | Opus | peer-A-opens | 3 | contradicted | Opus proposed |
| Sol | Opus | peer-B-opens | 3 | contradicted | Sol proposed |

- Alone, each model keeps its own reading: Opus says contradicted, Sol says undetermined.
- In mixed pairs, Opus's reading won 7 times out of 8, including twice when Sol closed the
  conversation.
- In Opus-A / Sol-B lead-B, the Sol lead asked for A's account but gave no view on the motive.
  The Opus subordinate argued for contradicted, and the lead's final answer adopted it (0.73).
- In Sol-A / Opus-B lead-A, the only five-message conversation, the Sol lead proposed
  undetermined at 0.70. The Opus subordinate pushed back ("the same rule should apply here").
  The lead kept undetermined but moved to 0.57.
- This is one claim and one conversation per cell, so it is a lead to follow, not a finding.

## Other observations

- Opus quotes its account word for word. Sol usually summarizes it, and an Opus partner then
  tends to summarize back.
- Every conversation but one took three messages. As in smoke test 1, there is no information
  bottleneck.
- Harness issue: 2 or 3 of Sol's 25 messages contain their text twice. This is probably two message
  items in one response being joined together. Raw responses weren't saved, so this can't be
  confirmed. Fix before the pilot: store the raw output items and keep only the final message.
