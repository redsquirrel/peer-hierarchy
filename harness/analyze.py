"""Analysis of a film-taste run, as fixed in plans/analysis-plan.md (frozen 2026-11-08). Free: no model calls.

    python3 -I harness/analyze.py CONVERSATIONS_LABEL [SOLO_LABEL ...]

Reads records from ../peer-hierarchy-private/runs/LABEL/, prints the report, and writes the full
numbers to ../peer-hierarchy-private/runs/CONVERSATIONS_LABEL/analysis.json (never inside the repo).
"""

import json
import math
import random
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import taste  # noqa: E402

PEER = ("peer-H-opens", "peer-D-opens")
HIER = ("lead-H", "lead-D")
BOOT = 10000
BOOT_SEED = 20261108


# ---------------------------------------------------------------- statistics (stdlib only)

def wilcoxon_greater(diffs):
    """One-sided Wilcoxon signed-rank test that the differences are above zero. Zeros are dropped,
    tied absolute values get average ranks, and the p-value is exact (all sign patterns, by counting)."""
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n == 0:
        return {"n": 0, "w_plus": 0.0, "p": 1.0}
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    doubled = [round(2 * r) for r in ranks]          # average ranks are halves: work in integers
    w_plus2 = sum(r for r, x in zip(doubled, d) if x > 0)
    counts = {0: 1}
    for r in doubled:
        nxt = dict(counts)
        for s, c in counts.items():
            nxt[s + r] = nxt.get(s + r, 0) + c
        counts = nxt
    p = sum(c for s, c in counts.items() if s >= w_plus2) / 2 ** n
    return {"n": n, "w_plus": w_plus2 / 2, "p": p}


def bootstrap(values, stat):
    rng = random.Random(BOOT_SEED)
    draws = sorted(stat([rng.choice(values) for _ in values]) for _ in range(BOOT))
    return draws[int(0.025 * BOOT)], draws[int(0.975 * BOOT) - 1]


# ---------------------------------------------------------------- measures

def strip_answer(text, marker):
    """Remove the answer JSON after a PROPOSE/FINAL line; keep any words before or after it."""
    if marker is None:
        return text
    lines = text.split("\n")
    bare = [line.strip().strip("*_#`: ") for line in lines]
    if marker not in bare:
        return text
    i = bare.index(marker)
    before = "\n".join(lines[:i])
    body = "\n".join(lines[i + 1:]).strip()
    fenced = body.startswith("```")
    if fenced:
        body = body.strip("`").strip()
        if body.startswith("json"):
            body = body[4:]
        body = body.strip()
    try:
        _, end = json.JSONDecoder().raw_decode(body)
        after = body[end:].strip().strip("`")
    except ValueError:
        after = ""
    return before + "\n" + after


def words_exchanged(record):
    total = 0
    for m in record["transcript"]:
        marker = {"peer": "PROPOSE", "lead": "FINAL", "subordinate": None}[m["role"]]
        total += len(strip_answer(m["text"], marker).split())
    return total


def call_sums(record):
    calls = record["calls"]
    return {"output_tokens": sum(c.get("output_tokens", 0) for c in calls),
            "input_tokens": sum(c.get("input_tokens", 0) + c.get("cache_write_tokens", 0)
                                + c.get("cache_read_tokens", 0) for c in calls),
            "queries": len(record["tool_log"]), "messages": len(record["transcript"]), "model_calls": len(calls)}


def sam_titles(friend_key):
    """Titles in Sam's history (targets removed), as the history agent sees them."""
    import sqlite3
    con = sqlite3.connect(f"file:{taste.OUT / 'history' / (friend_key + '.sqlite')}?mode=ro", uri=True)
    rows = con.execute("SELECT title FROM ratings").fetchall()
    con.close()
    return [r[0] for r in rows]


def h2c(record, titles):
    """Exploratory. Films from Sam's history named in the history agent's messages (a title match,
    so a lower bound on what was stated), and whether the database agent ran a query grouping by
    viewer (the similar-viewer search seen in smoke test 4)."""
    h_text = " ".join(m["text"].lower() for m in record["transcript"] if m["agent"] == "H")
    named = sum(1 for t in titles if len(t) >= 4 and re.search(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)", h_text))
    d_sql = [q["sql"] for q in record["tool_log"] if q["agent"] == "D"]
    by_viewer = any(re.search(r"group\s+by\s+[\w.]*viewer", s, re.I) for s in d_sql)
    return {"named": named, "share": named / len(titles), "d_grouped_by_viewer": by_viewer}


def load(label):
    folder = taste.PRIVATE / "runs" / label
    return [json.loads(p.read_text()) for p in sorted(folder.glob("f*.json"))]


def fmt(x, nd=3):
    return "—" if x is None else f"{x:.{nd}f}"


def main(conv_label, solo_labels):
    items = taste.load_items()
    keys = [f["key"] for f in items["friends"]]
    records = load(conv_label)
    ok = [r for r in records if r["outcome"] in ("agreed", "final")]
    failed = [r for r in records if r not in ok]
    by = {(r["friend"], r["setup"]): r for r in ok}
    out = {"conversations": len(records), "ended_with_answer": len(ok),
           "failures": [{"friend": r["friend"], "setup": r["setup"], "outcome": r["outcome"]} for r in failed]}
    lines = [f"# {conv_label}", "",
             f"{len(records)} conversations, {len(ok)} ended with an answer, {len(failed)} failed."]

    for r in ok:
        r["_words"] = words_exchanged(r)
        r["_sums"] = call_sums(r)

    def side_mean(friend, setups, value):
        vals = [value(by[(friend, s)]) for s in setups if (friend, s) in by]
        return statistics.fmean(vals) if vals else None

    def paired(value):
        rows = []
        for k in keys:
            p, h = side_mean(k, PEER, value), side_mean(k, HIER, value)
            if p is not None and h is not None:
                rows.append((k, p, h))
        return rows

    # H1
    lines += ["", "## H1: words exchanged (peers minus hierarchy, paired by friend)", ""]
    pairs = paired(lambda r: math.log(r["_words"]))
    diffs = [p - h for _, p, h in pairs]
    test = wilcoxon_greater(diffs)
    ratios = [math.exp(d) for d in diffs]
    ci = bootstrap(ratios, statistics.median)
    out["H1"] = {"friends": len(pairs), "wilcoxon_one_sided_greater": test,
                 "median_ratio": statistics.median(ratios), "ci95": ci}
    lines.append(f"Friends: {len(pairs)}. Median peer/hierarchy ratio of words: {statistics.median(ratios):.2f} "
                 f"(95% CI {ci[0]:.2f}–{ci[1]:.2f}). Peers said more for {sum(d > 0 for d in diffs)} of "
                 f"{len(diffs)} friends. One-sided Wilcoxon p = {test['p']:.4g} (W+ = {test['w_plus']}).")
    lines += ["", "Secondary (same pairing, no significance claim):", ""]
    for name in ("output_tokens", "input_tokens", "queries"):
        pr = paired(lambda r, n=name: math.log(max(r["_sums"][n], 1)))
        rs = [math.exp(p - h) for _, p, h in pr]
        c = bootstrap(rs, statistics.median)
        out["H1"][name] = {"median_ratio": statistics.median(rs), "ci95": c}
        lines.append(f"- {name}: median ratio {statistics.median(rs):.2f} (95% CI {c[0]:.2f}–{c[1]:.2f})")

    # H2a
    lines += ["", "## H2a: error in stars (peers minus hierarchy, paired by friend)", ""]
    pairs = paired(lambda r: r["score"]["abs_error"])
    diffs = [p - h for _, p, h in pairs]
    test = wilcoxon_greater([-d for d in diffs])     # H2a: peers lower, so test -diff > 0
    ci = bootstrap(diffs, statistics.fmean)
    out["H2a"] = {"friends": len(pairs), "wilcoxon_one_sided_less": test, "mean_diff": statistics.fmean(diffs),
                  "ci95": ci}
    lines.append(f"Friends: {len(pairs)}. Mean difference {statistics.fmean(diffs):+.3f} stars "
                 f"(95% CI {ci[0]:+.3f} to {ci[1]:+.3f}); negative favours peers. Peers more accurate for "
                 f"{sum(d < 0 for d in diffs)} of {len(diffs)} friends. One-sided Wilcoxon p = {test['p']:.4g}.")
    pr = paired(lambda r: r["score"]["rps"])
    dr = [p - h for _, p, h in pr]
    c = bootstrap(dr, statistics.fmean)
    out["H2a"]["rps"] = {"mean_diff": statistics.fmean(dr), "ci95": c}
    lines.append(f"Secondary, ranked probability score: mean difference {statistics.fmean(dr):+.4f} "
                 f"(95% CI {c[0]:+.4f} to {c[1]:+.4f}).")
    if failed:
        lines.append("Check with failures scored as the crowd: not yet implemented (there were failures).")
    else:
        lines.append("Check with failures scored as the crowd: not needed, no conversation failed.")

    # Reference table
    base = json.loads((taste.OUT / "baselines.json").read_text())["per_friend"]
    table = {}
    for name in ("crowd", "recommender"):
        table[name] = base[name]
    for s in taste.SETUPS:
        table[s] = [by[(k, s)]["score"] for k in keys if (k, s) in by]
    for lab in solo_labels:
        recs = [r for r in load(lab) if r["outcome"] == "final"]
        if recs:
            table[recs[0]["setup"]] = [r["score"] for r in recs]
    lines += ["", "## Error in stars by condition (mean over friends; n = runs)", "",
              "| Condition | n | All | Surprising | Typical | RPS |", "|---|---|---|---|---|---|"]
    out["table"] = {}
    for name, scores in table.items():
        row = {k: statistics.fmean(s[k] for s in scores) for k in
               ("abs_error", "abs_error_surprising", "abs_error_typical", "rps")}
        out["table"][name] = {"n": len(scores), **row}
        lines.append(f"| {name} | {len(scores)} | {fmt(row['abs_error'], 2)} | {fmt(row['abs_error_surprising'], 2)} "
                     f"| {fmt(row['abs_error_typical'], 2)} | {fmt(row['rps'], 3)} |")

    # Cost table
    lines += ["", "## Communication by setup (median over friends)", "",
              "| Setup | Words | Messages | Queries | Output tokens | Input tokens | Cost |", "|---|---|---|---|---|---|---|"]
    out["communication"] = {}
    for s in taste.SETUPS:
        rs = [by[(k, s)] for k in keys if (k, s) in by]
        row = {"words": statistics.median(r["_words"] for r in rs),
               **{n: statistics.median(r["_sums"][n] for r in rs) for n in
                  ("messages", "queries", "output_tokens", "input_tokens")},
               "cost_usd": statistics.median(r["cost_usd"] for r in rs)}
        out["communication"][s] = row
        lines.append(f"| {s} | {row['words']:.0f} | {row['messages']:.0f} | {row['queries']:.0f} | "
                     f"{row['output_tokens']:.0f} | {row['input_tokens']:.0f} | ${row['cost_usd']:.2f} |")
    msgs = {}
    for r in ok:
        msgs[len(r["transcript"])] = msgs.get(len(r["transcript"]), 0) + 1
    lines.append(f"\nMessages per conversation (count of conversations): {dict(sorted(msgs.items()))}")

    # H2b
    lines += ["", "## Exploratory: H2b", ""]
    for part in ("surprising", "typical"):
        pr = paired(lambda r, p=part: r["score"][f"abs_error_{p}"])
        d = [p - h for _, p, h in pr]
        c = bootstrap(d, statistics.fmean)
        out.setdefault("H2b", {})[part] = {"mean_diff": statistics.fmean(d), "ci95": c}
        lines.append(f"- {part} films, peers minus hierarchy: {statistics.fmean(d):+.3f} stars "
                     f"(95% CI {c[0]:+.3f} to {c[1]:+.3f})")
    for a, b in (("lead-H", "lead-D"), ("peer-H-opens", "peer-D-opens")):
        d = [by[(k, a)]["score"]["abs_error"] - by[(k, b)]["score"]["abs_error"] for k in keys
             if (k, a) in by and (k, b) in by]
        c = bootstrap(d, statistics.fmean)
        out["H2b"][f"{a}_minus_{b}"] = {"mean_diff": statistics.fmean(d), "ci95": c}
        lines.append(f"- {a} minus {b}: {statistics.fmean(d):+.3f} stars (95% CI {c[0]:+.3f} to {c[1]:+.3f})")

    # H2c
    lines += ["", "## Exploratory: H2c (information flow)", "",
              "| Setup | Sam's films named by H (median) | Share of history | D grouped by viewer | Error when D grouped / not |",
              "|---|---|---|---|---|"]
    titles = {k: sam_titles(k) for k in keys}
    out["H2c"] = {}
    for s in taste.SETUPS:
        rs = [by[(k, s)] for k in keys if (k, s) in by]
        flows = [h2c(r, titles[r["friend"]]) for r in rs]
        grouped = [r["score"]["abs_error"] for r, f in zip(rs, flows) if f["d_grouped_by_viewer"]]
        not_grouped = [r["score"]["abs_error"] for r, f in zip(rs, flows) if not f["d_grouped_by_viewer"]]
        row = {"named_median": statistics.median(f["named"] for f in flows),
               "share_median": statistics.median(f["share"] for f in flows),
               "grouped": sum(f["d_grouped_by_viewer"] for f in flows), "n": len(rs),
               "error_grouped": statistics.fmean(grouped) if grouped else None,
               "error_not_grouped": statistics.fmean(not_grouped) if not_grouped else None}
        out["H2c"][s] = row
        lines.append(f"| {s} | {row['named_median']:.0f} | {row['share_median']:.1%} | {row['grouped']}/{row['n']} | "
                     f"{fmt(row['error_grouped'], 2)} / {fmt(row['error_not_grouped'], 2)} |")

    # Peer details
    agreed_first = sum(1 for r in ok if r["config"] == "peer" and
                       next(m for m in r["transcript"] if m.get("agree"))["agreed_to"] ==
                       min(m["n"] for m in r["transcript"] if m.get("proposal")))
    n_peer = sum(1 for r in ok if r["config"] == "peer")
    lines.append(f"\nPeer conversations that agreed to the first proposal: {agreed_first} of {n_peer}.")
    out["peer_agreed_to_first_proposal"] = [agreed_first, n_peer]

    cost = sum(r["cost_usd"] for r in records)
    lines.append(f"\nConversation cost: ${cost:.2f}.")
    (taste.PRIVATE / "runs" / conv_label / "analysis.json").write_text(json.dumps(out, indent=1) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
