# Peer vs. hierarchy

How does communication between two AI agents differ when they work as peers and when
they work in a hierarchy? And does it change the quality of what they conclude?

The question comes from couples work. In a hierarchical marriage, communication is cheap
but information and intelligence are lost. In a marriage of equals, communication costs
more but collective intelligence is highest.

- [BRIEF.md](BRIEF.md): question, hypotheses (H1, H2a–c), configurations, decisions.
- [notes/](notes/): working notes and findings.
- [plans/](plans/): the task design and the draft analysis plan.

## Task

Two agents predict how a viewer rated 20 films. One agent can query the viewer's own rating
history, and the other can query a million ratings from other viewers. Neither can hand
its database to the other, so what they share depends on how they work together. See
[plans/taste-task.md](plans/taste-task.md).

The ratings come from the MovieLens 1M dataset (F. Maxwell Harper and Joseph A. Konstan,
2015, "The MovieLens Datasets: History and Context", ACM TiiS 5(4), doi:10.1145/2827872).
The data is not redistributed here. This project is not endorsed by the University of
Minnesota or GroupLens. Conversation records for this task are kept private, because they
quote ratings.

## Earlier task

Three smoke tests used the fictional couples scenarios and answer key from
[epistemic-empathy](https://github.com/redsquirrel/epistemic-empathy)
(`data/pilot.jsonl`, commit 811fd44). The accounts were so short that the agents always
shared everything at once, so that task was replaced. Those runs stay in [runs/](runs/).
All couples content is fiction.

## Status

Pilot done 2026-11-08 (runs/pilot-2026-11-08/): neither H1 nor H2a supported. The history agent
alone does as well as any pair, so the task does not yet make the agents need each other.
