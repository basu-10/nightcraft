from pathlib import Path

import requests
from flask import current_app, url_for

OPENROUTER_TTS_ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"
TTS_MODEL = "openai/gpt-4o-mini-tts-2025-12-15"


def synthesize_speech(script, api_key, segment_id):
    static_audio_dir = Path(current_app.root_path) / "static" / "audio"
    static_audio_dir.mkdir(parents=True, exist_ok=True)
    out_path = static_audio_dir / f"segment_{segment_id}.mp3"

    if api_key:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": TTS_MODEL,
            "voice": "alloy",
            "input": script,
            "format": "mp3",
        }
        try:
            response = requests.post(OPENROUTER_TTS_ENDPOINT, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            out_path.write_bytes(response.content)
        except Exception:
            out_path.write_bytes(b"")
    else:
        out_path.write_bytes(b"")

    audio_url = url_for("static", filename=f"audio/segment_{segment_id}.mp3")
    return audio_url, TTS_MODEL
