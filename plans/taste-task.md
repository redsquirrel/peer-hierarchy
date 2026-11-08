# Sketch: a taste-prediction task with tools (2026-11-07)

Status: agreed design (2026-11-07). Harness built (harness/taste.py) and reviewed; ready for a smoke test. The data is downloaded locally (gitignored); no code is
written yet.

## Why change the task

The couples key is short, concise and mostly objective. Agents share both 3-sentence
accounts in full at once, so nearly every conversation ends in 3 messages, and no
information gets lost.

Dave's requirement: no artificial limits on the agents, such as word caps. The task itself
must make full sharing impossible, so that what gets shared depends on how the two agents
work together. That is the situation of two real Claude Code sessions: each works in its
own environment and neither can hand over its whole context.

So in this version the information sits behind tools and is too large to pass across. Each
agent can look things up in its own database, and all it can share is what it found.

## The task

Two agents help a friend, "Sam", by predicting how Sam rated 20 films. Sam's ratings of
those films are hidden from both agents.

- **The history agent (H)** can query Sam's own rating history: 500 or more films with
  stars, title, year and genres. It cannot see other viewers.
- **The database agent (D)** can query everyone else's ratings: about a million ratings
  from about 6,000 viewers, with titles, years and genres. It cannot see Sam's ratings.
- Each agent has one tool: a read-only SQL query on its own database. The models already
  know SQL, so the agents work the way they normally would.

Neither half is enough alone:

- D can find viewers with taste like Sam's, but only if it learns what Sam likes.
- H knows Sam, but it cannot see how people with similar taste rated the target films.
- D's million ratings cannot be passed across. H's history could be pasted at a stretch
  (500 ratings is about 4,000 tokens), but D would then have to type it back into its queries
  to use it. Whether an agent pastes everything, sends a sample, or sends a summary is part
  of what we observe, not something we forbid.

## Data

- **Source:** MovieLens 1M (GroupLens): 1,000,209 ratings of 3,706 films by 6,040 anonymous
  viewers, 2000–2003, 1–5 stars. File sha256
  a6898adb50b9ca05aa231689da44c217cb524e7ebd39d264c56e2832f2c54e20.
- **Not used:** demographics (users.dat), timestamps, viewer IDs and the dataset's name.
  None of these are shown to the agents.
- **Friends:** 24 viewers drawn in a seeded random order from the 399 who rated at least 500
  films. A viewer is skipped if it would leave any chosen friend with fewer than 10 surprising
  or 10 typical candidate films (the first plain draw hit one with only 7). The draw is fixed
  before any runs, in `harness/taste.py prepare`.
- **D's database never contains the friend.** The crowd average used for selecting targets
  and for the baseline also excludes the friend.

## Targets

Each friend has 20 targets, which are removed from H's history:

- **10 surprising films:** Sam's rating is at least 1.5 stars from the crowd average. About
  10% of a heavy rater's ratings are like this, so there are plenty to choose from.
- **10 typical films:** Sam's rating is within 1.5 stars of the crowd.
- A film's reputation alone gets the typical films right and the surprising ones wrong.
  On the surprising films the agents need each other: H's knowledge of Sam and D's
  viewers with similar taste.

## Setups

- **Peer, H opens** and **peer, D opens:** counterbalancing, as before.
- **H leads** and **D leads:** these are now two different cells, not counterbalancing.
  They are the BRIEF's "lead holds the critical facts" and "subordinate holds the critical
  facts" conditions.

Each agent's turn is a tool loop: it may run queries, then writes one message to the other
agent. The endings (PROPOSE + AGREE, FINAL) and the silent message cap stay as they are.
Practical tool limits, such as a cap on rows returned per query and a time limit per
query, are stated in the tool description, the way any real tool states its limits.

Harness rules after the code review (2026-11-07):

- A peer proposal stays open until a new proposal replaces it, so an AGREE several messages
  later still counts. Before, it had to come straight after the proposal, which would have
  pushed peers into needlessly long conversations.
- After 40 queries in one turn (150 for a single agent), further queries get an error asking
  the agent to write its message. Only an agent that keeps querying after that loses the
  conversation.
- Probabilities that sum to within 0.01 of 1 are accepted and rescaled; a larger miss is
  sent back naming the film.
- Within each friend, the four setups run in a seeded random order, and friends run one at a
  time, so an early stop never empties a setup.
- Output is capped at 32,000 tokens per call for both providers. Effort is the provider default.

## Answer and scoring

- For each target, the joint answer gives probabilities for 1 to 5 stars.
- **Primary:** absolute error of the expected rating, in stars.
- **Secondary:** ranked probability score, which is like Brier but gives partial credit for
  being one star off.
- Reported separately for surprising and typical targets.

## Reference points

- **Crowd only:** each film's average rating, excluding Sam.
- **Floors:** H alone, and D alone. D alone can do little more than the crowd average.
- **Ceiling:** one agent with both tools. These answers are also the "who moved" references.
- **A standard recommender:** neighbour-based collaborative filtering on Sam's full
  history. It is a strong yardstick that is not a language model. The agents may lose to it.

Computed 2026-11-07 (`harness/taste.py baselines`), mean error in stars over 480 targets:

| | All | Surprising | Typical |
|---|---|---|---|
| Crowd average | 1.23 | 1.88 | 0.58 |
| Recommender | 1.08 | 1.63 | 0.54 |

The surprising films are hard even for the recommender. Part of what makes them surprising is
likely one-off noise in Sam's rating that nothing can predict, so the achievable gain there
is limited.

## What changes in the harness

- A preparation script builds two read-only SQLite files per friend from the local data,
  checking the file's checksum.
- A tool loop for both providers (Anthropic tool use, OpenAI function calls). The database
  is opened read-only, with a row cap and a per-query time limit.
- A single-agent mode, for the floors and the ceiling.
- Records are written to ~/Projects/anthropic-fellow/peer-hierarchy-private/, never inside
  the repo.
- Scoring (expected-rating error, ranked probability score) and the recommender baseline.
- A fresh review before any paid run, then a small smoke test.

## Scale and cost (rough)

24 friends × 4 setups gives 96 conversations per model pairing, plus single-agent
references. Tool loops mean many more calls per conversation, each with a growing context.
With prompt caching, a rough guess is $0.50–2 per conversation, so $50–200 for the pilot.
A smoke test with 4 conversations comes first to measure the real cost.

## Decisions

1. **Real data: yes** (Dave, 2026-11-07). Real anonymous MovieLens ratings are acceptable for
   this task. The fiction-only rule still applies to anything about couples or clinical
   material.
2. **Run records stay private: option A** (Dave, 2026-11-07). Conversation records stay in a
   private folder outside the public repo. The public repo gets the code, the plan and
   summary results. If public transcripts are wanted later, ask GroupLens
   (grouplens-info@cs.umn.edu). The ml-1m README allows any research use with no implied
   endorsement, citation of Harper & Konstan (2015), no redistribution without permission
   and no commercial use without permission. The repo holds a download script and the
   checksum, not the data.
3. **No word limit** (Dave, 2026-11-07). No artificial caps on the agents. The bottleneck has
   to come from the task. This replaces the word-limit and larger-halves options.
4. **This replaces the couples task** (Dave, 2026-11-07). The couples smoke tests stay in the
   repo as the record of why.

## Open questions for Dave

1. Pilot scale and the cost cap, after the smoke test.
