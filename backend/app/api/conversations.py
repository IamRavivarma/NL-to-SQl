from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Response

from app.api.serializers import serialize_conversation, serialize_message
from app.models import Conversation, Message

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


async def _get_or_404(conversation_id: PydanticObjectId) -> Conversation:
    conversation = await Conversation.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("")
async def list_conversations():
    conversations = await Conversation.find_all().sort(-Conversation.updated_at).to_list()
    return [serialize_conversation(c) for c in conversations]


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: PydanticObjectId):
    conversation = await _get_or_404(conversation_id)
    messages = await Message.find(Message.conversation_id == conversation.id).sort(+Message.created_at).to_list()
    return {**serialize_conversation(conversation), "messages": [serialize_message(m) for m in messages]}


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: PydanticObjectId):
    conversation = await _get_or_404(conversation_id)
    await Message.find(Message.conversation_id == conversation.id).delete()
    await conversation.delete()
    return Response(status_code=204)
