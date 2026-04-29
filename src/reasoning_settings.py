from dataclasses import dataclass


@dataclass
class ReasoningSettings:
    """Runtime settings that tune model reasoning effort."""
    mode: str = "medium"

    def __post_init__(self):
        """Normalise and validate dataclass state after initialisation."""
        self.mode = self.mode.lower().strip()

        if self.mode not in {"low", "medium", "high"}:
            self.mode = "medium"


    @property
    def planner_think(self) -> str:
        """Return the reasoning effort for planner calls."""
        if self.mode == "low":
            return "low"

        if self.mode == "medium":
            return "low"

        return "medium"


    @property
    def response_think(self) -> str:
        """Return the reasoning effort for response generation."""
        if self.mode == "low":
            return "low"

        if self.mode == "medium":
            return "medium"

        return "high"


    @property
    def memory_think(self) -> str:
        """Return the reasoning effort for memory routing and writing."""
        if self.mode == "high":
            return "medium"

        return "low"


    @property
    def reviewer_think(self) -> str:
        """Return the reasoning effort for reviewer calls."""
        if self.mode == "low":
            return "low"

        if self.mode == "medium":
            return "low"

        return "medium"


    @property
    def max_iterations(self) -> int:
        """Return the maximum planning iterations for the active mode."""
        if self.mode == "low":
            return 1

        if self.mode == "medium":
            return 2

        return 3


    @property
    def allow_reviewer(self) -> bool:
        """Return whether reviewer passes are enabled."""
        return self.mode in {"medium", "high"}
