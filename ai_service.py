from config import AI_PROVIDER, AI_API_KEY, AI_BASE_URL, AI_MODEL
from database import save_message

SYSTEM_PROMPT = "تو یک دستیار هوش مصنوعی مفید و مودب هستی که به فارسی پاسخ می‌دهی."

_conversation_memory: dict[int, list[dict]] = {}
MAX_HISTORY_MESSAGES = 10


def _get_history(user_id: int) -> list[dict]:
    return _conversation_memory.setdefault(user_id, [])


def _append_history(user_id: int, role: str, content: str):
    history = _get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_MESSAGES:
        del history[: len(history) - MAX_HISTORY_MESSAGES]


def reset_history(user_id: int):
    _conversation_memory[user_id] = []


async def get_ai_response(user_id: int, user_message: str) -> str:
    _append_history(user_id, "user", user_message)
    save_message(user_id, "user", user_message)
    history = _get_history(user_id)
    if AI_PROVIDER == "anthropic":
        reply = await _call_anthropic(history)
    else:
        reply = await _call_openai_compatible(history)
    _append_history(user_id, "assistant", reply)
    save_message(user_id, "assistant", reply)
    return reply


async def _call_openai_compatible(history: list[dict]) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL or None)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    response = await client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
        max_tokens=4000,
    )
    return response.choices[0].message.content


async def _call_anthropic(history: list[dict]) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=AI_API_KEY, base_url=AI_BASE_URL or None)
    response = await client.messages.create(
        model=AI_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    return response.content[0].text