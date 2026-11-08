# Analysis plan (draft)

Status: **draft, not frozen.** It will be finished, committed and pushed before any pilot
data is collected. Nothing here has been run on pilot data. Smoke-test runs are excluded.

The task is the tool-based film-taste task (plans/taste-task.md), which replaced the couples
task on 2026-11-07. Hypotheses are stated in BRIEF.md. In summary:

- **Confirmatory:** H1 (peers need more communication) and H2a (peers predict the friend's
  ratings more accurately).
- **Exploratory:** H2b (where the peer advantage shows: surprising targets, and the
  difference between "history agent leads" and "database agent leads"), H2c (information
  flow) and "who moved" (below).

Still to write before freezing: the H2a test, how repetitions are pooled, how failed
conversations (message cap, format failure, tool cap) are handled, and pilot scale.

## Confirmatory: H1 (peers need more communication)

Decided with Dave on 2026-11-07, after smoke test 4. In that test every conversation took 3
messages, whatever the setup, but the messages ran from 846 to 1,720 words per conversation.
So the message count cannot carry H1, and the amount said can.

**Primary measure: words exchanged.** This is the total number of words in all messages
delivered between the two agents in a conversation. The answer JSON after a PROPOSE or FINAL
line is removed before counting, so peers are not credited for repeating their proposals as
JSON. Rejected format attempts and harness notes are not counted.

**Secondary measures:**

- Total output tokens across both agents (thinking included), as the provider reports them.
- Total input tokens across both agents, counting cached and uncached together.
- Number of queries.

**Descriptive only:** messages delivered and model calls.

**Unit and test.** Each friend runs all four setups, so the comparison is paired within
friend:

- For each friend, take the mean of log(words) over the two peer setups minus the mean over
  the two hierarchy setups.
- Test that this difference is above zero across friends with a one-sided Wilcoxon
  signed-rank test, α = 0.05.
- Report the median peer/hierarchy ratio with a bootstrap 95% interval over friends.

The secondary measures are reported the same way, without a significance claim. Only
conversations that end with an answer are counted; failure counts are reported by setup.

## Exploratory: who moved

**Question.** When the two agents' judgments differ, whose judgment ends up in the joint
answer? Does that depend on the model or on the role (lead, subordinate, peer)? This
separates "being in charge" from "being the model that holds its ground".

**Why not simply compare each agent's solo answer with the joint answer?** The agents hold
different information, so their solo answers differ mostly because of information, not
opinion. An agent that learns something from the other and changes its answer has been
informed, not overruled. The comparison must hold information fixed.

**Reference answers.** For each model, collect answers from one agent of that model given
**both tools** (the "ceiling" condition already in the design), with the same wording as
the dialogue prompts where possible and at least 3 repetitions. For model *m* and target
film *t*, the reference R(m, t) is the mean expected rating of those answers, in stars. It is
what that model judges with access to everything both agents can reach.

**Where it is defined.** Only in mixed-model pairs (e.g. Opus with Sol), and only on targets
where the two models' references differ by at least 0.5 stars. In same-model pairs both
references are the same, so who moved cannot be measured there.

**Measures.** For a conversation whose joint answer has expected rating J on target t:

1. **Headline (simple):** which model's reference J is closer to.
2. **Continuous:** where J falls between the two references,
   `prevail(X) = (|J − R_Y| − |J − R_X|) / |R_X − R_Y|`.
   +1 means J equals X's reference, −1 means J equals Y's, and 0 means halfway.

**Reporting.** Descriptive only, with no significance test:

- Share of targets won by each model, and the mean prevail score, split by role (lead vs.
  subordinate, peer who opened vs. peer who responded) and by tool (history vs. database).
- Intervals from a bootstrap over conversations, since targets within a conversation are
  not independent.
- The number of qualifying targets.

**What it can and cannot show.**

- It can show whether one model's view tends to prevail regardless of role, or whether the
  lead's view prevails regardless of model.
- It cannot tell persuasion from deference. Giving way to a good argument and giving way to
  please look the same in the joint answer. Telling them apart needs a later design, such as
  one agent instructed to argue a weak position.
- The agents receive each other's messages in the user's seat. Models trained to defer to
  users may yield for that reason, and that may differ by model. This applies to all pairs
  equally, but it limits what "yielding" means here.

**Supporting detail (descriptive).** In peer conversations, record whose first proposal was
closer to the final answer, and how many times each agent revised its proposal.

**Needed before the pilot.** The harness has no single-agent mode yet. Reference answers
need one: one agent with both tools, the same targets and answer format. These runs are
also the ceiling reference point for H2a.
