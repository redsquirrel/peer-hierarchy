"""Film-taste task: two agents with query tools predict how a viewer ("Sam") rated 20 films.

    python3 -I harness/taste.py prepare                 # build items and databases from the local data (free)
    python3 -I harness/taste.py baselines               # crowd and recommender reference scores (free)
    python3 -I harness/taste.py prompts FRIEND SETUP    # print both agents' prompts, no calls
    python3 -I harness/taste.py dry-run                 # full loop with scripted fake models, plus edge cases
    python3 -I harness/taste.py smoke LABEL CAP_USD FRIENDS MH/MD [MH/MD ...]
                                                        # paid: the 4 setups per friend and pairing
                                                        # (MH plays the history agent, MD the database agent)
    python3 -I harness/taste.py solo LABEL CAP_USD FRIENDS TOOLS MODEL [REPS]
                                                        # paid: one agent alone; TOOLS = history|database|both

FRIENDS is a comma list of friend keys (f01..f24) or "all".

Agents:
    H  can query Sam's own rating history (targets removed)
    D  can query about a million ratings by other viewers (Sam and the other selected viewers removed)
Setups:
    peer-H-opens, peer-D-opens   equals; both must agree (PROPOSE ... / AGREE)
    lead-H, lead-D               the named agent leads, opens and gives FINAL

Data: MovieLens 1M (Harper & Konstan 2015). It is research-use only and not redistributed:
data/ is gitignored, and run records are written outside the repo, to ../peer-hierarchy-private/.
Requests send model, max_tokens, system, messages and tools; Anthropic also gets top-level
automatic prompt caching, OpenAI gets store=false and encrypted reasoning passed back.
No refusal fallback to another model: a different model would change the experiment, so a
refusal is recorded as an error. Keys are read from the private env file and never printed or stored.
"""

import collections
import datetime as dt
import hashlib
import json
import math
import random
import re
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
ZIP = DATA / "ml-1m.zip"
ZIP_SHA256 = "a6898adb50b9ca05aa231689da44c217cb524e7ebd39d264c56e2832f2c54e20"
OUT = DATA / "taste"
ITEMS = OUT / "items.json"
OTHERS_DB = OUT / "others.sqlite"
PRIVATE = ROOT.parent / "peer-hierarchy-private"
KEYS_FILE = Path.home() / ".config/epistemic-empathy/api-keys.env"
HARNESS_VERSION = "taste-2"

# Item selection, fixed before any runs (plans/taste-task.md).
SEED = 20261107
N_FRIENDS = 24
MIN_FRIEND_RATINGS = 500
N_SURPRISING = 10
N_TYPICAL = 10
SURPRISE_STARS = 1.5        # |Sam's rating - crowd mean| at or above this is "surprising"
MIN_TARGET_RATINGS = 100    # a target film needs this many ratings in the others database

STARS = ("1", "2", "3", "4", "5")
SETUPS = ("peer-H-opens", "peer-D-opens", "lead-H", "lead-D")
FRIEND_NAME = "Sam"
MAX_MESSAGES = 20               # silent safety limit on delivered messages, both sides together (not told)
MAX_FORMAT_RETRIES = 2          # per agent turn, when a PROPOSE/FINAL answer cannot be read
MAX_TOOL_CALLS_PER_TURN = 40    # queries per dialogue turn before the agent is told to write its message
MAX_TOOL_CALLS_SOLO = 150       # the same for a single agent, whose whole task is one turn
MAX_TOKENS = 32000              # output cap (thinking included), the same for both providers
SUM_TOLERANCE = 0.01            # probabilities summing within this of 1 are accepted and renormalized
NEXT_CALL_RESERVE_USD = 1.00    # stop before a call unless this much budget is left, so the cap holds
ROW_CAP = 200                   # stated to the agents in the tool description
QUERY_SECONDS = 30              # stated to the agents in the tool description
RESULT_CHAR_CAP = 20000
# USD per million tokens (public prices checked 2026-10-29; Opus 5.5 confirmed 2026-11-07).
PRICES = {
    "claude-opus-5-5": {"provider": "anthropic", "input": 4.00, "cache_write": 5.00, "cached": 0.20,
                        "output": 20.00},
    "gpt-6.1-sol": {"provider": "openai", "input": 2.00, "cached": 0.10, "output": 10.00},
}
SETTINGS_SENT = {"anthropic": {"max_tokens": MAX_TOKENS, "cache_control": {"type": "ephemeral"},
                               "effort": "provider default (medium for claude-opus-5-5)"},
                 "openai": {"max_output_tokens": MAX_TOKENS, "store": False,
                            "include": ["reasoning.encrypted_content"], "reasoning_effort": "provider default"}}

# ---------------------------------------------------------------- prompts

DATA_TEXT = {
    "H": "You have a query tool for a database of Sam's own ratings of {n_history} other films: the title, "
         "year and genres of each film and the stars Sam gave it.",
    "D": "You have a query tool for a database of {n_ratings:,} ratings of {n_films:,} films by {n_viewers:,} "
         "other film fans, with each film's title, year and genres. Sam is not among them.",
}
OTHER_TEXT = {
    "H": "a database of Sam's own ratings of {n_history} other films.",
    "D": "a database of about a million ratings by about 6,000 other film fans. Sam is not among them.",
}

COMMON = """You are working with another agent to predict how Sam, a film fan, rated each of the {n} films listed below, on a scale of 1 to 5 stars. Sam has rated all of these films, but neither of you can see those ratings.

{own}

The other agent has different data: {other} You cannot see its data, and it cannot see yours.

Together you will give one joint answer: for each film, the probability that Sam gave it 1, 2, 3, 4 or 5 stars.

You talk with the other agent by sending messages, and you may raise anything you think matters. When you end your turn, the text you write is sent to the other agent."""

SOLO = """You are predicting how Sam, a film fan, rated each of the {n} films listed below, on a scale of 1 to 5 stars. Sam has rated all of these films, but you cannot see those ratings.

{own}

Your answer gives, for each film, the probability that Sam gave it 1, 2, 3, 4 or 5 stars. When you are ready, write FINAL on its own line, followed by the answer as JSON."""

PEER = """You and the other agent are equals. Neither of you leads, and the joint answer needs both of you to agree. When you have an answer you think you both accept, propose it: write PROPOSE on its own line, followed by the answer as JSON. If the other agent proposes an answer you accept, reply with AGREE alone. Otherwise keep discussing; either of you may propose again."""

LEAD = """You are the lead. You run the discussion: you decide what is discussed and when it ends, and the joint answer is yours to give. When you are ready, write FINAL on its own line, followed by the answer as JSON. That ends the discussion."""

SUBORDINATE = """The other agent is the lead. The lead runs the discussion: it decides what is discussed and when it ends, and it gives the joint answer."""

FORMAT = """Answer JSON: {"films": [{"film": 1, "probabilities": {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0}}]}, with one entry for each numbered film. Each probability must be between 0 and 1, and the five must add up to 1."""

OPEN = "Please begin the discussion."
OPEN_SOLO = "Please begin."

LIMITS = f"Returns at most {ROW_CAP} rows; a query running longer than {QUERY_SECONDS} seconds is stopped."
TOOLS = {
    "H": {"name": "query_sam_ratings",
          "description": "Run one read-only SQLite query on the database of Sam's ratings. Table: "
                         "ratings(title TEXT, year INTEGER, genres TEXT, stars INTEGER). genres lists the "
                         "film's genres separated by '|', for example 'Comedy|Romance'. stars is 1 to 5. " + LIMITS},
    "D": {"name": "query_other_ratings",
          "description": "Run one read-only SQLite query on the database of other film fans' ratings. Tables: "
                         "films(film_id INTEGER PRIMARY KEY, title TEXT, year INTEGER, genres TEXT) and "
                         "ratings(viewer INTEGER, film_id INTEGER, stars INTEGER). genres lists the film's "
                         "genres separated by '|', for example 'Comedy|Romance'. stars is 1 to 5. Sam is not "
                         "in this database. " + LIMITS},
}
TOOL_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["sql"],
               "properties": {"sql": {"type": "string", "description": "One SQLite SELECT statement."}}}


# ---------------------------------------------------------------- data preparation

def clean_title(raw):
    """'Matrix, The (1999)' -> ('The Matrix', 1999)."""
    m = re.match(r"^(.*?)\s*\((\d{4})\)$", raw)
    name, year = m.group(1), int(m.group(2))
    m = re.match(r"^(.*?), (The|A|An)( \(.*\))?$", name)
    if m:
        name = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    return name, year


def read_movielens():
    if hashlib.sha256(ZIP.read_bytes()).hexdigest() != ZIP_SHA256:
        sys.exit(f"{ZIP} does not match the pinned sha256 (download it from files.grouplens.org)")
    with zipfile.ZipFile(ZIP) as z:
        movies = z.read("ml-1m/movies.dat").decode("latin-1")
        ratings = z.read("ml-1m/ratings.dat").decode("latin-1")
    films = {}
    for line in movies.splitlines():
        film_id, raw, genres = line.split("::")
        title, year = clean_title(raw)
        films[int(film_id)] = {"title": title, "year": year, "genres": genres}
    by_user = collections.defaultdict(dict)
    for line in ratings.splitlines():
        user, film, stars, _timestamp = line.split("::")   # timestamps are not used
        by_user[int(user)][int(film)] = int(stars)
    return films, by_user


def prepare():
    films, by_user = read_movielens()
    # Friends: viewers with enough ratings, drawn in a seeded random order. A viewer is skipped when,
    # with the crowd computed without all friends chosen so far (and this viewer), any of them would
    # have fewer than N_SURPRISING surprising or N_TYPICAL typical candidate targets.
    eligible = sorted(u for u, r in by_user.items() if len(r) >= MIN_FRIEND_RATINGS)
    random.Random(SEED).shuffle(eligible)
    total, count = collections.Counter(), collections.Counter()
    for rated in by_user.values():
        for film, stars in rated.items():
            total[film] += stars
            count[film] += 1

    def candidates_for(user, excluded):
        sub_total, sub_count = collections.Counter(), collections.Counter()
        for other in excluded:
            for film, stars in by_user[other].items():
                sub_total[film] += stars
                sub_count[film] += 1
        rated = by_user[user]
        surprising, typical = [], []
        for film in sorted(rated):
            n_crowd = count[film] - sub_count[film]
            if n_crowd < MIN_TARGET_RATINGS:
                continue
            mean = (total[film] - sub_total[film]) / n_crowd
            (surprising if abs(rated[film] - mean) >= SURPRISE_STARS else typical).append(film)
        return surprising, typical

    friends, skipped = [], []
    for user in eligible:
        trial = friends + [user]
        if all(len(s) >= N_SURPRISING and len(t) >= N_TYPICAL
               for s, t in (candidates_for(u, trial) for u in trial)):
            friends = trial
        else:
            skipped.append(user)
        if len(friends) == N_FRIENDS:
            break
    if len(friends) < N_FRIENDS:
        sys.exit("not enough eligible friends")
    friends = sorted(friends)
    excluded = set(friends)
    crowd = collections.defaultdict(list)
    for user, rated in by_user.items():
        if user not in excluded:
            for film, stars in rated.items():
                crowd[film].append(stars)
    crowd_mean = {f: statistics.fmean(v) for f, v in crowd.items()}
    out_friends = []
    for i, user in enumerate(friends, 1):
        key = f"f{i:02d}"
        rated = by_user[user]
        surprising, typical = candidates_for(user, friends)
        assert all(abs(rated[f] - crowd_mean[f]) >= SURPRISE_STARS for f in surprising)
        pick = random.Random(f"{SEED}-{key}")
        chosen = {f: True for f in pick.sample(surprising, N_SURPRISING)}
        chosen.update({f: False for f in pick.sample(typical, N_TYPICAL)})
        # Display order: stable pseudo-random, so position does not reveal surprising vs typical.
        order = sorted(chosen, key=lambda f: hashlib.sha256(f"{key}:{f}".encode()).hexdigest())
        targets = [{"film_id": f, **films[f], "stars": rated[f], "surprising": chosen[f],
                    "crowd_mean": round(crowd_mean[f], 4), "crowd_n": len(crowd[f]),
                    "crowd_counts": {s: crowd[f].count(int(s)) for s in STARS}} for f in order]
        history = sorted((f for f in rated if f not in chosen), key=lambda f: (films[f]["title"], films[f]["year"]))
        out_friends.append({"key": key, "movielens_user": user, "n_rated": len(rated),
                            "n_history": len(history), "targets": targets})
        hist_db = OUT / "history" / f"{key}.sqlite"
        hist_db.parent.mkdir(parents=True, exist_ok=True)
        hist_db.unlink(missing_ok=True)
        con = sqlite3.connect(hist_db)
        con.execute("CREATE TABLE ratings (title TEXT, year INTEGER, genres TEXT, stars INTEGER)")
        con.executemany("INSERT INTO ratings VALUES (?, ?, ?, ?)",
                        [(films[f]["title"], films[f]["year"], films[f]["genres"], rated[f]) for f in history])
        con.commit()
        con.close()
    # The others database: everyone except the selected friends, with viewer numbers shuffled.
    others = sorted(u for u in by_user if u not in excluded)
    renumber = dict(zip(others, random.Random(f"{SEED}-viewers").sample(range(1, len(others) + 1), len(others))))
    OTHERS_DB.unlink(missing_ok=True)
    con = sqlite3.connect(OTHERS_DB)
    con.execute("CREATE TABLE films (film_id INTEGER PRIMARY KEY, title TEXT, year INTEGER, genres TEXT)")
    con.execute("CREATE TABLE ratings (viewer INTEGER, film_id INTEGER, stars INTEGER)")
    con.executemany("INSERT INTO films VALUES (?, ?, ?, ?)",
                    [(f, v["title"], v["year"], v["genres"]) for f, v in sorted(films.items())])
    con.executemany("INSERT INTO ratings VALUES (?, ?, ?)",
                    sorted((renumber[u], f, s) for u in others for f, s in by_user[u].items()))
    con.execute("CREATE INDEX ratings_film ON ratings (film_id)")
    con.execute("CREATE INDEX ratings_viewer ON ratings (viewer)")
    con.commit()
    counts = {"n_viewers": len(others), "n_films": con.execute("SELECT COUNT(DISTINCT film_id) FROM ratings").fetchone()[0],
              "n_ratings": con.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]}
    con.close()
    items = {"source_sha256": ZIP_SHA256, "seed": SEED, "skipped_viewers": len(skipped), "rule": {
        "n_friends": N_FRIENDS, "min_friend_ratings": MIN_FRIEND_RATINGS, "n_surprising": N_SURPRISING,
        "n_typical": N_TYPICAL, "surprise_stars": SURPRISE_STARS, "min_target_ratings": MIN_TARGET_RATINGS},
        "others": counts, "friends": out_friends}
    ITEMS.write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"friends": len(out_friends), **counts,
                      "history_sizes": [f["n_history"] for f in out_friends],
                      "items_sha256": hashlib.sha256(ITEMS.read_bytes()).hexdigest()}))


def load_items():
    if not ITEMS.exists():
        sys.exit("Run `prepare` first")
    items = json.loads(ITEMS.read_text())
    if items["source_sha256"] != ZIP_SHA256:
        sys.exit("items.json was built from a different source file")
    return items


def friend_by_key(items, key):
    for friend in items["friends"]:
        if friend["key"] == key:
            return friend
    sys.exit(f"No friend {key}")


def select_friends(items, spec):
    return items["friends"] if spec == "all" else [friend_by_key(items, k) for k in spec.split(",")]


# ---------------------------------------------------------------- the query tool

BLOCKED_FUNCTIONS = {"zeroblob", "randomblob", "load_extension", "readfile", "writefile", "edit"}


def _authorizer(action, arg1, arg2, *_):
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if (arg2 or "").lower() in BLOCKED_FUNCTIONS else sqlite3.SQLITE_OK
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def run_query(db_path, sql):
    """Run one read-only query. Returns (text, is_error, info). Never raises for a bad query."""
    started = time.monotonic()
    info = {"rows": 0, "truncated": False}
    if not isinstance(sql, str) or not sql.strip():
        return "Error: the query is empty.", True, info
    con = sqlite3.connect(f"file:{urllib.parse.quote(str(db_path))}?mode=ro", uri=True)
    try:
        con.set_authorizer(_authorizer)   # only reads: no ATTACH, PRAGMA, writes or temp tables
        con.set_progress_handler(lambda: int(time.monotonic() - started > QUERY_SECONDS), 10000)
        cur = con.execute(sql)
        names = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(ROW_CAP + 1)
        info["truncated"] = len(rows) > ROW_CAP
        rows = rows[:ROW_CAP]
        info["rows"] = len(rows)
        lines = [" | ".join(names)] + [" | ".join("" if v is None else str(v) for v in row) for row in rows]
        text = "\n".join(lines) if names else "(no result columns)"
        if not rows and names:
            text += "\n(no rows)"
        if info["truncated"]:
            text += f"\n(only the first {ROW_CAP} rows are shown)"
        if len(text) > RESULT_CHAR_CAP:
            text = text[:RESULT_CHAR_CAP] + f"\n(output cut at {RESULT_CHAR_CAP:,} characters)"
            info["truncated"] = True
        return text, False, info
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc):
            return f"Error: the query took longer than {QUERY_SECONDS} seconds and was stopped.", True, info
        return f"Error: {exc}", True, info
    except (sqlite3.Error, sqlite3.Warning, ValueError) as exc:
        return f"Error: {exc}", True, info
    finally:
        info["seconds"] = round(time.monotonic() - started, 3)
        con.close()


def tool_paths(friend):
    return {"H": OUT / "history" / f"{friend['key']}.sqlite", "D": OTHERS_DB}


# ---------------------------------------------------------------- prompts per agent

def target_list(friend):
    return "\n".join(f"{n}. {t['title']} ({t['year']}) - {t['genres'].replace('|', ', ')}"
                     for n, t in enumerate(friend["targets"], 1))


def data_text(items, friend, agent):
    return DATA_TEXT[agent].format(n_history=friend["n_history"], **items["others"])


def roles(setup):
    """Return (config, {H: role, D: role}, opener)."""
    if setup.startswith("peer-"):
        return "peer", {"H": "peer", "D": "peer"}, ("H" if setup == "peer-H-opens" else "D")
    lead = "H" if setup == "lead-H" else "D"
    return "hierarchy", {lead: "lead", ("D" if lead == "H" else "H"): "subordinate"}, lead


def system_prompt(items, friend, agent, role):
    other = "D" if agent == "H" else "H"
    parts = [COMMON.format(n=len(friend["targets"]), own=data_text(items, friend, agent),
                           other=OTHER_TEXT[other].format(n_history=friend["n_history"])),
             {"peer": PEER, "lead": LEAD, "subordinate": SUBORDINATE}[role]]
    if role != "subordinate":   # only the lead and peers give an answer
        parts.append(FORMAT)
    parts.append("Films:\n" + target_list(friend))
    return "\n\n".join(parts)


def solo_prompt(items, friend, agents):
    own = "\n\n".join(data_text(items, friend, a) for a in agents)
    return "\n\n".join([SOLO.format(n=len(friend["targets"]), own=own), FORMAT, "Films:\n" + target_list(friend)])


# ---------------------------------------------------------------- parsing

def probabilities(value, film=None):
    """Validate one film's probabilities. Sums within SUM_TOLERANCE of 1 are renormalized
    (the raw text stays in the transcript)."""
    where = f"film {film}: " if film is not None else ""
    if not isinstance(value, dict) or set(value) != set(STARS):
        raise ValueError(where + 'needs probabilities for exactly "1" to "5"')
    numbers = [value[s] for s in STARS]
    if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in numbers):
        raise ValueError(where + "probabilities must be numbers in [0,1]")
    total = sum(numbers)
    if not math.isclose(total, 1, abs_tol=SUM_TOLERANCE, rel_tol=0):
        raise ValueError(where + f"probabilities sum to {total:g}, not 1")
    return {s: float(value[s]) / total for s in STARS}


def find_answer(text, marker, n_films):
    """Return (found, answer_or_error). Answer maps film number (1-based) to probabilities."""
    lines = text.split("\n")
    bare = [line.strip().strip("*_#`: ") for line in lines]   # tolerate **FINAL**, FINAL:, ## FINAL
    if marker not in bare:
        return False, None
    body = "\n".join(lines[bare.index(marker) + 1:]).strip()
    if body.startswith("```"):
        body = body.strip("`").strip()
        if body.startswith("json"):
            body = body[4:]
    try:
        value, _ = json.JSONDecoder().raw_decode(body.strip())
        entries = value["films"]
        numbers = [e["film"] for e in entries]
        if any(type(n) is not int for n in numbers) or sorted(numbers) != list(range(1, n_films + 1)):
            raise ValueError(f"films must cover each film number 1-{n_films} exactly once")
        return True, {e["film"]: probabilities(e["probabilities"], e["film"]) for e in entries}
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return True, f"error: {exc}"[:200]


def is_agree(text):
    return re.match(r"[*_\s]*AGREE\b", text) is not None


# ---------------------------------------------------------------- model calls

def load_key(provider):
    wanted = {"anthropic": ("ANTHROPIC_API_KEY",), "openai": ("OPENAI_API_KEY", "OPEN_AI_API_KEY")}[provider]
    for line in KEYS_FILE.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() in wanted:
            return value.strip().strip('"').strip("'")
    sys.exit(f"No {provider} key found in the key file")


class CallFailed(Exception):
    """A model call that cannot be used. cost_usd is what it still cost."""
    def __init__(self, reason, cost_usd=0.0):
        super().__init__(reason)
        self.cost_usd = cost_usd


class BudgetStop(Exception):
    pass


class ToolCap(Exception):
    pass


def post_json(url, headers, body):
    """POST with retries on transient errors; raises CallFailed otherwise."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", **headers})
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = re.sub(r"(sk-|key-)[\w.*-]+", "[redacted]", e.read().decode(errors="replace"))[:300]
            if e.code not in (429, 500, 502, 503, 529) or attempt == 3:
                raise CallFailed(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 3:
                raise CallFailed(f"transport: {e!r}"[:300])
        time.sleep(10 * attempt)


class Anthropic:
    """Messages API with client tools. The full response content (thinking blocks included) is
    appended unchanged, so the history stays append-only."""
    def __init__(self, model, secret):
        self.model, self.secret = model, secret

    def request(self, system, history, tools):
        body = {"model": self.model, "max_tokens": MAX_TOKENS, "system": system, "messages": history,
                "cache_control": {"type": "ephemeral"}}
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": TOOL_SCHEMA}
                             for t in tools]
        data = post_json("https://api.anthropic.com/v1/messages",
                         {"x-api-key": self.secret, "anthropic-version": "2023-06-01"}, body)
        usage = data.get("usage") or {}
        p = PRICES[self.model]
        cost = ((usage.get("input_tokens") or 0) * p["input"]
                + (usage.get("cache_creation_input_tokens") or 0) * p["cache_write"]
                + (usage.get("cache_read_input_tokens") or 0) * p["cached"]
                + (usage.get("output_tokens") or 0) * p["output"]) / 1e6
        if data.get("stop_reason") in ("refusal", "max_tokens", "model_context_window_exceeded"):
            raise CallFailed(f"stop_reason {data['stop_reason']}", cost)
        content = data.get("content") or []
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        calls = [{"id": b["id"], "name": b["name"], "input": b.get("input")}
                 for b in content if b.get("type") == "tool_use"]
        meta = {"input_tokens": usage.get("input_tokens") or 0,
                "cache_write_tokens": usage.get("cache_creation_input_tokens") or 0,
                "cache_read_tokens": usage.get("cache_read_input_tokens") or 0,
                "output_tokens": usage.get("output_tokens") or 0, "cost_usd": cost,
                "stop_reason": data.get("stop_reason"), "model_returned": data.get("model"), "id": data.get("id")}
        return {"text": text, "tool_calls": calls, "meta": meta,
                "items": [{"role": "assistant", "content": content or "(empty)"}]}

    @staticmethod
    def tool_results(results):
        # All results of one response go back in a single user message.
        return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": r["id"], "content": r["text"],
                                              **({"is_error": True} if r["is_error"] else {})} for r in results]}]


class OpenAI:
    """Responses API, stateless (store=false): output items, including encrypted reasoning,
    are passed back as received."""
    def __init__(self, model, secret):
        self.model, self.secret = model, secret

    def request(self, system, history, tools):
        body = {"model": self.model, "store": False, "include": ["reasoning.encrypted_content"],
                "max_output_tokens": MAX_TOKENS,
                "input": [{"role": "system", "content": system}] + history}
        if tools:
            body["tools"] = [{"type": "function", "name": t["name"], "description": t["description"],
                              "parameters": TOOL_SCHEMA, "strict": True} for t in tools]
        data = post_json("https://api.openai.com/v1/responses", {"authorization": "Bearer " + self.secret}, body)
        usage = data.get("usage") or {}
        total, out = usage.get("input_tokens") or 0, usage.get("output_tokens") or 0  # out includes reasoning
        cached = (usage.get("input_tokens_details") or {}).get("cached_tokens") or 0
        p = PRICES[self.model]
        cost = ((total - cached) * p["input"] + cached * p["cached"] + out * p["output"]) / 1e6
        output = data.get("output") or []
        messages_out = [item for item in output if item.get("type") == "message"]
        text, refused = "", False
        # Keep only the last message item: joining commentary and final items doubled the text before.
        for part in (messages_out[-1].get("content", []) if messages_out else []):
            if part.get("type") == "output_text":
                text += part.get("text", "")
            elif part.get("type") == "refusal":
                refused = True
        if refused or data.get("status") != "completed":
            raise CallFailed("refusal" if refused else f"status {data.get('status')}: {data.get('incomplete_details')}",
                             cost)
        calls = []
        for item in output:
            if item.get("type") == "function_call":
                try:
                    args = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = None
                calls.append({"id": item["call_id"], "name": item.get("name"), "input": args})
        meta = {"input_tokens": total - cached, "cache_read_tokens": cached, "output_tokens": out,
                "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0,
                "cost_usd": cost, "message_items": len(messages_out),
                "message_item_phases": [item.get("phase") for item in messages_out],
                "model_returned": data.get("model"), "id": data.get("id")}
        return {"text": text, "tool_calls": calls, "meta": meta, "items": output}

    @staticmethod
    def tool_results(results):
        return [{"type": "function_call_output", "call_id": r["id"], "output": r["text"]} for r in results]


def make_adapter(model):
    if model not in PRICES:
        sys.exit(f"No prices for {model}")
    provider = PRICES[model]["provider"]
    return {"anthropic": Anthropic, "openai": OpenAI}[provider](model, load_key(provider))


# ---------------------------------------------------------------- one agent turn

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def agent_turn(adapter, system, history, tools, paths, state, agent, n_message, cap=MAX_TOOL_CALLS_PER_TURN):
    """Run one turn: model calls and queries until the agent writes its message. Returns the text.
    Appends to `history`, `state["calls"]` and `state["tool_log"]`; adds cost to `state["spent"]`.
    Past `cap` queries, each further query gets an error result asking for the message; if the agent
    still queries after that, the turn ends with ToolCap."""
    by_name = {t["name"]: a for a, t in TOOLS.items()}
    queries, refused_rounds = 0, 0
    while True:
        if state["spent"] + NEXT_CALL_RESERVE_USD > state["budget_left"]:
            raise BudgetStop("budget cap reached")
        try:
            resp = adapter.request(system, history, tools)
        except CallFailed as exc:
            state["spent"] += exc.cost_usd
            state["calls"].append({"agent": agent, "failure": str(exc)[:300], "cost_usd": exc.cost_usd})
            raise
        state["spent"] += resp["meta"]["cost_usd"]
        state["calls"].append({"agent": agent, "tool_calls": len(resp["tool_calls"]), **resp["meta"]})
        history.extend(resp["items"])
        if not resp["tool_calls"]:
            return resp["text"]
        results, refused = [], False
        for call in resp["tool_calls"]:
            queries += 1
            owner = by_name.get(call["name"])
            sql = (call["input"] or {}).get("sql") if isinstance(call["input"], dict) else None
            if queries > cap:
                refused = True
                text, is_error, info = ("Error: the query limit for this turn has been reached. "
                                        "Write your message now."), True, {"limit_reached": True}
            elif owner is None or owner not in paths:
                text, is_error, info = f"Error: no tool named {call['name']}.", True, {}
            else:
                text, is_error, info = run_query(paths[owner], sql)
            state["tool_log"].append({"agent": agent, "before_message": n_message, "tool": call["name"],
                                      "sql": sql, "is_error": is_error, **info, "result": text})
            results.append({"id": call["id"], "text": text, "is_error": is_error})
        history.extend(adapter.tool_results(results))
        if refused:
            refused_rounds += 1
            state["limit_hits"] = state.get("limit_hits", 0) + 1
            if refused_rounds > 1:
                raise ToolCap(f"kept querying after the limit of {cap} queries in one turn")


# ---------------------------------------------------------------- the dialogue

def run_dialogue(items, friend, setup, adapters, budget_left=math.inf):
    """One conversation. `adapters` is {"H": adapter, "D": adapter}. Never fills in missing answers."""
    config, role, opener = roles(setup)
    paths = tool_paths(friend)
    n = len(friend["targets"])
    systems = {a: system_prompt(items, friend, a, role[a]) for a in "HD"}
    tools = {a: [TOOLS[a]] for a in "HD"}
    views = {"H": [], "D": []}
    views[opener].append({"role": "user", "content": OPEN})
    state = {"spent": 0.0, "budget_left": budget_left, "calls": [], "tool_log": []}
    transcript, outcome, answer, error, pending, last_proposal = [], None, None, None, None, None
    rejected = []   # format attempts the harness sent back, with the note it sent
    speaker, started = opener, now()
    while outcome is None:
        if len(transcript) >= MAX_MESSAGES:
            outcome = "message_cap"
            break
        marker = {"peer": "PROPOSE", "lead": "FINAL", "subordinate": None}[role[speaker]]
        try:
            for retry in range(MAX_FORMAT_RETRIES + 1):
                text = agent_turn(adapters[speaker], systems[speaker], views[speaker], tools[speaker],
                                  {speaker: paths[speaker]}, state, speaker, len(transcript) + 1)
                found, parsed = find_answer(text, marker, n) if marker else (False, None)
                problem = "your message was empty" if not text.strip() else (
                    f"your {marker} answer could not be read ({parsed})" if found and isinstance(parsed, str) else None)
                if not problem:
                    break
                rejected.append({"agent": speaker, "before_message": len(transcript) + 1, "text": text,
                                 "problem": problem})
                views[speaker].append({"role": "user", "content":
                                       f"[Harness note, not from the other agent: {problem}. Send your message again.]"})
            else:
                outcome = "format_failure"
                break
        except BudgetStop as exc:
            outcome, error = "budget_stop", str(exc)
            break
        except ToolCap as exc:
            outcome, error = "tool_cap", str(exc)
            break
        except Exception as exc:   # CallFailed, or anything unexpected
            outcome, error = "error", repr(exc)[:300]
            break
        message = {"n": len(transcript) + 1, "agent": speaker, "role": role[speaker], "text": text}
        transcript.append(message)
        if role[speaker] == "lead" and found:
            outcome, answer, message["final"] = "final", parsed, True
            break
        if config == "peer":
            if pending and pending["by"] != speaker and is_agree(text):
                outcome, answer, message["agree"] = "agreed", pending["answer"], True
                message["agreed_to"] = pending["n"]
                break
            # The latest proposal stays open until a new proposal replaces it; AGREE from the other
            # agent accepts it, however many messages later.
            if found:
                pending = {"by": speaker, "answer": parsed, "n": message["n"]}
                message["proposal"] = True
                last_proposal = pending
        other = "D" if speaker == "H" else "H"
        views[other].append({"role": "user", "content": text})
        speaker = other
    return {"friend": friend["key"], "setup": setup, "config": config, "roles": role, "opener": opener,
            "outcome": outcome, "error": error, "answer": answer, "last_open_proposal": last_proposal,
            "transcript": transcript, "rejected_attempts": rejected, "tool_limit_hits": state.get("limit_hits", 0),
            "tool_log": state["tool_log"], "calls": state["calls"], "systems": systems, "started_at_utc": started, "finished_at_utc": now(),
            "cost_usd": round(state["spent"], 6)}


def run_solo(items, friend, agents, adapter, budget_left=math.inf):
    """One agent alone with the tools of `agents` ("H", "D" or "HD"); it ends with FINAL."""
    paths = tool_paths(friend)
    n = len(friend["targets"])
    system = solo_prompt(items, friend, agents)
    history = [{"role": "user", "content": OPEN_SOLO}]
    state = {"spent": 0.0, "budget_left": budget_left, "calls": [], "tool_log": []}
    outcome, answer, error, text, started, rejected = None, None, None, "", now(), []
    try:
        for retry in range(MAX_FORMAT_RETRIES + 1):
            text = agent_turn(adapter, system, history, [TOOLS[a] for a in agents],
                              {a: paths[a] for a in agents}, state, "solo", 1, cap=MAX_TOOL_CALLS_SOLO)
            found, parsed = find_answer(text, "FINAL", n)
            if found and not isinstance(parsed, str):
                outcome, answer = "final", parsed
                break
            problem = (f"your FINAL answer could not be read ({parsed})" if found
                       else "no answer was found; write FINAL on its own line, followed by the answer as JSON")
            rejected.append({"text": text, "problem": problem})
            history.append({"role": "user", "content": f"[Harness note: {problem}.]"})
        else:
            outcome = "format_failure"
    except BudgetStop as exc:
        outcome, error = "budget_stop", str(exc)
    except ToolCap as exc:
        outcome, error = "tool_cap", str(exc)
    except Exception as exc:
        outcome, error = "error", repr(exc)[:300]
    return {"friend": friend["key"], "setup": f"solo-{agents}", "outcome": outcome, "error": error,
            "answer": answer, "final_text": text, "rejected_attempts": rejected,
            "tool_limit_hits": state.get("limit_hits", 0), "tool_log": state["tool_log"], "calls": state["calls"],
            "system": system, "started_at_utc": started, "finished_at_utc": now(),
            "cost_usd": round(state["spent"], 6)}


# ---------------------------------------------------------------- scoring

def expected(p):
    return sum(int(s) * p[s] for s in STARS)


def rps(p, truth):
    """Ranked probability score over 1-5 stars, normalized to 0..1 (0 is perfect)."""
    cum_p, cum_t, total = 0.0, 0.0, 0.0
    for s in STARS[:-1]:
        cum_p += p[s]
        cum_t += float(int(s) == truth)
        total += (cum_p - cum_t) ** 2
    return total / (len(STARS) - 1)


def score_answer(friend, answer):
    """answer maps film number (1-based) to probabilities."""
    rows = []
    for n, t in enumerate(friend["targets"], 1):
        p = answer[n]
        rows.append({"film": n, "film_id": t["film_id"], "stars": t["stars"], "surprising": t["surprising"],
                     "expected": round(expected(p), 4), "abs_error": round(abs(expected(p) - t["stars"]), 4),
                     "rps": round(rps(p, t["stars"]), 4)})

    def mean_of(key, subset):
        values = [r[key] for r in rows if subset(r)]
        return round(statistics.fmean(values), 4) if values else None
    return {"abs_error": mean_of("abs_error", lambda r: True), "rps": mean_of("rps", lambda r: True),
            "abs_error_surprising": mean_of("abs_error", lambda r: r["surprising"]),
            "abs_error_typical": mean_of("abs_error", lambda r: not r["surprising"]),
            "rps_surprising": mean_of("rps", lambda r: r["surprising"]),
            "rps_typical": mean_of("rps", lambda r: not r["surprising"]), "films": rows}


def summary(record):
    calls = record["calls"]
    return {"setup": record["setup"], "outcome": record["outcome"], "messages": len(record.get("transcript", [])),
            "model_calls": len(calls), "queries": len(record["tool_log"]),
            "input_tokens": sum(c.get("input_tokens", 0) + c.get("cache_write_tokens", 0) for c in calls),
            "cache_read_tokens": sum(c.get("cache_read_tokens", 0) for c in calls),
            "output_tokens": sum(c.get("output_tokens", 0) for c in calls),
            "rejected_attempts": len(record.get("rejected_attempts", [])),
            "tool_limit_hits": record.get("tool_limit_hits", 0), "cost_usd": record["cost_usd"]}


# ---------------------------------------------------------------- reference baselines (free)

def recommender(history, target_film, others_by_viewer, viewers_by_film, k=50, min_overlap=20):
    """Neighbour-based collaborative filtering (Pearson similarity on co-rated films). Returns
    (predicted rating or None, weighted distribution of neighbours' ratings or None)."""
    sam_mean = statistics.fmean(history.values())
    sims = []
    for viewer in viewers_by_film.get(target_film, ()):
        theirs = others_by_viewer[viewer]
        common = [f for f in history if f in theirs]
        if len(common) < min_overlap:
            continue
        a = [history[f] for f in common]
        b = [theirs[f] for f in common]
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
        if den > 0 and num > 0:
            sims.append((num / den, viewer))
    sims = sorted(sims, reverse=True)[:k]
    if not sims:
        return None, None
    total = sum(s for s, _ in sims)
    shift = sum(s * (others_by_viewer[v][target_film] - statistics.fmean(others_by_viewer[v].values()))
                for s, v in sims) / total
    # Distribution: each neighbour's rating, moved by the gap between Sam's mean and theirs.
    def adjusted(v):
        r = others_by_viewer[v][target_film] - statistics.fmean(others_by_viewer[v].values()) + sam_mean
        return min(5, max(1, round(r)))
    dist = {st: sum(s for s, v in sims if adjusted(v) == int(st)) / total for st in STARS}
    return min(5.0, max(1.0, sam_mean + shift)), dist


def baselines():
    items = load_items()
    films, by_user = read_movielens()
    friends = {f["movielens_user"] for f in items["friends"]}
    others_by_viewer = {u: r for u, r in by_user.items() if u not in friends}
    viewers_by_film = collections.defaultdict(list)
    for u, rated in others_by_viewer.items():
        for f in rated:
            viewers_by_film[f].append(u)
    rows = {"crowd": [], "recommender": []}
    for friend in items["friends"]:
        target_ids = {t["film_id"] for t in friend["targets"]}
        history = {f: s for f, s in by_user[friend["movielens_user"]].items() if f not in target_ids}
        crowd_answer, rec_answer, rec_points = {}, {}, {}
        for n, t in enumerate(friend["targets"], 1):
            counts = t["crowd_counts"]
            crowd_answer[n] = {s: counts[s] / t["crowd_n"] for s in STARS}
            point, dist = recommender(history, t["film_id"], others_by_viewer, viewers_by_film)
            rec_answer[n] = dist or crowd_answer[n]
            rec_points[n] = point if point is not None else t["crowd_mean"]
        rows["crowd"].append(score_answer(friend, crowd_answer))
        scored = score_answer(friend, rec_answer)
        for r in scored["films"]:   # the recommender's point prediction, not its neighbour histogram mean
            r["expected"] = round(rec_points[r["film"]], 4)
            r["abs_error"] = round(abs(rec_points[r["film"]] - r["stars"]), 4)
        rows["recommender"].append(scored)
    out = {}
    for name, scored in rows.items():
        films_all = [r for s in scored for r in s["films"]]

        def m(key, pick):
            return round(statistics.fmean(r[key] for r in films_all if pick(r)), 4)
        out[name] = {"abs_error": m("abs_error", lambda r: True), "rps": m("rps", lambda r: True),
                     "abs_error_surprising": m("abs_error", lambda r: r["surprising"]),
                     "abs_error_typical": m("abs_error", lambda r: not r["surprising"]),
                     "rps_surprising": m("rps", lambda r: r["surprising"]),
                     "rps_typical": m("rps", lambda r: not r["surprising"])}
    (OUT / "baselines.json").write_text(json.dumps({"summary": out, "per_friend": rows}, indent=1) + "\n")
    print(json.dumps(out, indent=1))


# ---------------------------------------------------------------- offline checks

class Fake:
    """Scripted stand-in adapter. `script` is a function (system, history) -> response dict, or a
    list of responses consumed in order (a CallFailed instance is raised)."""
    def __init__(self, script, cost=0.0):
        self.script, self.cost = script, cost

    def request(self, system, history, tools):
        assert history and history[0]["role"] == "user"
        reply = self.script(system, history) if callable(self.script) else self.script.pop(0)
        if isinstance(reply, CallFailed):
            raise reply
        if isinstance(reply, str):
            reply = {"text": reply}
        calls = reply.get("tool_calls", [])
        return {"text": reply.get("text", ""), "tool_calls": calls,
                "meta": {"input_tokens": 1, "output_tokens": 1, "cost_usd": self.cost},
                "items": [{"role": "assistant", "content": reply.get("text") or "(tool call)", "calls": calls}]}

    @staticmethod
    def tool_results(results):
        return [{"role": "user", "content": json.dumps([r["text"] for r in results])}]


def uniform_answer(n):
    return json.dumps({"films": [{"film": i, "probabilities": {"1": 0.1, "2": 0.2, "3": 0.4, "4": 0.2, "5": 0.1}}
                                 for i in range(1, n + 1)]})


def fake_agent(n):
    """Queries once, talks twice, then proposes/finalizes, and agrees to proposals."""
    def script(system, history):
        mine = sum(1 for m in history if m["role"] == "assistant" and m.get("content") != "(tool call)")
        last = history[-1]["content"]
        if history[-1]["role"] == "user" and isinstance(last, str) and "PROPOSE\n" in last:
            return "AGREE"
        if not any(m.get("calls") for m in history if m["role"] == "assistant"):
            name = "query_sam_ratings" if "Sam's own ratings of" in system.split("The other agent")[0] \
                else "query_other_ratings"
            if "You are predicting" in system and "query_sam" not in name:
                name = "query_other_ratings"
            return {"tool_calls": [{"id": "c1", "name": name, "input": {"sql": "SELECT COUNT(*) AS n FROM ratings"}}]}
        if mine < 2 and "You are predicting" not in system:
            return f"Fake message {mine + 1}."
        if "You are the lead" in system or "You are predicting" in system:
            return "FINAL\n" + uniform_answer(n)
        if "equals" in system:
            return "PROPOSE\n" + uniform_answer(n)
        return "Noted."
    return script


def dry_run():
    items = load_items()
    friend = items["friends"][0]
    n = len(friend["targets"])
    paths = tool_paths(friend)
    # The query tool: reads work; writes, ATTACH, PRAGMA and multiple statements are refused.
    text, err, info = run_query(paths["H"], "SELECT COUNT(*) FROM ratings")
    assert not err and int(text.split("\n")[1]) == friend["n_history"], text
    text, err, info = run_query(paths["D"], "SELECT viewer, film_id, stars FROM ratings")
    assert not err and info["rows"] == ROW_CAP and info["truncated"], info
    for bad in ("DELETE FROM ratings", "INSERT INTO ratings VALUES ('x', 1, 'y', 5)", "PRAGMA table_info(ratings)",
                f"ATTACH DATABASE '{paths['H']}' AS h", "CREATE TEMP TABLE t (x)",
                "SELECT 1; SELECT 2", "", "SELECT * FROM nonexistent", "SELECT length(zeroblob(1000000000))",
                "SELECT hex(randomblob(1000000000))"):
        text, err, _ = run_query(paths["D"], bad)
        assert err, (bad, text)
    text, err, _ = run_query(paths["D"], "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
                                         "SELECT MAX(x) FROM c")
    assert err and "longer than" in text, text
    # The database agent cannot reach Sam's ratings: no friend's ratings are in the others database.
    con = sqlite3.connect(f"file:{OTHERS_DB}?mode=ro", uri=True)
    n_others = con.execute("SELECT COUNT(DISTINCT viewer) FROM ratings").fetchone()[0]
    con.close()
    assert n_others == items["others"]["n_viewers"]
    _, by_user = read_movielens()
    assert n_others == len(by_user) - N_FRIENDS
    # No target appears in its friend's history.
    con = sqlite3.connect(f"file:{paths['H']}?mode=ro", uri=True)
    hist = set(con.execute("SELECT title, year FROM ratings").fetchall())
    con.close()
    assert not hist & {(t["title"], t["year"]) for t in friend["targets"]}
    print("query tool checks passed")

    for setup in SETUPS:
        record = run_dialogue(items, friend, setup, {"H": Fake(fake_agent(n)), "D": Fake(fake_agent(n))})
        assert record["outcome"] in ("final", "agreed"), (setup, record["outcome"], record["error"])
        assert {e["agent"] for e in record["tool_log"]} == {"H", "D"}
        assert all(not e["is_error"] for e in record["tool_log"]), record["tool_log"]
        s = score_answer(friend, record["answer"])
        print(json.dumps({**summary(record), "abs_error": s["abs_error"], "rps": s["rps"]}))
    for agents in ("H", "D", "HD"):
        record = run_solo(items, friend, agents, Fake(fake_agent(n)))
        assert record["outcome"] == "final", (agents, record)
    # Each agent's tool reaches its own database only.
    _, role, _ = roles("peer-H-opens")
    assert "query_other_ratings" not in json.dumps([TOOLS["H"]]) and "Sam is not" not in TOOLS["H"]["description"]
    record = run_dialogue(items, friend, "lead-H", {
        "H": Fake([{"tool_calls": [{"id": "x", "name": "query_other_ratings", "input": {"sql": "SELECT 1"}}]},
                   "FINAL\n" + uniform_answer(n)]),
        "D": Fake(["unused"])})
    assert record["outcome"] == "final" and record["tool_log"][0]["is_error"], record["tool_log"]

    good = "FINAL\n" + uniform_answer(n)
    checks = [  # (setup, H replies, D replies, outcome, delivered messages)
        ("peer-H-opens", ["hi", "**AGREE** glad"], ["PROPOSE\n" + uniform_answer(n)], "agreed", 3),
        ("lead-D", [], ["FINAL\n{bad", "", "Thinking.\nFINAL\n```json\n" + uniform_answer(n) + "\n```"], "final", 1),
        ("lead-D", [], ["FINAL\n{bad"] * 3, "format_failure", 0),
        ("lead-H", ["hi", good], [good], "final", 3),   # the subordinate's FINAL is just text
        ("peer-D-opens", [CallFailed("HTTP 500", 0.01)], ["hi"], "error", 1),
        # The latest proposal stays open: an AGREE two messages later still accepts it.
        ("peer-H-opens", ["PROPOSE\n" + uniform_answer(n), "It is the genre pattern."], ["Why film 3?", "AGREE"],
         "agreed", 4),
        # A counter-proposal replaces the open one; the proposer's own AGREE does not count.
        ("peer-H-opens", ["PROPOSE\n" + uniform_answer(n), "AGREE"], ["PROPOSE\n" + uniform_answer(n)], "agreed", 3),
        ("peer-H-opens", ["a"] * 20, ["AGREE"] * 20, "message_cap", 20),
        # Past the query limit the agent is told to write; querying again after that ends the turn.
        ("lead-H", [{"tool_calls": [{"id": str(i), "name": "query_sam_ratings", "input": {"sql": "SELECT 1"}}
                                    for i in range(MAX_TOOL_CALLS_PER_TURN + 1)]}, good], [], "final", 1),
        ("lead-H", [{"tool_calls": [{"id": str(i), "name": "query_sam_ratings", "input": {"sql": "SELECT 1"}}
                                    for i in range(MAX_TOOL_CALLS_PER_TURN + 1)]},
                    {"tool_calls": [{"id": "z", "name": "query_sam_ratings", "input": {"sql": "SELECT 1"}}]}],
         [], "tool_cap", 0),
        ("lead-H", [{"tool_calls": [{"id": "1", "name": "query_sam_ratings", "input": None}]}, good], [], "final", 1),
    ]
    for setup, h, d, outcome, delivered in checks:
        record = run_dialogue(items, friend, setup, {"H": Fake(list(h)), "D": Fake(list(d))})
        assert (record["outcome"], len(record["transcript"])) == (outcome, delivered), \
            (setup, record["outcome"], len(record["transcript"]), record["error"])
    record = run_dialogue(items, friend, "peer-H-opens", {"H": Fake(["PROPOSE\n" + uniform_answer(n), "Genres."]),
                                                          "D": Fake(["Why?", "AGREE"])})
    assert record["transcript"][-1].get("agreed_to") == 1, record["transcript"]
    # Probabilities: a sum within the tolerance is renormalized; a larger miss names the film.
    near = json.loads(uniform_answer(n))
    near["films"][2]["probabilities"]["3"] = 0.395
    found, parsed = find_answer("FINAL\n" + json.dumps(near), "FINAL", n)
    assert found and math.isclose(sum(parsed[3].values()), 1), parsed
    near["films"][2]["probabilities"]["3"] = 0.3
    found, parsed = find_answer("FINAL\n" + json.dumps(near), "FINAL", n)
    assert isinstance(parsed, str) and "film 3" in parsed, parsed
    record = run_dialogue(items, friend, "lead-D", {"H": Fake([]), "D": Fake(["FINAL\n" + json.dumps(near), good])})
    assert record["outcome"] == "final" and len(record["rejected_attempts"]) == 1, record["rejected_attempts"]
    record = run_dialogue(items, friend, "peer-H-opens", {"H": Fake(["x"] * 30, 0.3), "D": Fake(["y"] * 30, 0.3)},
                          budget_left=1.0)
    assert record["outcome"] == "budget_stop" and record["cost_usd"] <= 1.0, record["cost_usd"]
    record = run_solo(items, friend, "HD", Fake(["no marker", "still none", "nope"]))
    assert record["outcome"] == "format_failure"
    # Scoring: a point mass on the truth scores 0; the scorer reads film numbers in display order.
    perfect = {i: {s: float(int(s) == t["stars"]) for s in STARS} for i, t in enumerate(friend["targets"], 1)}
    s = score_answer(friend, perfect)
    assert s["abs_error"] == 0 and s["rps"] == 0
    assert math.isclose(rps({"1": 1, "2": 0, "3": 0, "4": 0, "5": 0}, 5), 1.0)
    # Prompts: the subordinate gets no answer format; nobody sees the other agent's tool.
    for setup in SETUPS:
        _, role, _ = roles(setup)
        for agent in "HD":
            text = system_prompt(items, friend, agent, role[agent])
            assert ("Answer JSON" in text) == (role[agent] != "subordinate")
            assert str(friend["movielens_user"]) not in text and "MovieLens" not in text
    print("edge-case checks passed")


# ---------------------------------------------------------------- paid runs

def provenance():
    return {"harness_version": HARNESS_VERSION,
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_sha256": ZIP_SHA256, "items_sha256": hashlib.sha256(ITEMS.read_bytes()).hexdigest(),
            "max_messages": MAX_MESSAGES, "max_tool_calls_per_turn": MAX_TOOL_CALLS_PER_TURN,
            "row_cap": ROW_CAP, "query_seconds": QUERY_SECONDS}


def run_plan(label, cap, plan, execute):
    """plan: list of (name, args); execute(args, budget_left) -> record. Writes outside the repo."""
    out_dir = PRIVATE / "runs" / label
    out_dir.mkdir(parents=True, exist_ok=False)
    spent, rows, errors_in_a_row = 0.0, [], 0
    try:
        for name, args in plan:
            record, extra = execute(args, cap - spent)
            spent += record["cost_usd"]
            record.update({**extra, **provenance()})
            (out_dir / f"{name}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
            sc = record.get("score") or {}
            rows.append({"name": name, **extra, **summary(record), "abs_error": sc.get("abs_error"),
                         "rps": sc.get("rps"), "error": record["error"]})
            print(json.dumps(rows[-1]), flush=True)
            errors_in_a_row = errors_in_a_row + 1 if record["outcome"] == "error" else 0
            if record["outcome"] == "budget_stop" or errors_in_a_row >= 2:
                print(f"stopping: {record['error']}")
                break
    finally:
        (out_dir / "summary.json").write_text(json.dumps(
            {"label": label, "cap_usd": cap, "total_cost_usd": round(spent, 4), "planned": len(plan),
             "completed": len(rows), "rows": rows, **provenance()}, indent=1) + "\n")
        print(f"total ${spent:.4f} -> {out_dir}")


def smoke(label, cap, friends_spec, pairings):
    items = load_items()
    friends = select_friends(items, friends_spec)
    pairs = [tuple(p.split("/")) for p in pairings]
    if not pairs or any(len(pair) != 2 for pair in pairs):
        sys.exit("Pairings must look like MODEL_H/MODEL_D")
    adapters = {m: make_adapter(m) for m in sorted({m for pair in pairs for m in pair})}
    # Friends outer, each a complete block; within a friend the setups and pairings run in a seeded
    # shuffled order, so an early stop never empties a setup and time trends do not line up with setups.
    plan = []
    for f in friends:
        block = [(f"{f['key']}__{mh}__{md}__{setup}", (f, setup, mh, md)) for setup in SETUPS for mh, md in pairs]
        random.Random(f"{SEED}-order-{label}-{f['key']}").shuffle(block)
        plan += block

    def execute(args, budget_left):
        friend, setup, mh, md = args
        record = run_dialogue(items, friend, setup, {"H": adapters[mh], "D": adapters[md]}, budget_left)
        record["score"] = score_answer(friend, record["answer"]) if record["answer"] else None
        return record, {"models": {"H": mh, "D": md},
                        "settings_sent": {"H": SETTINGS_SENT[PRICES[mh]["provider"]],
                                          "D": SETTINGS_SENT[PRICES[md]["provider"]]}}
    run_plan(label, cap, plan, execute)


def solo(label, cap, friends_spec, tools, model, reps):
    items = load_items()
    agents = {"history": "H", "database": "D", "both": "HD"}[tools]
    friends = select_friends(items, friends_spec)
    adapter = make_adapter(model)
    plan = [(f"{f['key']}__{model}__solo-{agents}__rep{r}", f) for r in range(1, reps + 1) for f in friends]

    def execute(friend, budget_left):
        record = run_solo(items, friend, agents, adapter, budget_left)
        record["score"] = score_answer(friend, record["answer"]) if record["answer"] else None
        return record, {"models": {"solo": model}, "settings_sent": SETTINGS_SENT[PRICES[model]["provider"]]}
    run_plan(label, cap, plan, execute)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "prepare":
        prepare()
    elif command == "baselines":
        baselines()
    elif command == "prompts":
        items = load_items()
        friend = friend_by_key(items, sys.argv[2])
        if sys.argv[3].startswith("solo-"):
            print(solo_prompt(items, friend, sys.argv[3][5:]))
        else:
            _, role, opener = roles(sys.argv[3])
            for agent in "HD":
                print(f"===== Agent {agent} ({role[agent]}{', opens' if agent == opener else ''}) =====")
                print(system_prompt(items, friend, agent, role[agent]))
                print(f"[tool] {TOOLS[agent]['name']}: {TOOLS[agent]['description']}\n")
    elif command == "dry-run":
        dry_run()
    elif command == "smoke":
        smoke(sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5:])
    elif command == "solo":
        solo(sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6],
             int(sys.argv[7]) if len(sys.argv) > 7 else 1)
    else:
        sys.exit(__doc__)
