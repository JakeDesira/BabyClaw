from ollama_client import OllamaClient
import prompts

class CoordinatorAgent:
    def __init__(self, planner=None, plan_executor=None, response_generator=None, reviewer=None, memory=None, model: str | None = None, debug: bool = True):
        """
        Entry point of the Baby Claw architecture.

        The Coordinator decides whether a request is simple enough to answer
        directly or whether it should be delegated into the planning pipeline.
        """
        self.client = OllamaClient(model=model)
        self.planner = planner
        self.plan_executor = plan_executor
        self.response_generator = response_generator
        self.reviewer = reviewer
        self.memory = memory
        self.debug = debug


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[COORDINATOR DEBUG] {label}: {value}")


    def _get_short_term_context(self) -> str:
        """
        Retrieve short-term memory context if a Memory Agent is available.
        """
        if self.memory is None:
            return ""

        try:
            return self.memory.get_short_term_context()
        except AttributeError:
            return ""
        

    def _looks_like_debug_fragment(self, prompt: str) -> bool:
        lower_prompt = prompt.lower().strip()

        debug_markers = [
            "traceback",
            'file "',
            "line ",
            "typeerror",
            "valueerror",
            "syntaxerror",
            "nameerror",
            "attributeerror",
            "keyboardinterrupt",
            "indexerror",
            "keyerror",
            "modulenotfounderror",
            "importerror",
            "draw_borders(",
            "main(stdscr)",
            "for x in range(",
            "for y in range(",
        ]

        if any(marker in lower_prompt for marker in debug_markers):
            return True

        if lower_prompt.startswith("file \"") or lower_prompt.startswith("traceback"):
            return True

        return False
    

    def _is_short_follow_up(self, prompt: str) -> bool:
        lower_prompt = prompt.lower().strip()

        short_follow_ups = {
            "yes",
            "yeah",
            "yep",
            "ok",
            "okay",
            "good",
            "do it",
            "fix it",
            "go on",
            "continue",
        }

        return lower_prompt in short_follow_ups


    def is_simple_question(self, prompt: str) -> bool:
        """
        Use the model to classify whether the user request is a simple question
        or a more complex task that needs planning.
        """
        short_term_context = self._get_short_term_context()

        classifier_user_prompt = (
            f"Recent context:\n{short_term_context}\n\n"
            f"User request:\n{prompt}"
        )

        result = self.client.ask(
            prompt=classifier_user_prompt,
            system_prompt=prompts.check_simple_question_prompt,
            temperature=0.1
        ).strip().upper()

        return result.startswith("SIMPLE")


    def handle(self, prompt: str) -> str:
        if self.memory is not None:
            try:
                self.memory.save_short_term(role="user", content=prompt)
            except AttributeError:
                pass

        self._debug("ORIGINAL PROMPT", prompt)

        if self._looks_like_debug_fragment(prompt):
            is_simple = False
        elif len(prompt) > 500:
            is_simple = False
        elif self._is_short_follow_up(prompt) and self._get_short_term_context():
            is_simple = False
        else:
            try:
                is_simple = self.is_simple_question(prompt)
            except Exception as e:
                self._debug("CLASSIFIER ERROR", e)
                is_simple = False

        if is_simple:
            short_term_context = self._get_short_term_context()

            simple_user_prompt = (
                f"Recent context:\n{short_term_context}\n\n"
                f"User request:\n{prompt}"
            )

            try:
                response = self.client.ask(
                    prompt=simple_user_prompt,
                    system_prompt=prompts.simple_response_prompt,
                    temperature=0.2
                )
            except Exception as e:
                response = f"I hit an internal routing error: {e}"

            if self.memory is not None:
                try:
                    self.memory.save_short_term(role="assistant", content=response)
                except AttributeError:
                    pass

            return response

        if self.planner is None or self.plan_executor is None or self.response_generator is None:
            response = (
                "This task appears to require planning, but the planning pipeline has not been connected correctly yet."
            )

            if self.memory is not None:
                try:
                    self.memory.save_short_term(role="assistant", content=response)
                except AttributeError:
                    pass

            return response

        current_prompt = prompt
        max_iterations = 3
        last_result = ""

        for iteration in range(max_iterations):
            self._debug("ITERATION", iteration + 1)
            self._debug("CURRENT PROMPT", current_prompt)

            plan = self.planner.create_plan(current_prompt)
            self._debug("PLAN", plan)

            execution_data = self.plan_executor.execute_plan_once(prompt, plan)
            self._debug("EXECUTION DATA", execution_data)

            context = execution_data.get("context", "")
            execution_result = execution_data.get("execution_result", "")
            source_text = execution_data.get("source_text", "")
            error = execution_data.get("error", "")

            if error:
                last_result = error
                break

            response_mode = plan.get("response_mode", "RAW")
            transformation = plan.get("transformation", "NONE")

            if response_mode == "RAW":
                draft_result = source_text or execution_result or context or "I could not retrieve the requested content."

            elif response_mode == "TRANSFORM":
                if not source_text:
                    if plan.get("memory_action") == "get_previous_active_file_content":
                        draft_result = "There is no other file in memory yet. Try reading a second file first."
                    else:
                        draft_result = "I could not retrieve the content needed for transformation."
                else:
                    draft_result = self.response_generator.transform_content(
                        prompt,
                        source_text,
                        transformation
                    )

            elif response_mode == "ANSWER":
                draft_result = self.response_generator.generate_final_response(
                    prompt=prompt,
                    context=context,
                    execution_result=execution_result
                )

            elif response_mode == "EXECUTE":
                if not source_text:
                    draft_result = "I could not retrieve the content needed to execute the instructions."
                else:
                    draft_result = self.response_generator.transform_content(
                        prompt,
                        source_text,
                        "EXECUTE_INSTRUCTIONS"
                    )

            else:
                draft_result = execution_result or context or "I understood the request, but I could not complete it reliably yet."

            last_result = draft_result
            self._debug("DRAFT RESULT", draft_result)

            if self.reviewer is None or not plan.get("needs_review", False):
                break

            review = self.reviewer.review(prompt, draft_result)
            self._debug("REVIEW RESULT", review)

            if review.get("approved", False):
                break

            current_prompt = (
                f"Original user request:\n{prompt}\n\n"
                f"Reviewer feedback on previous attempt:\n{review.get('feedback', '')}\n\n"
                "Please complete the remaining work."
            )

        response = last_result

        if self.memory is not None:
            try:
                self.memory.save_short_term(role="assistant", content=response)
            except AttributeError:
                pass

        return response