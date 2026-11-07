# Plan: smoke test 2, Opus and Sol

Status: draft, awaiting Dave's go. Process check only, excluded from every confirmatory analysis.

## What

The same test as smoke test 1 (runs/smoke-2026-11-06): the dishes scenario, the four setups
(peer-A-opens, peer-B-opens, lead-A, lead-B), the same prompts, a 20-message limit and no
word limit. The difference is that the two agents can be different models.

Models: claude-opus-5-5 ("Opus") and gpt-6.1-sol ("Sol"), the versions used in
epistemic-empathy run 1. Provider defaults: no temperature, reasoning or effort settings.
Anthropic gets max_tokens 16000; OpenAI gets store=false.

Pairings (X holds A's account, Y holds B's):

| Pairing | X (A) | Y (B) | New conversations |
|---|---|---|---|
| Opus + Opus | Opus | Opus | 0 (reuse smoke test 1) |
| Sol + Sol | Sol | Sol | 4 |
| Opus-A + Sol-B | Opus | Sol | 4 |
| Sol-A + Opus-B | Sol | Opus | 4 |

That makes 12 new conversations. Across the two mixed pairings, each model leads once while
holding A and once while holding B, and opens half of the peer runs. Agents are not told which
model the other agent is.

## Questions it answers

- Does Sol also quote its whole account at once, as Opus did?
- In mixed pairs, does one model defer to the other regardless of role, for example by
  accepting the other's proposal or its reading of the motive claim?
- Does the harness work with two providers in one conversation?

## Build

1. Add an OpenAI caller to harness/dialogue.py, following run 1's adapter: the Responses
   API, store=false, the system prompt as a system message, reasoning tokens counted as output.
2. Assign a model per agent and record it in each record and in the summary.
3. Extend the offline dry run to cover mixed pairs. No paid calls.
4. Have a fresh reviewer check the change before any paid call.

## Cost

Smoke test 1 cost about $0.05 per Opus–Opus conversation. Sol's list prices are half of
Opus's ($2 / $10 per million tokens, against $4 / $20). Expected: about $0.40 for the 12.
The script stops at a $2 cap.

## Keys

- Opus side: the Anthropic key, which still belongs to the Verifact org. Needs Dave's go for
  this run; his smoke-test go covered only smoke test 1.
- Sol side: the OpenAI key in the same private file. In run 1 it failed until credits were added.

## Output

runs/smoke-2026-11-07-opus-sol/: one record per conversation, a summary, and a README table
by pairing × setup (messages, tokens, outcome, Brier and accuracy against the AB key, and
whether each agent quoted its full account). Committed and pushed.
