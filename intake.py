"""A deterministic dispute intake policy for one synthetic cardholder."""
import json
import re
import sqlite3
import uuid
from datetime import date
from contextlib import contextmanager

TRANSACTIONS = [
    {"id":"T101","merchant":"Harbor Books","cents":2450,"date":"2026-05-12","aliases":["harbor","harbour"]},
    {"id":"T102","merchant":"Maple Market","cents":4200,"date":"2026-05-14","aliases":["maple"]},
    {"id":"T103","merchant":"North Star Coffee","cents":675,"date":"2026-05-15","aliases":["north star","northstar"]},
    {"id":"T104","merchant":"Harbor Books","cents":1800,"date":"2026-05-16","aliases":["harbor","harbour"]},
]
REASONS = {
    "duplicate charge": ("charged twice","duplicate","charged two times","billed twice"),
    "unrecognized charge": ("do not recognize","don't recognize","did not make","didn't make","unauthorized","unrecognized","not my purchase"),
    "goods not received": ("never arrived","never received","did not arrive","didn't arrive","not received"),
}
OPENING = "Hi, I can help with a payment dispute. Which merchant was the charge from?"
SCHEMA = """
CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS turns(call_id TEXT, seq INTEGER, request_id TEXT, transcript TEXT, reply TEXT,
                                 PRIMARY KEY(call_id,seq), UNIQUE(call_id,request_id));
CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, call_id TEXT UNIQUE, document TEXT NOT NULL);
"""


@contextmanager
def connection(path):
    db = sqlite3.connect(path, timeout=10)
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path):
    with connection(path) as db:
        db.executescript(SCHEMA)


def start(path):
    call_id = uuid.uuid4().hex
    state = dict(stage="payment", transaction=None, reason=None, seq=0, case_id=None)
    with connection(path) as db:
        db.execute("INSERT INTO calls VALUES (?,?)", (call_id,json.dumps(state)))
    return dict(call_id=call_id, prompt=OPENING, **state)


def describe_payment(item):
    day = date.fromisoformat(item["date"])
    dollars, cents = divmod(item["cents"], 100)
    amount = f"{dollars} dollars"
    if cents:
        amount += f" and {cents} cents"
    return f"{amount} at {item['merchant']} on {day:%B} {day.day}, {day.year}"


def readback(state, item):
    state["stage"] = "confirm"
    return (f"Let me read that back. You're disputing {describe_payment(item)}. "
            f"The reason is {state['reason']}. Say confirm, change the payment, or change the reason.")


def select_payment(state, item):
    state["transaction"] = item["id"]
    if state["reason"]:
        return readback(state, item)
    state["stage"] = "reason"
    return f"I found a charge for {describe_payment(item)}. What happened?"


def offer_choices(items):
    options = " ".join(f"Option {i}. {describe_payment(item)}." for i, item in enumerate(items, 1))
    return f"I found several charges. {options} Please say the option number, or say change the merchant."


def parse_choice(words, count):
    labels = (("one", "first"), ("two", "second"), ("three", "third"))
    for index in range(count):
        numbers = [str(index + 1)]
        if index < len(labels):
            numbers.extend(labels[index])
        for number in numbers:
            if words in (number, f"option {number}", f"number {number}", f"the {number} one",
                         f"the {number} charge", f"the {number} option"):
                return index
    return None


def transition(state, text):
    words = re.sub(r"[^a-z0-9' ]+", " ", text.lower().replace("’","'"))
    words = " ".join(words.split())
    if words in ("cancel", "cancel the dispute", "stop"):
        state["stage"] = "cancelled"
        return "Intake cancelled. No case was opened."
    if state["stage"] == "choose_payment":
        if words in ("start over", "change the merchant", "change the payment"):
            state.update(stage="payment", transaction=None)
            state.pop("choices")
            return "Which merchant should I look up?"
        by_id = {item["id"]: item for item in TRANSACTIONS}
        choices = [by_id[key] for key in state["choices"]]
        choice = parse_choice(words, len(choices))
        if choice is None:
            return offer_choices(choices)
        state.pop("choices")
        return select_payment(state, choices[choice])
    if state["stage"] == "payment":
        matches = [t for t in TRANSACTIONS if any(re.search(r"\b"+a+r"\b", words) for a in t["aliases"])]
        if len({item["merchant"] for item in matches}) != 1:
            return "Please choose one merchant: Harbor Books, Maple Market, or North Star Coffee."
        if len(matches) > 1:
            state.update(stage="choose_payment", choices=[item["id"] for item in matches])
            return offer_choices(matches)
        return select_payment(state, matches[0])
    item = next(t for t in TRANSACTIONS if t["id"] == state["transaction"])
    if state["stage"] == "reason":
        matches = [label for label, phrases in REASONS.items() if any(p in words for p in phrases)]
        denies_duplicate = re.search(
            r"\b(?:not|never|wasn't|isn't|weren't) (?:a |an |being )?(?:duplicate|charged|billed)\b", words
        )
        if len(matches) != 1 or denies_duplicate:
            return "Please describe one issue: a duplicate charge, an unrecognized charge, or goods that never arrived."
        state["reason"] = matches[0]
        return readback(state, item)
    if words in ("change the payment", "change the merchant"):
        state.update(stage="payment", transaction=None)
        return "Which merchant should I use instead?"
    if words == "change the reason":
        state.update(stage="reason", reason=None)
        return "What happened with this payment?"
    if words in ("start over","no","no start over"):
        state.update(stage="payment",transaction=None,reason=None)
        return "Let's correct the details. Which merchant was the payment with?"
    if words in ("confirm","yes confirm","i confirm","confirm the dispute","yes please open the case"):
        state.update(stage="opened",case_id="DSP-"+uuid.uuid4().hex[:12].upper())
        return "Your case is open. You can see the reference and the call details in your case record."
    return "I need explicit confirmation. Say confirm, start over, or cancel."


class Conflict(Exception):
    pass


def advance(path, call_id, seq, request_id, text):
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT state FROM calls WHERE id=?", (call_id,)).fetchone()
        if not row:
            raise KeyError("unknown call")
        previous = db.execute("SELECT seq,reply FROM turns WHERE call_id=? AND request_id=?", (call_id,request_id)).fetchone()
        if previous:
            if previous[0] != seq + 1:
                raise Conflict("turn ID already used")
            return json.loads(previous[1])
        state = json.loads(row[0])
        if state["seq"] != seq or state["stage"] in ("opened","cancelled"):
            raise Conflict("stale or closed call")
        prompt = transition(state, text)
        state["seq"] += 1
        response = dict(call_id=call_id,prompt=prompt,heard=text,**state)
        db.execute("UPDATE calls SET state=? WHERE id=?", (json.dumps(state),call_id))
        db.execute("INSERT INTO turns VALUES (?,?,?,?,?)",
                   (call_id,state["seq"],request_id,text,json.dumps(response)))
        if state["stage"] == "opened":
            item = next(t for t in TRANSACTIONS if t["id"] == state["transaction"])
            turns = db.execute("SELECT seq,transcript,reply FROM turns WHERE call_id=? ORDER BY seq", (call_id,))
            document = dict(case_id=state["case_id"],call_id=call_id,status="awaiting_review",
                            transaction={k:v for k,v in item.items() if k!="aliases"},currency="USD",
                            reason=state["reason"],opening_prompt=OPENING,
                            transcript=[dict(turn=n,caller=t,agent=json.loads(r)["prompt"]) for n,t,r in turns])
            db.execute("INSERT INTO cases VALUES (?,?,?)", (state["case_id"],call_id,json.dumps(document)))
        return response


def case(path, key):
    with connection(path) as db:
        row = db.execute("SELECT document FROM cases WHERE id=?", (key,)).fetchone()
    if not row:
        raise KeyError("unknown case")
    return json.loads(row[0])
