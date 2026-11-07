# Sketch: a taste-prediction task (2026-11-07)

Status: sketch for discussion. Nothing is built or downloaded yet.

## Why change the task

The couples key is short, concise and mostly objective. Agents share both 3-sentence
accounts in full at once, so nearly every conversation ends in 3 messages, and no
information gets lost. The new task should feel like judgment, have a real answer that is a
number, split the information so that both halves matter and neither can be relayed whole,
and have an answer the model cannot already know.

## The task

Two agents are helping a friend pick films. Each has seen a different part of the friend's
rating history. Together they predict how the friend rated films that neither has seen
rated.

- **Source:** MovieLens 1M (GroupLens). These are anonymous viewers' 1–5 star ratings
  from 2000–2003 of well-known films. The models know the films but not these viewers.
- **The friend** is one real anonymous viewer, given a plain first name in the prompt. No
  user IDs or dataset name are shown, and no demographics are used.
- **Truth:** the star rating the viewer actually gave.

## Items

- **Viewers:** those with at least 150 ratings that are not all the same.
- **The split is by genre.** For example, X sees the viewer's comedy and horror ratings and
  Y sees their drama and sci-fi ratings. Each agent sees about 40 to 60 films with stars.
  The split is fixed before any runs, by a stated rule.
- **Targets:** 10 films per viewer, which neither agent sees rated:
  - Some fall in X's genres, some in Y's, and some in both, such as a horror-comedy.
  - A target in only one agent's genres is **decisive** for that agent, so H2b gets a clean
    definition: when the lead holds comedy, the drama targets depend on the subordinate.
  - About half the targets are ones where this viewer departs from the crowd by at least 1.5
    stars. On the rest the viewer agrees with the crowd. A film's reputation alone gets the
    typical ones right and the surprising ones wrong, so information about the person is
    what counts.

## Answer and scoring

- For each target, the joint answer gives probabilities for 1 to 5 stars. This uses the
  same format and harness as now.
- **Primary:** absolute error of the expected rating, measured in stars and easy to read.
- **Secondary:** ranked probability score, which is like Brier but gives partial credit
  for being one star off.

## Reference points

- **Crowd only:** the film's average rating across all viewers, with no information about
  this viewer.
- **Floor:** one agent with one half.
- **Ceiling:** one agent with both halves. These are also the "who moved" references.
- **A standard recommender** (collaborative filtering on the viewer's other ratings): a
  yardstick that is not a language model.

## The bottleneck

40 to 60 lines per agent can still be pasted whole, and the models may do just that. Two ways
to make sharing a choice:

- An equal word limit per message, for example 150 words, for every agent in every setup.
- Larger halves, for example 150 films each.

To be decided. The word limit is the cleaner test of H2c.

## Scale and cost (rough)

24 viewers × 10 targets gives 240 items. 4 setups per viewer gives 96 conversations per model
pairing. Messages will be longer than in the couples task. Rough guess: $10–25 for Opus on
both sides, to be checked with a smoke test first.

## Open questions for Dave

1. ~~Real data.~~ **Decided (Dave, 2026-11-07): yes.** Real anonymous MovieLens ratings are
   acceptable for this task. The fiction-only rule still applies to anything about couples
   or clinical material.
2. **Licence.** The ml-1m README allows any research use under four conditions: no implied
   endorsement by the University of Minnesota or GroupLens, cite Harper & Konstan (2015) in
   publications, no redistribution without separate permission, and no commercial use
   without permission. The public repo would hold a download script and a checksum, not
   the data. Published run records would quote some ratings, so whether those records
   stay public needs a decision, or a request to grouplens-info@cs.umn.edu.
3. The bottleneck: word limit or larger halves.
4. Whether this replaces the couples task or runs alongside it.
