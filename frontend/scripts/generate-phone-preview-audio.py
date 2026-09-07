"""Generate the public, synthetic 8-second phone mockup sample. No speech or call data."""
import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 16000
SECONDS = 8
path = Path(__file__).resolve().parents[1] / 'src/assets/phone-preview-sample.wav'
path.parent.mkdir(parents=True, exist_ok=True)
frames = bytearray()
for i in range(SAMPLE_RATE * SECONDS):
    t = i / SAMPLE_RATE
    phase = t % 2
    envelope = max(0, min(phase / 0.1, (1.4 - phase) / 0.2, 1))
    frequency = (261.63, 329.63, 392.0, 523.25)[int(t // 2)]
    value = 0.12 * envelope * math.sin(2 * math.pi * frequency * t)
    frames.extend(struct.pack('<h', round(value * 32767)))
with wave.open(str(path), 'wb') as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(SAMPLE_RATE)
    audio.writeframes(frames)
print(f'Generated synthetic sample: {SECONDS}s, {path.stat().st_size} bytes')
