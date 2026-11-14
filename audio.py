"""Local neural speech input and output for the dispute agent."""
import io
import math
from threading import Lock
import wave

import numpy as np
from scipy.signal import resample_poly
import sherpa_onnx as sherpa


def pcm_input(data):
    with wave.open(io.BytesIO(data), "rb") as stream:
        if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Expected 16 kHz mono PCM16 WAV")
        frames = stream.getnframes()
        if not 1600 <= frames <= 480000:
            raise ValueError("Record between 0.1 and 30 seconds")
        samples = np.frombuffer(stream.readframes(frames), "<i2").astype(np.float32)
    if len(samples) != frames:
        raise ValueError("Incomplete recording")
    if np.sqrt(np.mean(samples ** 2)) < 45:
        raise ValueError("No audible speech. Please try again.")
    return samples / 32768


def wav_bytes(samples, rate):
    divisor = math.gcd(rate, 16000)
    pcm = resample_poly(samples, 16000 // divisor, rate // divisor)
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "PCM"))
        stream.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
    return output.getvalue()


class SpeechEngine:
    def __init__(self, root, speaker=5):
        if not 0 <= speaker <= 9:
            raise ValueError("AGENT_SPEAKER must be between 0 and 9")
        self.speaker = speaker
        self.asr_lock = Lock()
        self.tts_lock = Lock()
        voice = root / "sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
        asr = root / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
        self.recognizer = sherpa.OfflineRecognizer.from_transducer(
            encoder=str(asr / "encoder.int8.onnx"), decoder=str(asr / "decoder.int8.onnx"),
            joiner=str(asr / "joiner.int8.onnx"), tokens=str(asr / "tokens.txt"),
            model_type="nemo_transducer", feature_dim=128, num_threads=3)
        supertonic = sherpa.OfflineTtsSupertonicModelConfig(
            duration_predictor=str(voice / "duration_predictor.int8.onnx"),
            text_encoder=str(voice / "text_encoder.int8.onnx"),
            vector_estimator=str(voice / "vector_estimator.int8.onnx"),
            vocoder=str(voice / "vocoder.int8.onnx"), tts_json=str(voice / "tts.json"),
            unicode_indexer=str(voice / "unicode_indexer.bin"), voice_style=str(voice / "voice.bin"))
        config = sherpa.OfflineTtsConfig(model=sherpa.OfflineTtsModelConfig(supertonic=supertonic, num_threads=3))
        self.tts = sherpa.OfflineTts(config)

    def transcribe(self, data):
        samples = pcm_input(data)
        with self.asr_lock:
            stream = self.recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self.recognizer.decode_stream(stream)
            words = stream.result.text.strip()
        if not words:
            raise ValueError("No transcript. Please try again.")
        return words

    def synthesize(self, text, speaker=None):
        config = sherpa.GenerationConfig()
        config.sid = self.speaker if speaker is None else speaker
        config.num_steps = 8
        config.speed = 1.08
        config.extra = {"lang": "en"}
        with self.tts_lock:
            result = self.tts.generate(text, config)
        if not len(result.samples):
            raise RuntimeError("Speech synthesis returned an empty clip")
        return wav_bytes(result.samples, result.sample_rate)
