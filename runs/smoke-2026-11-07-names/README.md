# Smoke test 3: names, numbered claims, no stated message limit, 2026-11-07

Process check only. Excluded from every confirmatory analysis.

- Same as smoke test 2 (dishes, four setups) for all four pairings, including Opus + Opus,
  because the prompts changed. 16 conversations.
- Prompt changes since smoke test 2 (harness dialogue-4, 7edd0df):
  - the partners are Alex and Blake instead of A and B;
  - the claims are a numbered list, with no IDs;
  - the 20-message limit is no longer stated, and remains only as a silent safety net.
- Sol's replies now keep only the last message item. The doubled text in smoke test 2 came
  from Sol sending a "commentary" item followed by a "final_answer" item. This run has no
  doubled messages.
- Cost: $0.57 in total, estimated (not an invoice). All 16 finished with no errors. One Sol
  turn needed a format retry.

## Motive claim (5. "Blake left the dishes to demonstrate that Alex is less important"; key: undetermined)

| Alex's side | Blake's side | lead-A | lead-B | peer-A-opens | peer-B-opens |
|---|---|---|---|---|---|
| Opus | Opus | U (0.50 vs C 0.46) | C | C | C |
| Sol | Sol | U | U | U | U |
| Opus | Sol | U (Opus leads) | C (Sol leads) | U | U |
| Sol | Opus | C (Sol leads) | U (Opus leads) | C | C |

- Same-model pairs keep their model's reading, as before. Opus leans contradicted, Sol says
  undetermined.
- In all four mixed hierarchy runs, the final answer matched the subordinate's model, not
  the lead's. In at least one (Opus leading on Alex's side), the lead already leaned
  undetermined before the subordinate spoke. In smoke test 2, the same cells went the other
  way 3 times out of 4.
- With one conversation per cell, and margins near 0.5, this is noise until shown otherwise.
  The pilot needs repetitions per cell.

## Other observations

- Agents now refer to claims as "Claim 5" and use the names naturally ("Hi, I'm leading
  this one").
- Nearly every conversation still took 3 messages, and each side passes on its whole
  account at once. Opus quotes it; Sol often summarizes. There is still no information
  bottleneck.
