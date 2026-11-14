# Dispute Desk

A voice agent that takes a disputed payment from a spoken call to a reviewable case. It listens with local Whisper, looks up a charge on a synthetic statement, asks what happened, reads back the details, and waits for explicit confirmation. The caller gets a reference. The reviewer gets the matched transaction, dispute reason, and turn-by-turn transcript in one JSON record.

**[Hear the complete demo](demo/call.wav) · [Inspect the case it created](demo/case.json)**

In the recorded call, the caller reports a duplicate charge at North Star Coffee. The agent matches transaction T103 for $6.75, reads the merchant, amount, date and reason back, and opens the case after hearing “Confirm.” Replaying that final request returns the original case ID.

## Make a call

With Docker installed, run these commands from the repository root. The first build compiles the pinned whisper.cpp release and downloads a checksum-verified English model (about 75 MiB).

```sh
docker build -t dispute-desk .
docker run --rm -p 127.0.0.1:8765:8765 -v dispute-cases:/data dispute-desk
```

Open [localhost:8765](http://localhost:8765). Start a call, allow microphone access, then use **Record reply** and **Stop and send** for each turn. Try “The charge at North Star Coffee,” then “There is a duplicate charge on my statement.” At readback, say “confirm,” “start over,” or “cancel.” Use **Open case record** for the resulting JSON. The volume preserves cases across restarts.

## Reproduce the demo without a microphone

With the server running, use Python 3.10+ in a second terminal.

```sh
python3 replay.py --out run
python3 -m unittest discover -s tests -v
```

The replay uploads three prerecorded synthetic WAVs through the browser's HTTP API. It fetches the synthesized agent prompts, checks the recognized merchant, amount, and reason, retries confirmation, and writes the actual call audio and persisted case to `run/`. Case IDs vary. The GitHub Actions workflow runs the same exercise against a fresh container.

## How intake works

The browser records mono audio and resamples each turn to 16 kHz PCM. Whisper tiny.en produces the transcript. A deterministic dialogue policy matches one merchant on the sample statement, then classifies three supported reasons: duplicate, unrecognized, or goods never received. Ambiguous or out-of-scope turns prompt a retry. Flite renders each reply locally. A single SQLite transaction records the confirmed turn and the case. Sequence numbers reject stale turns and a per-call idempotency key protects against a repeated confirmation request.

The three charges belong to one synthetic caller. This prototype runs as a local browser call. Identity verification, telephone-network routing and bank dispute submission are outside the demo. The database retains transcripts and case records. Production cardholder information should stay out of this demo.

## Native execution

Set `WHISPER_CLI` to a built [whisper.cpp v1.8.2](https://github.com/ggml-org/whisper.cpp/tree/v1.8.2) CLI, `WHISPER_MODEL` to the matching GGML tiny.en model, and `FLITE` to a [Flite](https://github.com/festvox/flite) executable with the RMS voice. Run `python3 server.py`. The server binds to loopback by default. The caller fixtures were synthesized with the SLT voice from Flite 2.2. Their source sentences are in [the fixture script](fixtures/script.json).
