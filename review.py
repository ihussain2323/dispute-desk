"""Render a confirmed dispute from its persisted case snapshot."""
from datetime import date
from html import escape
from urllib.parse import quote


def render_case(record):
    transaction = record["transaction"]
    case_id = escape(record["case_id"])
    dollars, cents = divmod(transaction["cents"], 100)
    posted = date.fromisoformat(transaction["date"])
    fields = [
        ("Merchant", transaction["merchant"]),
        ("Amount", f"${dollars:,}.{cents:02d} {record['currency']}"),
        ("Transaction date", f"{posted:%B} {posted.day}, {posted.year}"),
        ("Transaction ID", transaction["id"]),
        ("Dispute reason", record["reason"]),
    ]
    summary = "".join(f"<dt>{label}</dt><dd>{escape(value)}</dd>" for label, value in fields)
    lines = [("Agent", record["opening_prompt"])]
    for turn in record["transcript"]:
        lines.extend([("Caller", turn["caller"]), ("Agent", turn["agent"])])
    transcript = "".join(f"<li><b>{speaker}</b> {escape(words)}</li>" for speaker, words in lines)
    status = escape(record["status"].replace("_", " ").capitalize())
    json_url = "/cases/" + quote(record["case_id"], safe="")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{case_id} · Dispute Desk</title><link rel="stylesheet" href="/style.css"></head>
<body><main class="review"><header><a href="/">Dispute Desk</a></header>
<div class="review-title"><h1>Dispute case</h1><p>{case_id} · {status}</p></div>
<div class="review-body"><aside aria-labelledby="payment"><h2 id="payment">Disputed payment</h2>
<dl>{summary}</dl><a href="{json_url}">View case JSON</a></aside>
<section aria-labelledby="transcript"><h2 id="transcript">Call transcript</h2><ol>{transcript}</ol></section>
</div></main></body></html>"""
