import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_store
from app.api.serializers import serialize_document
from app.models import StoredDocument

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
async def list_documents():
    documents = await StoredDocument.find_all().sort(-StoredDocument.uploaded_at).to_list()
    return [serialize_document(doc) for doc in documents]


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: PydanticObjectId, store=Depends(get_store)):
    document = await StoredDocument.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        await run_in_threadpool(store.delete_document, str(document_id))
    except Exception as exc:
        # Keep the record so the delete can be retried; never leave orphaned chunks without a record.
        logger.exception("Deleting chunks failed for document %s", document_id)
        raise HTTPException(status_code=500, detail="Could not delete the document. Please try again.") from exc
    await document.delete()
    return Response(status_code=204)
