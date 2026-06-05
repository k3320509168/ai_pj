from transformers import pipeline

MODEL_ID = "MediaTek-Research/Breeze-ASR-26"
AUDIO_PATH = "test.wav"

pipe = pipeline(
    task="automatic-speech-recognition",
    model=MODEL_ID,
    device=-1,  # CPU
)

result = pipe(AUDIO_PATH)

print(result["text"])