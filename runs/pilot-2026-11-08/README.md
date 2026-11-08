# Pilot, 2026-11-08: film-taste task, Claude Opus 5.5 on both sides

Run under the frozen analysis plan (plans/analysis-plan.md, commit 87624bc). Analysis code:
`harness/analyze.py`. Conversation records stay private (they quote MovieLens ratings); this
page gives aggregates only.

- 96 conversations (24 friends × 4 setups) and 72 single-agent runs. Every run ended with an
  answer: no failures, no reruns, no cap stops.
- Cost: $28.83 for the conversations, $7.14 for the single-agent runs, $35.97 in total
  (cap $60).

## Confirmatory results

**H1 (peers need more communication): not supported; the difference runs the other way.**
Peers exchanged fewer words than hierarchies for all 24 friends. The median peer/hierarchy
ratio is 0.62 (95% CI 0.57–0.65); one-sided Wilcoxon p = 1. Secondary measures were close to
even: output tokens 0.91 (0.89–1.01), input tokens 1.02 (0.95–1.20), queries 0.91 (0.85–1.00).

**H2a (peers predict better): not supported.** Mean error difference, peers minus hierarchy,
+0.011 stars (95% CI −0.006 to +0.027); peers were more accurate for 9 of 24 friends;
one-sided Wilcoxon p = 0.93.

## Error in stars by condition

Mean over 24 friends, 20 films each.

| Condition | All | Surprising | Typical | RPS |
|---|---|---|---|---|
| Crowd average | 1.23 | 1.88 | 0.58 | 0.216 |
| Recommender | 1.09 | 1.64 | 0.55 | 0.191 |
| Peers, H opens | 1.03 | 1.51 | 0.54 | 0.172 |
| Peers, D opens | 1.02 | 1.51 | 0.54 | 0.171 |
| H leads | 1.02 | 1.49 | 0.54 | 0.171 |
| D leads | 1.01 | 1.49 | 0.54 | 0.169 |
| H alone | 1.02 | 1.49 | 0.55 | 0.171 |
| D alone | 1.22 | 1.87 | 0.58 | 0.215 |
| One agent, both tools | 1.01 | 1.46 | 0.56 | 0.169 |

## What it shows

- **The task has no headroom for H2a.** The history agent alone (1.02) does as well as every
  pair and almost as well as one agent with both tools (1.01). The database agent alone does no
  better than the crowd average (1.22 vs 1.23). The other viewers' ratings added almost nothing
  that the model did not already know about the films. Peers and hierarchies cannot differ in
  accuracy when the second agent's information does not matter.
- **The agents still do not negotiate.** 90 of 96 conversations took 3 messages. In peer
  conversations, the third message was usually a one-word AGREE.
- **Why hierarchies used more words.** The subordinate has no answer format, so it reports in
  prose: a median of 706 words (D reporting) and 830 words (H reporting). Peers put their
  judgments into a proposal's JSON answer, which the plan excludes from the word count, and the
  closing message is usually "AGREE". So part of the H1 reversal is where the information is
  written, not how much is shared. Total tokens were about even.
- **Information flow (exploratory).** The history agent named a median of 30–67 of Sam's films
  (5–10% of the history), most when the database agent led. The database agent searched for
  similar viewers (a query grouped by viewer) in 22–23 of 24 conversations when H opened, but in
  11 of 24 (peers) and 3 of 24 (D leads) when D opened. It made no visible difference to accuracy.
