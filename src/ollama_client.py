import os
from ollama import Client


class OllamaClient:
    def __init__(self, model: str = "gpt-oss:20b"):
        """
        Wrapper for communicating with a local or remote Ollama instance.

        By default, the client connects to localhost. For convenience during
        development, the host can also be overridden through the
        OLLAMA_HOST_URL environment variable.
        """
        self.host = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "gpt-oss:20b") # Default to "gpt-oss:20b" if not set in environment variables
        self.client = Client(host=self.host)

    def ask(self, prompt: str, system_prompt: str | None = None) -> str:
        """
        Send a prompt to the configured Ollama model and return the response text.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat(model=self.model, messages=messages)
            return response["message"]["content"]
        except Exception as e:
            return f"Error communicating with Ollama: {e}"
        
    # Asking model with images or/and files
    def ask_multi_modal(self):
        pass
