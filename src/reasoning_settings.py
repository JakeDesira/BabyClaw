from dataclasses import dataclass


@dataclass
class ReasoningSettings:
    mode: str = "medium"

    def __post_init__(self):
        self.mode = self.mode.lower().strip()

        if self.mode not in {"low", "medium", "high"}:
            self.mode = "medium"


    @property
    def planner_think(self) -> str:
        if self.mode == "low":
            return "low"

        if self.mode == "medium":
            return "low"

        return "medium"


    @property
    def response_think(self) -> str:
        if self.mode == "low":
            return "low"

        if self.mode == "medium":
            return "medium"

        return "high"


    @property
    def memory_think(self) -> str:
        if self.mode == "high":
            return "medium"

        return "low"


    @property
    def reviewer_think(self) -> str:
        if self.mode == "low":
            return "low"

        if self.mode == "medium":
            return "low"

        return "medium"


    @property
    def max_iterations(self) -> int:
        if self.mode == "low":
            return 1

        if self.mode == "medium":
            return 2

        return 3


    @property
    def allow_reviewer(self) -> bool:
        return self.mode in {"medium", "high"}