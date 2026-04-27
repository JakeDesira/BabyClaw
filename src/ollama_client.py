import os
from dataclasses import dataclass
from ollama import Client
from config import OLLAMA_SUPPORTS_THINK


@dataclass
class LLMResponse:
    ok: bool
    content: str = ""
    error: str = ""


class OllamaClient:
    def __init__(self, model: str | None = None, supports_think: bool | None = None):
        self.host = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
        self.client = Client(host=self.host)

        if supports_think is None:
            self.supports_think = OLLAMA_SUPPORTS_THINK
        else:
            self.supports_think = supports_think


    def _build_request_args(self, prompt: str, system_prompt: str | None = None, temperature: float | None = None, think: str | bool | None = None) -> dict:
        messages = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        request_args = {
            "model": self.model,
            "messages": messages,
        }

        options = {}

        if temperature is not None:
            options["temperature"] = temperature

        if options:
            request_args["options"] = options

        if self.supports_think and think is not None:
            request_args["think"] = think

        return request_args


    def ask(self, prompt: str, system_prompt: str | None = None, temperature: float | None = None, think: str | bool | None = None) -> LLMResponse:
        request_args = self._build_request_args(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            think=think,
        )

        try:
            response = self.client.chat(**request_args)
            content = response["message"]["content"]

            return LLMResponse(
                ok=True,
                content=content,
            )

        except Exception as e:
            return LLMResponse(
                ok=False,
                error=f"Error communicating with Ollama: {e}",
            )