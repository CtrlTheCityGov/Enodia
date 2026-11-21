"""Neural Greek & English TTS endpoint: POST /api/tts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import tts

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2500)
    lang: str | None = None
    voice: str | None = None


@router.post("/api/tts")
async def synthesize_endpoint(body: TTSRequest) -> Response:
    """Return natural Greek (el-GR-AthinaNeural) or English neural MP3 audio for AI responses."""
    try:
        result = await tts.synthesize_speech(body.text, lang=body.lang, voice=body.voice)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except tts.TTSUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc

    return Response(
        content=result.audio,
        media_type=result.media_type,
        headers={
            "X-TTS-Provider": result.provider,
            "X-TTS-Voice": result.voice,
            "X-TTS-Lang": result.locale,
            "Cache-Control": "no-store",
        },
    )
