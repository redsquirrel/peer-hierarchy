# Analysis plan (draft)

Status: **draft, not frozen.** It will be finished, committed and pushed before any pilot
data is collected. Nothing here has been run on pilot data. Smoke-test runs are excluded.

Hypotheses and measures are stated in BRIEF.md. In summary:

- **Confirmatory:** H1 (peers need more communication) and H2a (peers match the AB key more
  closely).
- **Exploratory:** H2b (decisive claims), H2c (information flow) and "who moved" (below).

Still to write before freezing: the exact H1 and H2a tests, the unit of analysis, how
repetitions are pooled, how failed conversations (message cap, format failure) are
handled, and pilot scale.

## Exploratory: who moved

**Question.** When the two agents' judgments differ, whose judgment ends up in the joint
answer? Does that depend on the model or on the role (lead, subordinate, peer)? This
separates "being in charge" from "being the model that holds its ground".

**Why not simply compare each agent's own single-account answer with the joint answer?**
The agents hold different accounts, so their single-account answers differ mostly because
of information, not opinion. An agent that learns Blake's account and changes its answer
has been informed, not overruled. The comparison must hold information fixed.

**Reference answers.** For each model, collect answers from one agent of that model given
**both accounts** (the "ceiling" condition already in the design), with the same wording as
the dialogue prompts where possible and at least 3 repetitions. For model *m* and claim *c*,
the reference R(m, c) is the mean of those probability answers. It is what that model
judges once it has all the information, which is also what each agent has by the end of a
conversation where both accounts are shared.

**Where it is defined.** Only in mixed-model pairs (e.g. Opus with Sol), and only on claims
where the two models' references differ:

- the top labels of R(X, c) and R(Y, c) differ, or
- the total variation distance between them is at least 0.15.

In same-model pairs both references are the same, so who moved cannot be measured there.

**Measures.** For a conversation with joint answer J on claim c:

1. **Headline (simple):** when the two references have different top labels, which model's
   top label did J pick? Possible results: X's, Y's or neither.
2. **Continuous:** where J falls between the two references,
   `prevail(X) = (TV(J, R_Y) − TV(J, R_X)) / TV(R_X, R_Y)`.
   +1 means J equals X's reference, −1 means J equals Y's, and 0 means halfway.
   TV(p, q) = ½ Σ |p − q| over the three labels.

**Reporting.** Descriptive only, with no significance test:

- Share of claims won by each model, and the mean prevail score, split by role: lead vs.
  subordinate, and peer who opened vs. peer who responded.
- Intervals from a bootstrap over conversations, since claims within a conversation are
  not independent.
- The number of qualifying claims, which may be small: in the smoke tests, only the motive
  claim in the dishes scenario split the two models.

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
need one: one call, both accounts, the same claim list and answer format. These calls are
also the ceiling reference point for H2a.
