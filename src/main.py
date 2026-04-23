from pathlib import Path

from filesystem_guard import FilesystemGuard
import agents


def main() -> None:
    planning_model = "gemma4"
    reasoning_model = "gpt-oss:20b"
    debug = True

    filesystem_guard = FilesystemGuard()

    memory = agents.MemoryAgent()
    executor = agents.ExecutorAgent(memory=memory, filesystem_guard=filesystem_guard)

    response_generator = agents.ResponseGenerator(memory=memory, reasoning_model=reasoning_model, debug=debug)
    plan_executor = agents.PlanExecutor(memory=memory, executor=executor, filesystem_guard=filesystem_guard, response_generator=response_generator, debug=debug)

    reviewer = agents.ReviewerAgent(model=reasoning_model, debug=debug)

    planner = agents.PlannerAgent(memory=memory, planning_model=planning_model, filesystem_guard=filesystem_guard, debug=debug)
    
    coordinator = agents.CoordinatorAgent(planner=planner, plan_executor=plan_executor, response_generator=response_generator, reviewer=reviewer, memory=memory, model=planning_model, debug=debug)

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break

        if prompt.lower().startswith("grant access "):
            raw_path = prompt[len("grant access "):].strip().strip("\"'")
            print(filesystem_guard.request_approval(raw_path))

            confirm = input("You: ").strip().upper()

            if confirm == "YES":
                if filesystem_guard.approve(raw_path):
                    print(f"\nBaby Claw: Access granted to {Path(raw_path).resolve()}\n")
                else:
                    print("\nBaby Claw: Could not approve that path. Make sure it exists and is a directory.\n")
            else:
                print("\nBaby Claw: Access denied.\n")

            continue

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()