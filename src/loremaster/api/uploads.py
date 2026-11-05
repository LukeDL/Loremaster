"""Audio file uploads: save to disk, extract metadata, register in DB."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID, uuid4

import soundfile as sf
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.api.deps import db_session, require_csrf, require_gm
from loremaster.config import settings
from loremaster.models.repository import (
    create_audio_file,
    delete_audio_file,
    get_audio_file,
    list_audio_files,
)
from loremaster.models.scene import AudioFile

router = APIRouter(
    prefix="/api/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_gm), Depends(require_csrf)],
)

ALLOWED_EXTS = {".wav", ".flac", ".ogg", ".mp3", ".oga", ".opus", ".aiff", ".aif"}


@router.post("", response_model=AudioFile, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    file: UploadFile,
    sess: AsyncSession = Depends(db_session),
) -> AudioFile:
    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "filename required")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported extension: {ext}")

    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4()}{ext}"
    stored_path = settings.audio_dir / stored_name

    with stored_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        info = sf.info(str(stored_path))
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"could not decode: {exc}") from exc

    return await create_audio_file(
        sess,
        original_name=file.filename,
        path=stored_name,
        duration_ms=int(info.frames / info.samplerate * 1000),
        sample_rate=info.samplerate,
        channels=info.channels,
        size_bytes=stored_path.stat().st_size,
    )


@router.get("", response_model=list[AudioFile])
async def list_uploads(sess: AsyncSession = Depends(db_session)) -> list[AudioFile]:
    return await list_audio_files(sess)


@router.get("/{file_id}/download")
async def download_upload(
    file_id: UUID,
    sess: AsyncSession = Depends(db_session),
) -> FileResponse:
    """Serve the raw audio file — used by the browser waveform editor
    (wavesurfer.js) to decode and render peaks."""
    audio = await get_audio_file(sess, file_id)
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "audio file not found")
    path = settings.audio_dir / audio.path
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "audio file missing on disk")
    return FileResponse(path, filename=audio.original_name)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_upload(
    file_id: UUID,
    sess: AsyncSession = Depends(db_session),
) -> None:
    audio = await get_audio_file(sess, file_id)
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "audio file not found")
    deleted = await delete_audio_file(sess, file_id)
    if not deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "file is used by one or more scenes")
    # Remove the physical file too
    (settings.audio_dir / audio.path).unlink(missing_ok=True)
