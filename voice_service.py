import asyncio
import edge_tts
import os
import tempfile

DEFAULT_VOICE = os.getenv("TTS_VOICE", "en-IN-NeerjaExpressiveNeural")
KANNADA_VOICE = os.getenv("TTS_KANNADA_VOICE", "kn-IN-SapnaNeural")
DEFAULT_PITCH = os.getenv("TTS_PITCH", "+0Hz")
DEFAULT_RATE = os.getenv("TTS_RATE", "-5%")
MAX_SPEECH_CHARACTERS = 3000

def select_voice(text: str, voice: str | None = None) -> str:
    """Prefer native Kannada for Kannada script; an explicit voice always wins.

    Keep mixed-language replies in one voice to avoid abrupt speaker changes.
    Romanized Kannada cannot reliably be distinguished from English here.
    """
    if voice:
        return voice
    if any("\u0c80" <= char <= "\u0cff" for char in text):
        return KANNADA_VOICE
    return DEFAULT_VOICE


async def text_to_speech(text: str, voice: str | None = None, pitch: str = DEFAULT_PITCH) -> str:
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
        communicate = edge_tts.Communicate(clean_text, voice=select_voice(clean_text, voice), pitch=pitch, rate=DEFAULT_RATE)
        await asyncio.wait_for(communicate.save(tmp_path), timeout=45)
        if not os.path.getsize(tmp_path):
            raise RuntimeError("Voice service returned empty audio")
        return tmp_path
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

def synthesize_sync(text: str, voice: str | None = None, pitch: str = DEFAULT_PITCH) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(text_to_speech(text, voice, pitch))
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, text_to_speech(text, voice, pitch)).result()
