import re

from ollama_client import OllamaClient
import prompts


class ResponseGenerator:
    def __init__(self, memory=None, reasoning_model: str | None = None, reasoning_settings=None, debug: bool = True):
        self.memory = memory
        self.reasoning_settings = reasoning_settings
        self.debug = debug
        self.reasoning_client = OllamaClient(model=reasoning_model, supports_think=True)


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[RESPONSE GENERATOR DEBUG] {label}: {value}")


    def _get_context(self) -> str:
        if self.memory is None:
            return ""

        try:
            return self.memory.get_short_term_context()
        except AttributeError:
            return ""


    def _ask_reasoning_model(self, prompt: str, system_prompt: str, temperature: float, debug_label: str, think: str | None = None) -> str:
        if think is None:
            think = self.reasoning_settings.response_think if self.reasoning_settings else "medium"

        result = self.reasoning_client.ask(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            think=think,
        )

        if not result.ok:
            self._debug(f"{debug_label} ERROR", result.error)
            return result.error

        self._debug(debug_label, result.content)
        return result.content


    def _clean_file_output(self, content: str) -> str:
        """
        Clean common LLM formatting mistakes before writing generated content to files.
        """
        cleaned = content.strip()

        if not cleaned:
            return ""

        cleaned = re.sub(
            r"^```[a-zA-Z0-9_+-]*\s*",
            "",
            cleaned,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

        bad_prefixes = [
            "Here is the updated file:",
            "Here is the complete file:",
            "Here is the file:",
            "Sure, here is the updated file:",
            "Sure, here is the complete file:",
            "Sure, here is the file:",
        ]

        for prefix in bad_prefixes:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].lstrip()

        return cleaned


    def transform_content(self, prompt: str, source_text: str, transformation: str) -> str:
        user_prompt = (
            f"Original user request:\n{prompt}\n\n"
            f"Transformation type:\n{transformation}\n\n"
            f"Source text:\n{source_text}"
        )

        return self._ask_reasoning_model(
            prompt=user_prompt,
            system_prompt=prompts.response_transformation_prompt,
            temperature=0,
            debug_label="TRANSFORM RESULT",
        )


    def build_source_text(self, plan: dict, context: str, execution_result: str) -> str:
        target_source = plan.get("target_source", "NONE")

        if target_source == "MEMORY":
            return context

        if target_source == "EXECUTOR":
            return execution_result

        if target_source == "BOTH":
            parts = []

            if context:
                parts.append(context)

            if execution_result:
                parts.append(execution_result)

            return "\n\n".join(parts)

        return ""


    def generate_final_response(self, prompt: str, context: str = "", execution_result: str = "") -> str:
        """
        Generate a final user-facing response from gathered memory/tool results.
        """
        user_prompt = (
            f"Original user request:\n{prompt}\n\n"
            f"Retrieved memory context:\n{context if context else 'None'}\n\n"
            f"Execution result:\n{execution_result if execution_result else 'None'}"
        )

        return self._ask_reasoning_model(
            prompt=user_prompt,
            system_prompt=prompts.final_response_prompt,
            temperature=0.2,
            debug_label="FINAL RESPONSE",
        )


    def generate_file_content(self, prompt: str, execution_context: str = "") -> str:
        context = self._get_context()
        last_file_name = self.memory.get_last_active_file_name() if self.memory else ""
        last_file_content = self.memory.get_last_active_file_content() if self.memory else ""

        user_prompt = (
            f"Recent conversation context:\n{context}\n\n"
            f"Previous execution results:\n{execution_context if execution_context else 'None'}\n\n"
            f"Recently active file: {last_file_name}\n"
            f"Its content:\n{last_file_content[:2000] if last_file_content else 'None'}\n\n"
            f"User request:\n{prompt}"
        )

        generated = self._ask_reasoning_model(
            prompt=user_prompt,
            system_prompt=prompts.file_generation_prompt,
            temperature=0.3,
            debug_label="GENERATED FILE CONTENT",
        )

        return self._clean_file_output(generated)


    def improve_file_content(self, prompt: str, existing_content: str, instruction: str) -> str:
        user_prompt = (
            f"User request:\n{prompt}\n\n"
            f"Edit instruction for this file only:\n{instruction or prompt}\n\n"
            "Important:\n"
            "- You are editing ONE file only.\n"
            "- Do not include content from other files.\n"
            "- Do not include multiple file versions.\n"
            "- Do not repeat the existing file after the improved version.\n"
            "- Return exactly one complete final file.\n\n"
            f"Existing file content:\n{existing_content}"
        )

        improved = self._ask_reasoning_model(
            prompt=user_prompt,
            system_prompt=prompts.file_improvement_prompt,
            temperature=0,
            debug_label="IMPROVED FILE CONTENT",
        )

        return self._clean_file_output(improved)