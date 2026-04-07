"""LLM client wrapper using litellm for multi-provider support.

Supports OpenAI, Anthropic, Azure, Ollama, and any litellm-compatible provider.
"""
import logging
from typing import AsyncIterator

import litellm

logger = logging.getLogger(__name__)


class LLMClient:
    """Multi-provider LLM client.

    Uses litellm for unified API across providers. Mirrors RAGFlow's
    chat_model.py factory pattern but simpler.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            system_prompt: System instructions (includes context)
            user_message: User's question

        Returns:
            Generated text response
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content or ""

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    async def generate_stream(
        self,
        system_prompt: str,
        user_message: str,
    ) -> AsyncIterator[str]:
        """Stream a response from the LLM.

        Yields text chunks as they arrive.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )

            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            raise
