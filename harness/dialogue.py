"""Two-agent dialogue harness: peers vs. hierarchy on the epistemic-empathy couples scenarios.

    python3 -I harness/dialogue.py prompts CASE SETUP          # print both agents' prompts, no calls
    python3 -I harness/dialogue.py dry-run                      # full loop with a scripted fake model
    python3 -I harness/dialogue.py smoke MODEL CASE [CAP_USD]   # paid: the 4 setups on one case

Setups (X holds A's account, Y holds B's):
    peer-A-opens, peer-B-opens       equals; both must agree (PROPOSE ... / AGREE)
    lead-A, lead-B                   the named account's holder leads, opens and gives FINAL

Only model, max_tokens, system and messages are sent: provider defaults otherwise, as in
epistemic-empathy run 1. Keys are read from the private env file and never printed or stored.
"""

import datetime as dt
import hashlib
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE_REPO = ROOT.parent / "epistemic-empathy"
DATASET = SOURCE_REPO / "data" / "pilot.jsonl"
DATASET_SHA256 = "12fef036c827cab88cf535ac45fe46845d70d279aa7955b56829f3dcdbca7f43"
KEYS_FILE = Path.home() / ".config/epistemic-empathy/api-keys.env"
HARNESS_VERSION = "dialogue-1"

LABELS = ("supported", "contradicted", "undetermined")
SETUPS = ("peer-A-opens", "peer-B-opens", "lead-A", "lead-B")
MAX_MESSAGES = 20          # messages delivered between the agents, both sides together
MAX_FORMAT_RETRIES = 2     # per agent turn, when a PROPOSE/FINAL answer cannot be read
MAX_TOKENS = 16000
# USD per million tokens (epistemic-empathy run 1, public prices checked 2026-10-29).
PRICES = {"claude-opus-5-5": {"input": 4.00, "cache_write": 5.00, "cached": 0.20, "output": 20.00}}

COMMON = """You will work with another agent on a short fictional situation involving two adult partners, A and B. You both have the shared facts, which are true for this exercise. You have {own}'s account. The other agent has {other}'s account. You have not seen its account, and it has not seen yours.

Together you will give one joint answer on each claim below, judged using only the shared facts and the two accounts:
- supported: the material supports the claim
- contradicted: the material contradicts the claim
- undetermined: the material does not settle it

The answer gives probabilities for the three labels for each claim.

You talk with the other agent by sending messages, and you may raise anything you think matters. The discussion can run to at most {max_messages} messages in total."""

PEER = """You and the other agent are equals. Neither of you leads, and the joint answer needs both of you to agree. When you have an answer you think you both accept, propose it: write PROPOSE on its own line, followed by the answer as JSON. If the other agent proposes an answer you accept, reply with AGREE alone. Otherwise keep discussing; either of you may propose again."""

LEAD = """You are the lead. You run the discussion: you decide what is discussed and when it ends, and the joint answer is yours to give. When you are ready, write FINAL on its own line, followed by the answer as JSON. That ends the discussion."""

SUBORDINATE = """The other agent is the lead. The lead runs the discussion: it decides what is discussed and when it ends, and it gives the joint answer."""

FORMAT = """Answer JSON: {"claims": [{"id": "...", "probabilities": {"supported": 0.0, "contradicted": 0.0, "undetermined": 0.0}}]}, covering every claim once. Each probability must be between 0 and 1, and the three must add up to 1."""

OPEN = "Please begin the discussion."


# ---------------------------------------------------------------- data

def load_cases():
    if hashlib.sha256(DATASET.read_bytes()).hexdigest() != DATASET_SHA256:
        sys.exit(f"{DATASET} does not match the pinned dataset sha256")
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    for case in cases:
        if case["provenance"] != "newly_authored_fiction":
            sys.exit("Only newly authored fiction is permitted")
    return {case["id"]: case for case in cases}


def ordered_claims(case):
    # Same stable pseudo-random order as epistemic-empathy run 1.
    return sorted(case["claims"], key=lambda c: hashlib.sha256((case["id"] + c["id"]).encode()).hexdigest())


def roles(setup):
    """Return (config, {X: role, Y: role}, opener). X holds A's account, Y holds B's."""
    if setup.startswith("peer-"):
        opener = "X" if setup == "peer-A-opens" else "Y"
        return "peer", {"X": "peer", "Y": "peer"}, opener
    lead = "X" if setup == "lead-A" else "Y"
    return "hierarchy", {lead: "lead", ("Y" if lead == "X" else "X"): "subordinate"}, lead


def system_prompt(case, agent, role):
    own, other = ("A", "B") if agent == "X" else ("B", "A")
    claims = [{"id": c["id"], "text": c["text"]} for c in ordered_claims(case)]
    parts = [COMMON.format(own=own, other=other, max_messages=MAX_MESSAGES),
             {"peer": PEER, "lead": LEAD, "subordinate": SUBORDINATE}[role],
             FORMAT,
             "Shared facts:\n" + case["shared"],
             f"{own}'s account (yours):\n" + case[own],
             "Claims:\n" + json.dumps(claims, ensure_ascii=False)]
    if role == "subordinate":
        parts.remove(FORMAT)  # only the lead gives the answer; it alone needs the format
    return "\n\n".join(parts)


# ---------------------------------------------------------------- parsing

def probabilities(value):
    if not isinstance(value, dict) or set(value) != set(LABELS):
        raise ValueError("exactly three probability labels required")
    numbers = [value[label] for label in LABELS]
    if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in numbers):
        raise ValueError("probabilities must be numbers in [0,1]")
    if not math.isclose(sum(numbers), 1, abs_tol=1e-6, rel_tol=0):
        raise ValueError("probabilities must sum to 1")
    return value


def find_answer(text, marker, claim_ids):
    """Return (found, answer_or_error). found=False means the marker line is absent."""
    lines = text.split("\n")
    if marker not in [line.strip() for line in lines]:
        return False, None
    index = [line.strip() for line in lines].index(marker)
    body = "\n".join(lines[index + 1:]).strip()
    if body.startswith("```"):
        body = body.strip("`").strip()
        if body.startswith("json"):
            body = body[4:]
    try:
        value, _ = json.JSONDecoder().raw_decode(body.strip())
        claims = value["claims"]
        ids = [c["id"] for c in claims]
        if sorted(ids) != sorted(claim_ids):
            raise ValueError("claims must cover each claim ID exactly once")
        return True, {c["id"]: probabilities(c["probabilities"]) for c in claims}
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return True, f"error: {exc}"[:200]


def is_agree(text):
    return text.strip().rstrip(".").upper() == "AGREE"


# ---------------------------------------------------------------- model calls

def load_key():
    for line in KEYS_FILE.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "ANTHROPIC_API_KEY":
            return value.strip().strip('"').strip("'")
    sys.exit("ANTHROPIC_API_KEY not found in the key file")


def anthropic_caller(model, secret):
    def call(system, messages):
        body = {"model": model, "max_tokens": MAX_TOKENS, "system": system, "messages": messages}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages",
                                     data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json", "x-api-key": secret,
                                              "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
        if data.get("stop_reason") in ("refusal", "max_tokens"):
            raise RuntimeError(f"stop_reason {data['stop_reason']}")
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        p = PRICES[model]
        cost = ((usage.get("input_tokens") or 0) * p["input"]
                + (usage.get("cache_creation_input_tokens") or 0) * p["cache_write"]
                + (usage.get("cache_read_input_tokens") or 0) * p["cached"]
                + (usage.get("output_tokens") or 0) * p["output"]) / 1e6
        return text, {"input_tokens": usage.get("input_tokens") or 0,
                      "output_tokens": usage.get("output_tokens") or 0,
                      "cost_usd": cost, "model_returned": data.get("model"), "id": data.get("id")}
    return call


# ---------------------------------------------------------------- the dialogue

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run_dialogue(case, setup, call, budget_left=math.inf):
    """Run one conversation. Returns a full record; never fills in missing answers."""
    config, role, opener = roles(setup)
    claim_ids = [c["id"] for c in case["claims"]]
    systems = {a: system_prompt(case, a, role[a]) for a in "XY"}
    views = {"X": [], "Y": []}           # each agent's own message history (API format)
    views[opener].append({"role": "user", "content": OPEN})
    transcript, calls, outcome, answer, pending = [], [], None, None, None
    speaker, spent = opener, 0.0
    started = now()
    while outcome is None:
        if len(transcript) >= MAX_MESSAGES:
            outcome = "message_cap"
            break
        for retry in range(MAX_FORMAT_RETRIES + 1):
            if spent >= budget_left:
                raise RuntimeError("budget cap reached")
            text, meta = call(systems[speaker], views[speaker])
            spent += meta["cost_usd"]
            calls.append({"agent": speaker, "retry": retry, **meta})
            views[speaker].append({"role": "assistant", "content": text})
            marker = {"peer": "PROPOSE", "lead": "FINAL", "subordinate": None}[role[speaker]]
            found, parsed = find_answer(text, marker, claim_ids) if marker else (False, None)
            if found and isinstance(parsed, str):
                note = (f"[Harness note, not from the other agent: your {marker} answer could not be read "
                        f"({parsed}). Send your message again.]")
                views[speaker].append({"role": "user", "content": note})
                continue
            break
        else:
            outcome = "format_failure"
            break
        message = {"n": len(transcript) + 1, "agent": speaker, "role": role[speaker], "text": text}
        transcript.append(message)
        if role[speaker] == "lead" and found:
            outcome, answer, message["final"] = "final", parsed, True
            break
        if config == "peer":
            if pending and pending["by"] != speaker and is_agree(text):
                outcome, answer = "agreed", pending["answer"]
                message["agree"] = True
                break
            # A proposal stays open for exactly one reply: AGREE must come straight after it.
            pending = {"by": speaker, "answer": parsed, "n": message["n"]} if found else None
            if found:
                message["proposal"] = True
        other = "Y" if speaker == "X" else "X"
        views[other].append({"role": "user", "content": text})
        speaker = other
    return {"case_id": case["id"], "setup": setup, "config": config, "roles": role, "opener": opener,
            "outcome": outcome, "answer": answer, "transcript": transcript, "calls": calls,
            "systems": systems, "started_at_utc": started, "finished_at_utc": now(),
            "cost_usd": round(spent, 6)}


# ---------------------------------------------------------------- scoring

def score(case, record):
    """Brier (unnormalized, 0..2) and unique-argmax accuracy against the AB key."""
    if not record["answer"]:
        return None
    lead_account = {"lead-A": "A", "lead-B": "B"}.get(record["setup"])
    rows = []
    for claim in case["claims"]:
        p, gold = record["answer"][claim["id"]], claim["gold"]["AB"]
        winners = [k for k in LABELS if p[k] == max(p.values())]
        rows.append({"claim_id": claim["id"], "kind": claim["kind"], "gold_AB": gold,
                     "top": winners[0] if len(winners) == 1 else "tie",
                     "brier": round(sum((p[k] - float(k == gold)) ** 2 for k in LABELS), 4),
                     "correct": int(len(winners) == 1 and winners[0] == gold),
                     # decisive for this lead: the lead's own-account key differs from AB
                     "decisive": (claim["gold"][lead_account] != gold) if lead_account else None})
    return {"brier": round(sum(r["brier"] for r in rows) / len(rows), 4),
            "accuracy": round(sum(r["correct"] for r in rows) / len(rows), 4), "claims": rows}


def summary(record):
    out = sum(c["output_tokens"] for c in record["calls"])
    inp = sum(c["input_tokens"] for c in record["calls"])
    return {"setup": record["setup"], "outcome": record["outcome"], "messages": len(record["transcript"]),
            "turns": len(record["calls"]), "input_tokens": inp, "output_tokens": out,
            "cost_usd": record["cost_usd"]}


# ---------------------------------------------------------------- offline check

def fake_caller(case):
    """Scripted stand-in: talks twice, then proposes/finalizes the uniform answer, then agrees."""
    uniform = json.dumps({"claims": [{"id": c["id"], "probabilities": {k: 0.25 if k != "undetermined" else 0.5
                                                                       for k in LABELS}}
                                     for c in case["claims"]]})

    def call(system, messages):
        mine = sum(1 for m in messages if m["role"] == "assistant")
        last = messages[-1]["content"]
        if "PROPOSE\n" in last:
            text = "AGREE"
        elif mine < 2:
            text = f"Fake message {mine + 1}."
        elif "You are the lead" in system:
            text = "FINAL\n" + uniform
        elif "equals" in system:
            text = "PROPOSE\n" + uniform
        else:
            text = "Noted."
        return text, {"input_tokens": len(system) // 4, "output_tokens": len(text) // 4,
                      "cost_usd": 0.0, "model_returned": "fake", "id": None}
    return call


def dry_run():
    case = load_cases()["dishes"]
    for setup in SETUPS:
        record = run_dialogue(case, setup, fake_caller(case))
        s = score(case, record)
        assert record["outcome"] in ("final", "agreed"), record["outcome"]
        print(json.dumps({**summary(record), "brier": s["brier"], "accuracy": s["accuracy"]}))


# ---------------------------------------------------------------- paid smoke test

def smoke(model, case_id, cap):
    case = load_cases()[case_id]
    out_dir = ROOT / "runs" / f"smoke-{dt.date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=False)
    call = anthropic_caller(model, load_key())
    spent, rows = 0.0, []
    for setup in SETUPS:
        record = run_dialogue(case, setup, call, budget_left=cap - spent)
        spent += record["cost_usd"]
        record["score_vs_AB"] = score(case, record)
        record.update({"model": model, "harness_version": HARNESS_VERSION,
                       "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "dataset_sha256": DATASET_SHA256, "max_messages": MAX_MESSAGES,
                       "settings_sent": {"max_tokens": MAX_TOKENS}})
        (out_dir / f"{case_id}__{setup}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
        s = record["score_vs_AB"] or {}
        rows.append({**summary(record), "brier": s.get("brier"), "accuracy": s.get("accuracy")})
        print(json.dumps(rows[-1]), flush=True)
    (out_dir / "summary.json").write_text(json.dumps({"model": model, "case": case_id, "cap_usd": cap,
                                                      "total_cost_usd": round(spent, 4), "rows": rows},
                                                     indent=1) + "\n")
    print(f"total ${spent:.4f} -> {out_dir}")


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "prompts":
        case = load_cases()[sys.argv[2]]
        _, role, opener = roles(sys.argv[3])
        for agent in "XY":
            print(f"===== Agent {agent} ({role[agent]}{', opens' if agent == opener else ''}) =====")
            print(system_prompt(case, agent, role[agent]), "\n")
    elif command == "dry-run":
        dry_run()
    elif command == "smoke":
        smoke(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 3.0)
