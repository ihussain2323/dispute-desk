"""Replay a synthetic spoken call through the same HTTP endpoints as the browser."""
import argparse
import io
import json
from pathlib import Path
import urllib.request
import wave

ROOT = Path(__file__).resolve().parent


def request(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=100) as response:
        return response.read()


def speak_turn(base, call, n, audio):
    return json.loads(request(f"{base}/calls/{call['call_id']}/turns", audio, {
        "Content-Type":"audio/wav","X-Sequence":str(call["seq"]),"Idempotency-Key":f"fixture-{n}"}))


def join_audio(clips, path):
    with wave.open(str(path),"wb") as out:
        out.setparams((1,2,16000,0,"NONE","PCM"))
        for clip in clips:
            with wave.open(io.BytesIO(clip),"rb") as source:
                if (source.getnchannels(),source.getsampwidth(),source.getframerate()) != (1,2,16000):
                    raise ValueError("Expected 16 kHz PCM at playback")
                out.writeframes(source.readframes(source.getnframes()))
            out.writeframes(bytes(9600))


def run(base, output, correct_reason=False):
    call = json.loads(request(base+"/calls", b""))
    def prompt(state):
        return request(f"{base}/calls/{state['call_id']}/speech/{state['seq']}")
    clips = [prompt(call)]
    turns = [("turn-1", "reason"), ("turn-2", "confirm")]
    expected_reason = "duplicate charge"
    if correct_reason:
        turns.extend([("change-reason", "reason"), ("never-arrived", "confirm")])
        expected_reason = "goods not received"
    turns.append(("turn-3", "opened"))
    for n, (fixture, stage) in enumerate(turns, 1):
        audio = (ROOT / "fixtures" / f"{fixture}.wav").read_bytes()
        previous = call
        call = speak_turn(base, previous,n,audio)
        if call["stage"] != stage:
            raise RuntimeError(f"Turn {n} heard {call['heard']!r} and reached {call['stage']!r}, expected {stage!r}")
        clips.extend((audio,prompt(call)))
    repeated = speak_turn(base, previous,len(turns),audio)
    if repeated != call:
        raise RuntimeError("Confirmation retry did not return the original case")
    case = json.loads(request(f"{base}/cases/{call['case_id']}"))
    if (case["reason"],case["transaction"]["id"],case["transaction"]["cents"],len(case["transcript"])) != (
            expected_reason,"T103",675,len(turns)):
        raise RuntimeError("Case does not match spoken dispute")
    output.mkdir(parents=True, exist_ok=True)
    (output/"case.json").write_text(json.dumps(case,indent=2)+"\n")
    join_audio(clips,output/"call.wav")
    return case


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",default="http://127.0.0.1:8765")
    parser.add_argument("--out",type=Path,default=ROOT/"run")
    parser.add_argument("--correct-reason", action="store_true", help="Change the reason during readback")
    args=parser.parse_args()
    result=run(args.url.rstrip("/"),args.out,args.correct_reason)
    print(f"{result['case_id']} · {result['reason']} · {result['status']}")
