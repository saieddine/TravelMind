
import os
import logging

from dotenv import load_dotenv
from openai import OpenAI

# Load API settings from the .env file.
load_dotenv()

logger = logging.getLogger(__name__)


def get_llm_client() -> OpenAI | None:
    # Return no client if AI is not enabled or the key is missing.
    api_key = os.getenv("OPENROUTER_API_KEY")
    enabled = os.getenv("ENABLE_OPENROUTER", "false").lower() == "true"

    if not enabled or not api_key:
        return None

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=45.0,
    )


def ask_llm(messages: list[dict], max_tokens: int = 1200) -> str | None:
    # Send a request and safely handle API errors.
    client = get_llm_client()

    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=os.getenv(
                "OPENROUTER_MODEL",
                "nvidia/nemotron-3.5-lightning:free",
            ),
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )

        return response.choices[0].message.content

    except Exception:
        logger.exception("OpenRouter request failed.")
        return None
