from ollama_client import OllamaClient
import prompts

class CoordinatorAgent:
    def __init__(self, planner=None, plan_executor=None, response_generator=None, reviewer=None, memory=None, memory_router=None, memory_writer=None, model: str | None = None, debug: bool = True):
        """
        Entry point of the Baby Claw architecture.

        The Coordinator decides whether a request is simple enough to answer
        directly or whether it should be delegated into the planning pipeline.
        Memory retrieval is checked separately because simple requests may still
        require remembered context.
        """
        self.client = OllamaClient(model=model)
        self.planner = planner
        self.plan_executor = plan_executor
        self.response_generator = response_generator
        self.reviewer = reviewer
        self.memory = memory
        self.memory_router = memory_router
        self.memory_writer = memory_writer
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
        
    def _save_extracted_memories(self, prompt: str) -> str:
        """
        Use MemoryWriter to extract durable facts from the current prompt
        and save them through MemoryAgent.
        """
        if self.memory is None or self.memory_writer is None:
            return ""

        short_term_context = self._get_short_term_context()

        try:
            extraction = self.memory_writer.extract(
                user_prompt=prompt,
                short_term_context=short_term_context,
            )
        except Exception as e:
            self._debug("MEMORY WRITER ERROR", e)
            return ""

        self._debug("MEMORY WRITER DECISION", extraction)

        if not extraction.get("should_save", False):
            return ""

        saved_results = []

        for memory_item in extraction.get("memories", []):
            content = memory_item.get("content", "").strip()
            memory_type = memory_item.get("memory_type", "general")
            importance = memory_item.get("importance", 1)

            if not content:
                continue

            try:
                result = self.memory.save_long_term_memory_if_new(
                    content=content,
                    memory_type=memory_type,
                    source="conversation",
                    importance=importance,
                )
                saved_results.append(result)
            except Exception as e:
                saved_results.append(f"Error saving memory '{content}': {e}")

        if not saved_results:
            return ""

        return "\n".join(saved_results)
        

    def _get_relevant_long_term_memory(self, prompt: str) -> str:
        """
        Retrieve long-term memory when the memory router thinks it may help.

        This is intentionally separate from the planner.
        A request can be simple but still need memory, for example:
        - What is my name?
        """
        if self.memory is None or self.memory_router is None:
            return ""

        short_term_context = self._get_short_term_context()

        try:
            decision = self.memory_router.check(
                user_prompt=prompt,
                short_term_context=short_term_context,
            )
        except Exception as e:
            self._debug("MEMORY ROUTER ERROR", e)
            return ""

        self._debug("MEMORY ROUTER DECISION", decision)

        if not decision.get("needs_memory", False):
            return ""

        search_query = decision.get("search_query", "").strip()

        if not search_query:
            search_query = prompt

        try:
            memory_context = self.memory.search_long_term_memory(search_query)
        except AttributeError:
            return ""
        except Exception as e:
            self._debug("LONG-TERM MEMORY SEARCH ERROR", e)
            return ""

        self._debug("RETRIEVED LONG-TERM MEMORY", memory_context)

        if memory_context.strip() == "No matching long-term memories found.":
            return ""

        return memory_context
    

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
    
    def _looks_like_file_operation(self, prompt: str) -> bool:
        lower_prompt = prompt.lower()

        filesystem_action_words = [
            "create",
            "move",
            "rename",
            "delete",
            "edit",
            "append",
            "write",
            "organise",
            "organize",
            "copy",
        ]

        filesystem_object_words = [
            "file",
            "folder",
            "directory",
            "path",
        ]

        return (
            any(action in lower_prompt for action in filesystem_action_words)
            and any(obj in lower_prompt for obj in filesystem_object_words)
        )
    

    def _looks_like_direct_writing_task(self, prompt: str) -> bool:
        lower_prompt = prompt.lower()

        writing_words = [
            "write",
            "draft",
            "compose",
            "rewrite",
            "re-write",
            "generate",
        ]

        writing_objects = [
            "email",
            "message",
            "letter",
            "reply",
            "paragraph",
            "post",
        ]

        tool_or_file_words = [
            "file",
            "folder",
            "directory",
            "save",
            "send",
            "append",
            "overwrite",
            "edit the file",
            "write it to",
            "put it in",
        ]

        return (
            any(word in lower_prompt for word in writing_words)
            and any(obj in lower_prompt for obj in writing_objects)
            and not any(word in lower_prompt for word in tool_or_file_words)
        )
    

    def _looks_like_directory_listing(self, prompt: str) -> bool:
        lower_prompt = prompt.lower()

        return (
            "list" in lower_prompt
            and (
                "approved directory" in lower_prompt
                or "approved folder" in lower_prompt
                or "current directory" in lower_prompt
                or "current folder" in lower_prompt
            )
        )


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
            temperature=0.1,
        )
    
        if not result.ok:
            self._debug("CLASSIFIER LLM ERROR", result.error)
            return False
        
        return result.content.strip().upper().startswith("SIMPLE")
    

    def _save_assistant_response(self, response: str) -> None:
        """
        Avoids repeating the same memory-save block multiple times.
        """
        if self.memory is None:
            return
        try:
            self.memory.save_short_term(role="assistant", content=response)
        except AttributeError:
            pass


    def handle(self, prompt: str) -> str:
        if self.memory is not None:
            try:
                self.memory.save_short_term(role="user", content=prompt)
            except AttributeError:
                pass

        self._debug("ORIGINAL PROMPT", prompt)

        memory_save_result = self._save_extracted_memories(prompt)

        if memory_save_result:
            self._debug("MEMORY SAVE RESULT", memory_save_result)

        long_term_memory_context = self._get_relevant_long_term_memory(prompt)

        if self._looks_like_debug_fragment(prompt):
            is_simple = False
        elif self._looks_like_file_operation(prompt):
            is_simple = False
        elif self._looks_like_direct_writing_task(prompt):
            is_simple = True
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
                f"Recent conversation context:\n"
                f"{short_term_context if short_term_context else 'None'}\n\n"
                f"Retrieved long-term memory:\n"
                f"{long_term_memory_context if long_term_memory_context else 'None'}\n\n"
                f"User request:\n{prompt}"
            )

            response_result = self.client.ask(
                prompt=simple_user_prompt,
                system_prompt=prompts.simple_response_prompt,
                temperature=0.2,
            )

            if response_result.ok:
                response = response_result.content
            else:
                self._debug("SIMPLE RESPONSE LLM ERROR", response_result.error)
                response = response_result.error

            self._save_assistant_response(response)
            return response

        if self.planner is None or self.plan_executor is None or self.response_generator is None:
            response = (
                "This task appears to require planning, but the planning pipeline "
                "has not been connected correctly yet."
            )

            self._save_assistant_response(response)
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
                draft_result = (
                    source_text
                    or execution_result
                    or context
                    or "I could not retrieve the requested content."
                )

            elif response_mode == "TRANSFORM":
                if not source_text:
                    if plan.get("memory_action") == "get_previous_active_file_content":
                        draft_result = (
                            "There is no other file in memory yet. "
                            "Try reading a second file first."
                        )
                    else:
                        draft_result = (
                            "I could not retrieve the content needed for transformation."
                        )
                else:
                    draft_result = self.response_generator.transform_content(
                        prompt,
                        source_text,
                        transformation,
                    )

            elif response_mode == "ANSWER":
                combined_context_parts = []

                if long_term_memory_context:
                    combined_context_parts.append(
                        "Retrieved long-term memory:\n"
                        + long_term_memory_context
                    )

                if context:
                    combined_context_parts.append(
                        "Planner memory/tool context:\n"
                        + context
                    )

                combined_context = "\n\n".join(combined_context_parts)

                draft_result = self.response_generator.generate_final_response(
                    prompt=prompt,
                    context=combined_context,
                    execution_result=execution_result,
                )

            elif response_mode == "EXECUTE":
                if not source_text:
                    draft_result = (
                        "I could not retrieve the content needed to execute the instructions."
                    )
                else:
                    draft_result = self.response_generator.transform_content(
                        prompt,
                        source_text,
                        "EXECUTE_INSTRUCTIONS",
                    )

            else:
                draft_result = (
                    execution_result
                    or context
                    or "I understood the request, but I could not complete it reliably yet."
                )

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

        self._save_assistant_response(response)

        return response