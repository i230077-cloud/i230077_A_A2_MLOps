"""Multi-provider LLM Client implementations without third-party agent frameworks."""

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLLMClient(ABC):
    """Abstract base class for provider-agnostic LLM interaction."""

    @abstractmethod
    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Executes a single reasoning turn and returns structured action."""
        pass


def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Extracts and parses the first valid JSON block from LLM output text."""
    if not text:
        return None
    # Try direct parse
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Try markdown json block ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    # Try finding first { and matching outer }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass

    return None


class GeminiClient(BaseLLMClient):
    """Google Gemini client using official google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or arguments.")
        self.model_name = model
        from google import genai
        self.client = genai.Client(api_key=self.api_key)

    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt_parts.append(f"[{role.upper()}]:\n{content}\n")

        full_prompt = "\n".join(prompt_parts) + "\n\nRespond with a valid JSON object only."

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
            )
            raw_text = response.text or ""
            parsed = extract_json_block(raw_text)
            if parsed:
                return parsed
            return {
                "thought": "Failed to parse structured JSON from model response.",
                "action": "finish",
                "report": {"repository": "", "violations": []},
            }
        except Exception as e:
            raise RuntimeError(f"Gemini API request failed: {e}")


class OpenAIClient(BaseLLMClient):
    """OpenAI / Compatible client (works with OpenAI, Groq, OpenRouter, Ollama)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY (or GROQ_API_KEY) not found in environment.")
        self.model_name = model
        import openai
        self.client = openai.OpenAI(api_key=self.api_key, base_url=base_url)

    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": str(msg.get("content", ""))
            })

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=formatted_messages,
                temperature=0.1,
                response_format={"type": "json_object"} if "gpt" in self.model_name else None,
            )
            raw_text = response.choices[0].message.content or ""
            parsed = extract_json_block(raw_text)
            if parsed:
                return parsed
            return {
                "thought": "Failed to parse structured JSON from model response.",
                "action": "finish",
                "report": {"repository": "", "violations": []},
            }
        except Exception as e:
            raise RuntimeError(f"OpenAI API request failed: {e}")


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment.")
        self.model_name = model
        import anthropic
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        system_content = ""
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                user_messages.append({
                    "role": msg.get("role", "user"),
                    "content": str(msg.get("content", ""))
                })

        try:
            response = self.client.messages.create(
                model=self.model_name,
                system=system_content,
                messages=user_messages,
                max_tokens=4096,
                temperature=0.1,
            )
            raw_text = "".join([block.text for block in response.content if hasattr(block, "text")])
            parsed = extract_json_block(raw_text)
            if parsed:
                return parsed
            return {
                "thought": "Failed to parse structured JSON from Anthropic response.",
                "action": "finish",
                "report": {"repository": "", "violations": []},
            }
        except Exception as e:
            raise RuntimeError(f"Anthropic API request failed: {e}")


class MockClient(BaseLLMClient):
    """Deterministic offline mock client for automated testing without API costs."""

    def __init__(self, scripted_steps: Optional[List[Dict[str, Any]]] = None):
        self.turn_count = 0
        self.scripted_steps = scripted_steps or []

    def generate_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if self.turn_count < len(self.scripted_steps):
            step = self.scripted_steps[self.turn_count]
            self.turn_count += 1
            return step

        # Default fallback: inspect files, inspect workflows, then finish
        if self.turn_count == 0:
            self.turn_count += 1
            return {
                "thought": "I should first discover the repository structure using list_files.",
                "action": "call_tool",
                "tool_name": "list_files",
                "arguments": {"path": "", "max_depth": 3},
            }
        elif self.turn_count == 1:
            self.turn_count += 1
            return {
                "thought": "Checking CI workflows and dependency configurations.",
                "action": "call_tool",
                "tool_name": "inspect_ci_workflows",
                "arguments": {},
            }
        else:
            self.turn_count += 1
            return {
                "thought": "Investigation complete. Formulating report.",
                "action": "finish",
                "report": {
                    "repository": "mock-repo",
                    "violations": [],
                },
            }


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseLLMClient:
    """Factory function to instantiate the appropriate LLM provider client."""
    provider = (provider or os.environ.get("DEFAULT_LLM_PROVIDER") or "").strip().lower()

    # Auto-detect if provider not explicitly specified
    if not provider:
        if os.environ.get("GEMINI_API_KEY"):
            provider = "gemini"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("GROQ_API_KEY"):
            provider = "groq"
        else:
            provider = "gemini"  # Default fallback

    if provider == "gemini":
        model = model or os.environ.get("DEFAULT_LLM_MODEL") or "gemini-2.5-flash"
        return GeminiClient(api_key=api_key, model=model)
    elif provider == "openai":
        model = model or os.environ.get("DEFAULT_LLM_MODEL") or "gpt-4o-mini"
        return OpenAIClient(api_key=api_key, model=model)
    elif provider == "anthropic":
        model = model or os.environ.get("DEFAULT_LLM_MODEL") or "claude-3-5-sonnet-20241022"
        return AnthropicClient(api_key=api_key, model=model)
    elif provider == "groq":
        model = model or os.environ.get("DEFAULT_LLM_MODEL") or "llama-3.3-70b-versatile"
        return OpenAIClient(
            api_key=api_key or os.environ.get("GROQ_API_KEY"),
            model=model,
            base_url="https://api.groq.com/openai/v1",
        )
    elif provider in {"mock", "offline"}:
        return MockClient()
    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. Supported providers are: gemini, openai, anthropic, groq, mock."
        )
