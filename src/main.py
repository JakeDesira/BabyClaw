from agents.coordinator import CoordinatorAgent
from agents.planner import PlannerAgent
from agents.memory import MemoryAgent
from agents.executor import ExecutorAgent
from agents.reviewer import ReviewerAgent


def main() -> None:
    memory = MemoryAgent()
    executor = ExecutorAgent(memory=memory)
    reviewer = ReviewerAgent()
    planner = PlannerAgent(memory=memory, executor=executor, reviewer=reviewer)
    coordinator = CoordinatorAgent(planner=planner, memory=memory)

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()