import asyncio
import edge_tts
import os
import tempfile

DEFAULT_VOICE = os.getenv("TTS_VOICE", "en-IN-PrabhatNeural")
DEFAULT_PITCH = os.getenv("TTS_PITCH", "+0Hz")
DEFAULT_RATE = os.getenv("TTS_RATE", "+0%")
MAX_SPEECH_CHARACTERS = 3000

async def text_to_speech(text: str, voice: str = DEFAULT_VOICE, pitch: str = DEFAULT_PITCH) -> str:
    """Synthesizes text into an audio file (mp3/ogg) and returns the file path."""
    clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
    if not clean_text:
        clean_text = "I am ready."
    if len(clean_text) > MAX_SPEECH_CHARACTERS:
        raise ValueError("Reply is too long for a short voice note; use text instead.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp_path = tmp.name
    tmp.close()

    try:
        communicate = edge_tts.Communicate(clean_text, voice=voice, pitch=pitch, rate=DEFAULT_RATE)
        await asyncio.wait_for(communicate.save(tmp_path), timeout=45)
        if not os.path.getsize(tmp_path):
            raise RuntimeError("Voice service returned empty audio")
        return tmp_path
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

def synthesize_sync(text: str, voice: str = DEFAULT_VOICE, pitch: str = DEFAULT_PITCH) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(text_to_speech(text, voice, pitch))
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, text_to_speech(text, voice, pitch)).result()
