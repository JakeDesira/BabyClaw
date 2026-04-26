import re

from ollama_client import OllamaClient
import prompts


class ReviewerAgent:
    def __init__(self, model: str | None = None, reasoning_settings=None, debug: bool = True):
        self.reasoning_settings = reasoning_settings
        self.client = OllamaClient(model=model, supports_think=True)
        self.debug = debug


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[REVIEWER DEBUG] {label}: {value}")

    
    def _rule_based_review(self, original_prompt: str, draft_result: str) -> dict | None:
        lower_prompt = original_prompt.lower()
        lower_result = draft_result.lower()

        failure_markers = [
            "error:",
            "access denied",
            "verification failed",
            "undo complete",
            "rollback",
            "traceback",
            "nothing to undo",
            "could not",
            "failed",
        ]

        if any(marker in lower_result for marker in failure_markers):
            return {
                "approved": False,
                "feedback": "The result contains an error or rollback message.",
            }

        filesystem_success_markers = [
            "file created:",
            "file updated:",
            "file deleted:",
            "directory created:",
            "moved:",
            "copied:",
            "renamed:",
            "verified created file:",
            "verified written file:",
            "verified deleted file:",
            "verified created directory:",
            "verified move:",
            "verified copy:",
            "verified rename:",
        ]

        filesystem_request_markers = [
            "create",
            "write",
            "edit",
            "delete",
            "move",
            "copy",
            "rename",
            "folder",
            "directory",
            "file",
        ]

        if (
            any(marker in lower_prompt for marker in filesystem_request_markers)
            and any(marker in lower_result for marker in filesystem_success_markers)
        ):
            return {
                "approved": True,
                "feedback": "The requested filesystem action appears to have completed successfully.",
            }

        return None
    

    def review(self, original_prompt: str, draft_result: str) -> dict:
        rule_based_result = self._rule_based_review(original_prompt, draft_result)

        if rule_based_result is not None:
            self._debug("RULE-BASED REVIEW", rule_based_result)
            return rule_based_result

        review_user_prompt = (
            f"Original user request:\n{original_prompt}\n\n"
            f"Draft result:\n{draft_result}"
        )

        review_response = self.client.ask(
            prompt=review_user_prompt,
            system_prompt=prompts.reviewer_prompt,
            temperature=0,
            think=self.reasoning_settings.reviewer_think if self.reasoning_settings else "low",
        )

        if not review_response.ok:
            self._debug("REVIEW ERROR", review_response.error)
            return {
                "approved": False,
                "feedback": review_response.error,
            }

        self._debug("RAW REVIEW", review_response.content)
        parsed = self._parse_review(review_response.content)
        self._debug("PARSED REVIEW", parsed)
        return parsed
    

    def _parse_review(self, raw_review: str) -> dict:
        cleaned = re.sub(r"<think>.*?</think>", "", raw_review, flags=re.DOTALL).strip()

        result = {
            "approved": False,
            "feedback": cleaned,
        }

        approved_match = re.search(
            r"(?im)^APPROVED:\s*(YES|NO)\s*$",
            cleaned,
        )

        feedback_match = re.search(
            r"(?is)^FEEDBACK:\s*(.*)$",
            cleaned,
        )

        if approved_match is not None:
            result["approved"] = approved_match.group(1).upper() == "YES"

        if feedback_match is not None:
            result["feedback"] = feedback_match.group(1).strip()

        return result