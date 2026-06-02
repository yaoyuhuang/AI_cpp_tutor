import json
import os
import uuid
from datetime import datetime


FILE_NAME = "conversations.json"
MAX_MESSAGES_FOR_MODEL = 20
DEFAULT_TITLE = "新对话"
DEFAULT_SCOPE = "ask"
VALID_SCOPES = {"debug", "ask", "oj", "coach", "practice", "profile"}


def normalize_scope(scope):
    return scope if scope in VALID_SCOPES else DEFAULT_SCOPE


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_json(data):
    with open(FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_conversations():
    if not os.path.exists(FILE_NAME):
        return []

    try:
        with open(FILE_NAME, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(data, list):
        return []

    changed = False
    for conversation in data:
        if not conversation.get("id"):
            conversation["id"] = uuid.uuid4().hex
            changed = True
        if not conversation.get("title"):
            conversation["title"] = DEFAULT_TITLE
            changed = True
        if not conversation.get("scope"):
            conversation["scope"] = DEFAULT_SCOPE
            changed = True
        else:
            scope = normalize_scope(conversation.get("scope"))
            if scope != conversation.get("scope"):
                conversation["scope"] = scope
                changed = True
        if "messages" not in conversation or not isinstance(conversation["messages"], list):
            conversation["messages"] = []
            changed = True
        if not conversation.get("created_at"):
            conversation["created_at"] = _now()
            changed = True
        if not conversation.get("updated_at"):
            conversation["updated_at"] = conversation["created_at"]
            changed = True

    if changed:
        _write_json(data)

    return data


def save_conversations(conversations):
    _write_json(conversations)


def summarize_conversation(conversation):
    return {
        "id": conversation["id"],
        "scope": normalize_scope(conversation.get("scope")),
        "title": conversation.get("title", DEFAULT_TITLE),
        "created_at": conversation.get("created_at", ""),
        "updated_at": conversation.get("updated_at", ""),
        "message_count": len(conversation.get("messages", [])),
    }


def list_conversation_summaries(scope=None):
    scope = normalize_scope(scope) if scope else None
    conversations = load_conversations()
    if scope:
        conversations = [item for item in conversations if normalize_scope(item.get("scope")) == scope]
    summaries = [summarize_conversation(item) for item in conversations]
    return sorted(summaries, key=lambda item: item.get("updated_at", ""), reverse=True)


def get_conversation(conversation_id):
    for conversation in load_conversations():
        if conversation.get("id") == conversation_id:
            conversation["scope"] = normalize_scope(conversation.get("scope"))
            return conversation
    return None


def find_empty_conversation(scope=DEFAULT_SCOPE):
    scope = normalize_scope(scope)
    empty_conversations = [
        conversation
        for conversation in load_conversations()
        if normalize_scope(conversation.get("scope")) == scope and not conversation.get("messages")
    ]
    if not empty_conversations:
        return None
    conversation = sorted(empty_conversations, key=lambda item: item.get("updated_at", ""), reverse=True)[0]
    conversation["scope"] = scope
    return conversation


def create_conversation(title=DEFAULT_TITLE, scope=DEFAULT_SCOPE):
    conversations = load_conversations()
    now = _now()
    conversation = {
        "id": uuid.uuid4().hex,
        "scope": normalize_scope(scope),
        "title": title or DEFAULT_TITLE,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    conversations.append(conversation)
    save_conversations(conversations)
    return conversation


def _title_from_message(content):
    content = " ".join((content or "").split())
    if not content:
        return DEFAULT_TITLE
    return content[:24] + ("..." if len(content) > 24 else "")


def append_message(conversation_id, role, content, attachments=None):
    conversations = load_conversations()
    for conversation in conversations:
        if conversation.get("id") == conversation_id:
            message = {
                "role": role,
                "content": content,
                "created_at": _now(),
            }
            if attachments:
                message["attachments"] = attachments
            conversation.setdefault("messages", []).append(message)
            if role == "user" and conversation.get("title") == DEFAULT_TITLE:
                conversation["title"] = _title_from_message(content)
            conversation["updated_at"] = _now()
            save_conversations(conversations)
            conversation["scope"] = normalize_scope(conversation.get("scope"))
            return conversation
    return None


def delete_conversation(conversation_id):
    conversations = load_conversations()
    kept = [item for item in conversations if item.get("id") != conversation_id]
    if len(kept) == len(conversations):
        return False
    save_conversations(kept)
    return True


def messages_for_model(conversation):
    messages = []
    for message in conversation.get("messages", []):
        if message.get("role") in {"user", "assistant"}:
            model_message = {
                "role": message["role"],
                "content": message.get("content", ""),
            }
            if message.get("attachments"):
                model_message["attachments"] = message.get("attachments", [])
            messages.append(model_message)
    return messages[-MAX_MESSAGES_FOR_MODEL:]
