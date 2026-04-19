import os
from ollama import Client


class OllamaClient:
    def __init__(self, model: str | None = None):
        """
        Wrapper for communicating with a local or remote Ollama instance.

        By default, the client connects to localhost. For convenience during
        development, the host can also be overridden through the
        OLLAMA_HOST_URL environment variable.
        """
        self.host = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "gpt-oss:20b") # Default to "gpt-oss:20b" if not set in environment variables
        self.client = Client(host=self.host)

    def ask(self, prompt: str, system_prompt: str | None = None, temperature: float | None = None, think: str | bool | None = None) -> str:
        """
        Send a prompt to the configured Ollama model and return the response text.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})
        
        # For creative tasks, a higher temperature can be used. 
        # For more deterministic responses, a lower temperature is better.
        options = {}
        if temperature is not None:
            options["temperature"] = temperature

        # Implemented so that if another model is used doesn't support the "think" option, it can be set to None and ignored in the request
        request_args = {
            "model": self.model,
            "messages": messages,
        }

        if options:
            request_args["options"] = options
        
        if think is not None:
            request_args["think"] = think

        try:
            response = self.client.chat(**request_args)
            return response["message"]["content"]
        except Exception as e:
            return f"Error communicating with Ollama: {e}"
        
    # Asking model with images or/and files
    def ask_multi_modal(self):
        pass
