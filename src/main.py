import agents


def main() -> None:
    memory = agents.MemoryAgent()
    executor = agents.ExecutorAgent(memory=memory)
    reviewer = agents.ReviewerAgent()
    planner = agents.PlannerAgent(memory=memory, executor=executor, reviewer=reviewer)
    coordinator = agents.CoordinatorAgent(planner=planner, memory=memory)

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()