from array import array
import io
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import wave


def transcribe(data, cli, model):
    with wave.open(io.BytesIO(data), "rb") as stream:
        if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (16000,1,2):
            raise ValueError("Expected 16 kHz mono PCM16 WAV")
        frames = stream.getnframes()
        if not 1600 <= frames <= 16000*30:
            raise ValueError("Record between 0.1 and 30 seconds")
        samples = array("h", stream.readframes(frames))
        if len(samples)!=frames:
            raise ValueError("Incomplete recording")
        if sys.byteorder!="little":
            samples.byteswap()
        if math.sqrt(sum(v*v for v in samples)/frames) < 45:
            raise ValueError("No audible speech. Please try again.")
    with tempfile.TemporaryDirectory() as directory:
        audio = Path(directory)/"turn.wav"
        base = Path(directory)/"words"
        audio.write_bytes(data)
        subprocess.run([cli,"-m",str(model),"-f",str(audio),"-l","en","-t","2","-otxt","-of",str(base),
                        "-nt","-ng"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=90)
        words = base.with_suffix(".txt").read_text().strip()
        if not words:
            raise ValueError("No transcript. Please try again.")
        return words
