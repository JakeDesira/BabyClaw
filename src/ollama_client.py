import os
from ollama import Client

class OllamaClient:
    def __init__(self, model: str = "gpt-oss:20b"):
        # For convenience, I also added optional support for running the client on my Mac 
        # while using the model hosted on my desktop PC through Tailscale. 
        # This was mainly for personal development and testing.
        host = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
        self.model = model
        self.client = Client(host=host)

      def ask(self, prompt: str, system_prompt: str | None = None) -> str:
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat(model=self.model, messages=messages)
        return response["message"]["content"]