# Smoke test 4: film-taste task (2026-11-07)

Excluded from analysis. Its purpose was to check the tool-based harness end to end.

- Harness `taste-2` (commit ce6478b). Claude Opus 5.5 on both sides, one friend (f01, 532
  rated films), the four setups, one conversation each. Cap $15; spent $1.24.
- The full conversation records stay private, because they quote MovieLens ratings
  (licence: no redistribution). This summary has no ratings in it.

| Setup | Outcome | Messages | Words | Queries (H / D) | Database agent matched similar viewers | Cost | Error (stars) |
|---|---|---|---|---|---|---|---|
| peer, H opens | agreed | 3 | 1,206 | 5 / 4 | yes | $0.29 | 1.10 |
| peer, D opens | agreed | 3 | 846 | 6 / 2 | no | $0.29 | 1.06 |
| H leads | final | 3 | 1,720 | 6 / 6 | yes | $0.34 | 1.02 |
| D leads | final | 3 | 1,581 | 6 / 2 | no | $0.33 | 0.98 |

References for f01: crowd average 1.19, standard recommender 1.09.

What we saw:

- **No failures.** No format retries, no query-limit hits and no errors.
- **Every conversation took 3 messages again.** But these messages ran 300–1,000 words each, and
  every turn started with several queries. Each agent did a full piece of work per turn.
- **Sharing was selective.** The history agent sent a profile of Sam's taste (genre averages,
  related films and about 20 example ratings), not the full 532 ratings.
- **When the history agent opened,** the database agent typed those example ratings into a
  query and found viewers with similar taste. In one run it also pointed out how its matching
  could be biased.
- **When the database agent opened,** it sent crowd averages first. The history agent then
  adjusted those using Sam's taste, and nobody ever searched for viewers with similar taste.
  With one conversation per setup this is a lead, not a finding.
- **All four joint answers beat the crowd average** for this friend, and three beat the
  recommender.
