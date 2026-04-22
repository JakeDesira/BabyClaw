import agents


def main() -> None:
    planning_model = "gemma4"
    reasoning_model = "gpt-oss:20b"

    memory = agents.MemoryAgent()
    executor = agents.ExecutorAgent(memory=memory)
    reviewer = agents.ReviewerAgent(model=reasoning_model)
    planner = agents.PlannerAgent(memory=memory, executor=executor, reviewer=reviewer, planning_model=planning_model, reasoning_model=reasoning_model, debug=True)
    coordinator = agents.CoordinatorAgent(planner=planner, memory=memory, model=planning_model)

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()