from __future__ import annotations

import logging

from fastapi import APIRouter

from rag_backend.auth.dependencies import CurrentUserDep
from rag_backend.conversations import repository
from rag_backend.conversations import service as conversation_service
from rag_backend.conversations.models import ConversationRecord, MessageRecord
from rag_backend.exceptions import ConversationNotFoundError
from rag_backend.schemas.conversations import (
    ConversationDetailOut,
    ConversationOut,
    CreateConversationRequest,
    MessageOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


def _to_conversation_out(conversation: ConversationRecord) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _to_message_out(message: MessageRecord) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        standalone_question=message.standalone_question,
        cache_hit=message.cache_hit,
        payload=message.payload,
    )


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user: CurrentUserDep) -> list[ConversationOut]:
    """The caller's own conversations, most recently active first."""
    return [
        _to_conversation_out(conversation)
        for conversation in await repository.list_conversations(user.id)
    ]


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    request: CreateConversationRequest, user: CurrentUserDep
) -> ConversationOut:
    title = conversation_service.title_from_question(request.title or "")
    conversation = await repository.create_conversation(user.id, title)
    return _to_conversation_out(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(conversation_id: str, user: CurrentUserDep) -> ConversationDetailOut:
    conversation = await conversation_service.get_owned_conversation(user, conversation_id)
    messages = await repository.get_messages(conversation.id)
    return ConversationDetailOut(
        **_to_conversation_out(conversation).model_dump(),
        messages=[_to_message_out(message) for message in messages],
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, user: CurrentUserDep) -> None:
    if not await repository.delete_conversation(conversation_id, user.id):
        raise ConversationNotFoundError(f"Conversation {conversation_id} not found")
    logger.info("Conversation deleted: conversation=%s user=%s", conversation_id, user.username)
