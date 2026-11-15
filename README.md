# Dispute Desk

A caller can dispute a payment by voice, check the readback, and open a reviewable case. The agent looks up the original transaction on a synthetic statement and asks for explicit confirmation before it writes a case.

**[Listen to the neural voice demo](demo/call.wav) · [Read the case from that call](demo/case.json)**

Two Supertonic 3 speakers perform the recorded call. The caller reports a duplicate charge at North Star Coffee. The agent reads back the date, reason, and amount of $6.75. The caller confirms, and the case becomes available for review. Repeating the confirmation request returns the same case ID.

## Make a call

Run from the repository root. The first build fetches about 616 MB of checksum-verified model archives. The resulting container performs speech recognition and synthesis locally on CPU.

```sh
docker build -t dispute-desk .
docker run --rm -p 127.0.0.1:8765:8765 -v dispute-cases:/data dispute-desk
```

Open [localhost:8765](http://localhost:8765). Start a call, allow microphone access, and use **Record reply** and **Stop and send** for each turn. Try “The charge at North Star Coffee,” then “There is a duplicate charge on my statement.” At readback, say “change the payment” to choose another merchant or “change the reason” to explain the issue again. The agent keeps the other detail, reads the updated dispute back, and waits for “confirm.” You can also say “start over” or “cancel.” Select **Open case record** to inspect the result.

For a merchant with multiple charges, try “Harbor Books.” The agent reads each amount and date. Say “option two” for the $18 charge on May 16, or “change the merchant” to look up a different payment.

## Speech and application stack

| Layer | Implementation |
| --- | --- |
| Microphone | An AudioWorklet captures the caller on the browser audio thread and supplies 16 kHz PCM to the turn endpoint. |
| Recognition | NVIDIA Parakeet TDT 0.6B v3 transcribes each completed turn. |
| Voice | Supertonic 3 speaks the agent's replies. The demo uses speaker 5 for the agent and speaker 1 for the caller. Set the container environment variable `AGENT_SPEAKER` from 0 to 9 to audition another preset. |
| Serving | FastAPI and Uvicorn serve the UI, turn API, and case records. Sherpa-ONNX keeps both models in memory across turns. Interactive API docs are available at `/docs`. |
| Case writes | A deterministic policy asks for a single merchant, a supported dispute reason, and confirmation. A SQLite transaction records the final turn and case together. Sequence numbers and idempotency keys protect retries. |

The workflow supports duplicate charges, unrecognized charges, and goods never received. This is turn-based intake for one synthetic cardholder. Live bank submission, caller identity verification, and telephone-network routing are outside the demo.

Model credits and usage terms are in the [NVIDIA Parakeet model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) and [Supertone Supertonic 3 model card](https://huggingface.co/Supertone/supertonic-3). The downloader verifies the ONNX exports distributed by [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx).

## Replay the demo

With the agent running, use Python 3.10+ in a second terminal.

```sh
python3 replay.py --out run
python3 replay.py --choose-payment --out run/selection
python3 replay.py --correct-reason --out run/correction
python3 -m unittest discover -s tests -v
```

The replay sends three neural caller recordings to the same API as the browser, retrieves the synthesized replies, verifies the persisted case and retries the confirmation. It saves the actual audio and case to `run/`. The workflow repeats this test against a fresh container on GitHub.

For native execution, use Python 3.13, install `requirements.txt` into a virtual environment, run `sh fetch-models.sh`, then `python server.py`. Set `MODEL_DIR` if the extracted models are stored elsewhere.
