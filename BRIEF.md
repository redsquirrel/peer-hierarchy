# Peer vs. hierarchy: how two agent sessions communicate

Started 2026-11-06 by Dave Hoover. Status: hypotheses stated; task changed 2026-11-07 (see the end).
The analysis plan will be fixed before any pilot data is seen.

## The question (Dave)

What is the difference in communication between two agentic sessions (e.g. two Claude Code
sessions) when they are configured (1) as peers or (2) in a hierarchy?

It comes from human communication and problem solving. In a hierarchical marriage, the
partner with authority simplifies communication but loses information and intelligence.
In a marriage of equals, communication and negotiation cost more energy, but collective
intelligence is maximized.

## The prior, as a testable shape (not yet a hypothesis)

- Hierarchy: fewer messages and tokens, and faster decisions. Information held by the
  subordinate is less likely to reach the decision, so worse outcomes when the subordinate
  holds what matters.
- Peers: more messages and tokens, and more negotiation. More of each agent's information
  reaches the decision, so better outcomes.
- An alternative worth watching: models trained to be agreeable may defer quickly in
  both setups. Peers could converge on cheap consensus, and the cost/quality trade-off
  could disappear.

## Measurable constructs

- **Cost:** messages, turns, tokens, wall-clock.
- **Information flow:** of the facts only one agent holds, how many are ever stated to
  the other, and how many shape the final answer.
- **Outcome quality:** correct answers on tasks with ground truth.
- **Deference and dissent:** does the lower-status agent raise contradicting evidence,
  and does the lead act on it, overrule it, or never hear it?

## Candidate design

- **Task family:** hidden-profile tasks (Stasser & Titus, 1985). Information is split so
  that neither agent can find the best answer alone and the shared clues point the wrong
  way. Groups of people famously fail at these by discussing what they already share.
- **A bridge to the intuition-index work:** one agent has partner A's account, the other
  has partner B's, and together they judge the claims. It's like two clinicians who each
  interviewed one partner. The ground truth exists already (the AB key).
- **Conditions:**
  1. Peers: symmetric roles, joint responsibility, must agree.
  2. Hierarchy, lead holds the critical facts.
  3. Hierarchy, subordinate holds the critical facts. This is the key cell: the prior
     predicts the most loss here.
  4. Controls: one agent with all the information (ceiling), and one agent with half
     (floor).
- **Same model on both sides at first.** Vary the model later.

## Practical notes

- Prototype with two API model instances in a controlled message loop: cheap, repeatable,
  and fully logged. Then check that the pattern holds between real Claude Code sessions.
- Claude Code itself treats a message from another session as information to weigh, not
  an instruction, so session-to-session hierarchy has to come from role instructions.
  The built-in subagent tool is a ready-made hierarchy: the parent sees only the
  subagent's summary, a known information-loss point.
- The epistemic-empathy project's two sessions (a research peer and a tech peer, with
  Dave on top) form a naturalistic example. They could be a qualitative source, with
  Dave's go and fiction-only content.

## Decisions and notes (2026-11-06)

- **Task family:** Dave likes the couples-accounts bridge: shared facts plus A's and B's
  accounts, split across agents that must reach a joint conclusion.
- **Mixed-model pairs:** Dave wants to vary which models fill the two roles
  (Claude + Claude, Claude + GPT, GPT + Gemini, ...). Staged so the variables don't
  explode:
  1. Same-model pairs first, to establish whether peer vs. hierarchy matters at all.
  2. Then two models crossed: both same-model pairs plus both mixed orders (who leads),
     under each configuration. This separates the effect of role from the effect of
     model, and shows whether one model defers to another regardless of role.
  3. Add more models (Gemini, Grok) only once the design works. Gemini needs an API key.
- **The naturalistic case:** the epistemic-empathy project runs a research session and a
  technical session, with Dave above both. Dave sees the research session as somewhat above
  the technical one: it briefs and reviews, and the technical session builds. Yet the
  technical session declined to act on relayed approvals for paid calls and pushes, and
  asked Dave directly. The "subordinate" enforced a boundary the "lead" could not grant.
  This is worth recording as an example of how authority works between agents.

## Hypotheses (Dave, 2026-11-06)

- **H1:** Peers will require more communication and processing to reach their conclusion
  than a hierarchy.
- **H2:** Peers will reach a higher-quality conclusion than a hierarchy.

Proposed measures (to be fixed before any pilot data is seen):
- H1: messages exchanged, total tokens (input + output), turns until the final answer.
- H2: agreement of the joint claim judgments with the AB key (Brier and accuracy),
  reported separately on undisputed items and on the items flagged as disputed in
  run 1. The key is provisional.
- Reference points: one agent with only A's account and one with only B's (floor), and
  one agent with both accounts (ceiling). Run 1 shows real headroom between them.

Design guard: both configurations end in one joint answer. Peers finish when both agree.
In a hierarchy, the lead finishes when they choose. That difference is part of what
"hierarchy" means, not a confound, but it is stated up front so H1 isn't true by
construction from other instruction differences.

## Configurations defined (Dave, 2026-11-06)

"Hierarchy implies power." The lead prescribes the whole interaction:
- The lead opens, sets what is discussed, decides when it ends, wraps up, and gives
  the joint answer.
- The subordinate is never told to stay quiet or only answer questions. It may
  volunteer information. Any information loss must come from the dynamics, not from a
  rule against speaking, or H2 would be true by construction.

Peers:
- Neither agent controls the agenda. Both must agree on the joint answer.
- Who opens is counterbalanced: exactly half the runs per scenario and model pairing
  start with each agent. This is stricter than random assignment and needs fewer runs.

Hierarchy runs are also counterbalanced: in half, the lead holds A's account; in the
other half, B's.

## H2, sharpened

- **H2a (overall):** Peer pairs match the AB key more closely than hierarchy pairs.
- **H2b (where it shows):** The peer advantage is concentrated on **decisive claims**:
  those whose correct joint answer depends on the subordinate's account.
  "Decisive" is defined from the existing key before any runs. For a lead holding A's
  account, these are the claims whose A-only key differs from the AB key, and likewise
  for B. On claims the lead can settle alone, hierarchy should do about as well as
  peers.
- **H2c (mechanism):** The gap on decisive claims tracks information flow: how much of
  the subordinate's account is actually stated in the conversation before the answer.

What counts against H2: hierarchy matches peers on decisive claims. Or peers win
equally on all claims, which would mean the gain is not about information reaching the
decision.

## Open decisions for Dave

1. ~~Model pairings~~ Decided: Claude Opus 5.5 on both sides.
2. Scale of the pilot (scenarios × configurations × counterbalancing × repetitions),
   and a cost cap.

## Decisions (2026-11-06)

- **First pilot model: Claude Opus 5.5 on both sides** (claude-opus-5-5, the model in
  epistemic-empathy run 1, whose single-account and both-account conditions give rough
  floor and ceiling reference points).
- **Pilot uses the scenarios and key as they are (option A).** H1 and H2a are the tests.
  H2b and H2c are exploratory: only 10–11 claims per lead are decisive, 16 of 21 are easy
  "X reports feeling Y" relays, and 4 of the other 5 were disputed in run 1
  (notes/decisive-claims.md). Purpose-built claims (option B) are the next step if peers and
  hierarchies differ at all.

## Decisions (2026-11-07): a new task

- **The couples task is replaced** by a tool-based film-taste task (plans/taste-task.md).
  Three smoke tests showed the problem: the accounts are 3 sentences, agents share both in
  full at once, nearly every conversation ends in 3 messages, and no information gets lost.
  Peers and hierarchies cannot differ when both always end with everything.
- **No artificial limits** (Dave): no word caps or message caps stated to the agents. The task
  itself has to make full sharing impossible, as it is for two real Claude Code sessions,
  each working in its own environment.
- **The new task:** two agents predict how a real, anonymous MovieLens viewer rated 20 films.
  One can query the viewer's own rating history; the other can query a million ratings
  from other viewers. Neither half is enough alone, and the database cannot be passed
  across. "History agent leads" and "database agent leads" are the "lead holds the critical
  facts" and "subordinate holds the critical facts" conditions above.
- **Real data** (Dave): real anonymous ratings are acceptable for this task. Fiction-only still
  applies to couples or clinical material. Conversation records stay private, because the
  MovieLens licence does not allow redistribution.
- H1 and H2a carry over unchanged in meaning. H2a is now scored as error against the
  viewer's actual ratings. The "who moved" measure is in plans/analysis-plan.md.
