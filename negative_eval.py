"""Exercise ambiguous and cancelled spoken intake against the server and its database."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.error import HTTPError

from replay import ROOT, request, speak_turn


def evaluate(base, db_path):
    call = json.loads(request(base + "/calls", b""))
    steps = [
        ("harbor-books", "choose_payment", None, None),
        ("negative/ambiguous-choice", "choose_payment", None, None),
        ("option-two", "reason", "T104", None),
        ("negative/negated-duplicate", "reason", "T104", None),
        ("turn-2", "confirm", "T104", "duplicate charge"),
        ("negative/decline", "confirm", "T104", "duplicate charge"),
        ("negative/cancel", "cancelled", "T104", "duplicate charge"),
    ]
    history = []
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        for n, (name, stage, transaction, reason) in enumerate(steps, 1):
            audio = (ROOT / "fixtures" / f"{name}.wav").read_bytes()
            call = speak_turn(base, call, n, audio)
            observed = (call["stage"], call["transaction"], call["reason"], call["case_id"])
            if observed != (stage, transaction, reason, None):
                raise RuntimeError(f"{name}: heard {call['heard']!r}, got {observed}")
            history.append({"fixture": name, "heard": call["heard"], "stage": stage, "reply": call["prompt"]})

        try:
            speak_turn(base, call, len(steps) + 1, (ROOT / "fixtures/turn-3.wav").read_bytes())
        except HTTPError as exc:
            if exc.code != 409:
                raise
        else:
            raise RuntimeError("A late confirmation was accepted after cancellation")

        key = (call["call_id"],)
        row = db.execute("SELECT state FROM calls WHERE id=?", key).fetchone()
        cases = db.execute("SELECT count(*) FROM cases WHERE call_id=?", key).fetchone()[0]
        if row is None or json.loads(row[0])["stage"] != "cancelled" or cases:
            raise RuntimeError("Expected a persisted cancelled call with zero cases")

    return {"call_id": call["call_id"], "turns": history, "late_confirmation_http": 409, "cases_created": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--db", type=Path, required=True, help="SQLite file used by the running agent")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.url.rstrip("/"), args.db), indent=2))
