from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.deps import get_store
from app.ingestion.loaders import DocumentLoadError
from app.ingestion.pipeline import IngestionError, ingest_document

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", status_code=201)
async def upload(file: UploadFile, store=Depends(get_store)):
    content = await file.read()
    try:
        document = await ingest_document(file.filename or "", content, store)
    except DocumentLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "id": str(document.id),
        "filename": document.filename,
        "file_type": document.file_type,
        "page_count": document.page_count,
        "chunk_count": document.chunk_count,
    }
