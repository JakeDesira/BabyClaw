import os
from dataclasses import dataclass
from ollama import Client

@dataclass
class LLMResponse:
    ok: bool
    content: str = ""
    error: str = ""

class OllamaClient:
    def __init__(self, model: str | None = None, supports_think: bool = False):
        """
        Wrapper for communicating with a local or remote Ollama instance.

        By default, the client connects to localhost. For convenience during
        development, the host can also be overridden through the
        OLLAMA_HOST_URL environment variable.
        """
        self.host = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "gpt-oss:20b") # Default to "gpt-oss:20b" if not set in environment variables
        self.client = Client(host=self.host)
        self.supports_think = supports_think

    def _build_request_args(self, prompt: str, system_prompt: str | None = None, temperature: float | None = None, think: str | bool | None = None) -> dict:
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        request_args = {
            "model": self.model,
            "messages": messages,
        }

        options = {}

        if temperature is not None:
            options["temperature"] = temperature

        if options:
            request_args["options"] = options

        if think is not None and self.supports_think:
            request_args["think"] = think

        return request_args


    def ask(self, prompt: str, system_prompt: str | None = None, temperature: float | None = None, think: str | bool | None = None) -> LLMResponse:
        """
        Send a prompt to the configured Ollama model and return a structured response.
        """
        request_args = self._build_request_args(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            think=think,
        )

        try:
            response = self.client.chat(**request_args)
            content = response["message"]["content"]
            return LLMResponse(ok=True, content=content)
        except Exception as e:
            return LLMResponse(ok=False, error=f"Error communicating with Ollama: {e}")