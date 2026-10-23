import asyncio
import edge_tts
import os
import tempfile

DEFAULT_VOICE = "en-US-AnaNeural"
DEFAULT_PITCH = "+14Hz"

async def text_to_speech(text: str, voice: str = DEFAULT_VOICE, pitch: str = DEFAULT_PITCH) -> str:
    """Synthesizes text into an audio file (mp3/ogg) and returns the file path."""
    clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
    if not clean_text:
        clean_text = "I am ready."

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp_path = tmp.name
    tmp.close()

    communicate = edge_tts.Communicate(clean_text, voice=voice, pitch=pitch)
    await communicate.save(tmp_path)
    return tmp_path

def synthesize_sync(text: str, voice: str = DEFAULT_VOICE, pitch: str = DEFAULT_PITCH) -> str:
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, text_to_speech(text, voice, pitch)).result()
        else:
            return asyncio.run(text_to_speech(text, voice, pitch))
    except Exception:
        return asyncio.run(text_to_speech(text, voice, pitch))
