"""LLM adapter that patches PageIndex to use our LLM client (Groq/Anthropic).

PageIndex uses OpenAI's API directly via utils.py. This module monkey-patches
those functions so PageIndex uses whatever LLM provider is configured in our
platform (Groq free tier or Anthropic production).
"""

import json
import logging
import os

import openai

from app.config import settings

logger = logging.getLogger(__name__)

_patched = False


def _get_openai_client() -> openai.OpenAI:
    """Get an OpenAI-compatible client for the active LLM provider."""
    if settings.LLM_PROVIDER == "groq":
        return openai.OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    else:
        return openai.OpenAI(api_key=settings.ANTHROPIC_API_KEY)


def _get_async_openai_client() -> openai.AsyncOpenAI:
    """Get an async OpenAI-compatible client for the active LLM provider."""
    if settings.LLM_PROVIDER == "groq":
        return openai.AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    else:
        return openai.AsyncOpenAI(api_key=settings.ANTHROPIC_API_KEY)


def _get_model() -> str:
    """Get the model name for PageIndex operations."""
    if settings.LLM_PROVIDER == "groq":
        return settings.GROQ_MODEL
    return settings.CLAUDE_MODEL


def patch_pageindex_llm():
    """Monkey-patch PageIndex's utils to use our LLM provider.

    This replaces the global CHATGPT_API_KEY and the ChatGPT_API_* functions
    in PageIndex's utils module so all LLM calls go through our configured provider.
    """
    global _patched
    if _patched:
        return

    from app.services.pageindex import utils

    # Override the API key
    utils.CHATGPT_API_KEY = settings.GROQ_API_KEY if settings.LLM_PROVIDER == "groq" else settings.ANTHROPIC_API_KEY

    # Override synchronous call
    _original_sync = utils.ChatGPT_API

    def patched_sync(model, prompt, api_key=None, chat_history=None):
        client = _get_openai_client()
        effective_model = _get_model()
        messages = []
        if chat_history:
            messages = list(chat_history)
        messages.append({"role": "user", "content": prompt})
        try:
            response = client.chat.completions.create(
                model=effective_model,
                messages=messages,
                temperature=0,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("PageIndex LLM sync call failed: %s", e)
            return "Error"

    utils.ChatGPT_API = patched_sync

    # Override sync call with finish reason
    def patched_sync_with_finish(model, prompt, api_key=None, chat_history=None):
        client = _get_openai_client()
        effective_model = _get_model()
        messages = []
        if chat_history:
            messages = list(chat_history)
        messages.append({"role": "user", "content": prompt})
        try:
            response = client.chat.completions.create(
                model=effective_model,
                messages=messages,
                temperature=0,
            )
            if response.choices[0].finish_reason == "length":
                return response.choices[0].message.content, "max_output_reached"
            return response.choices[0].message.content, "finished"
        except Exception as e:
            logger.error("PageIndex LLM sync call failed: %s", e)
            return "Error", "error"

    utils.ChatGPT_API_with_finish_reason = patched_sync_with_finish

    # Override async call
    async def patched_async(model, prompt, api_key=None):
        client = _get_async_openai_client()
        effective_model = _get_model()
        messages = [{"role": "user", "content": prompt}]
        try:
            response = await client.chat.completions.create(
                model=effective_model,
                messages=messages,
                temperature=0,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("PageIndex LLM async call failed: %s", e)
            return "Error"

    utils.ChatGPT_API_async = patched_async

    _patched = True
    logger.info("PageIndex LLM adapter patched (provider=%s, model=%s)", settings.LLM_PROVIDER, _get_model())
