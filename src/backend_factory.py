from pathlib import Path

from filesystem_guard import FilesystemGuard
from reasoning_settings import ReasoningSettings
from paths import MEMORY_DB_PATH
from config import DEFAULT_PLANNING_MODEL, DEFAULT_REASONING_MODEL, BABYCLAW_DEBUG
import agents


def build_backend(
    reasoning_settings: ReasoningSettings | None = None,
    planning_model: str | None = None,
    reasoning_model: str | None = None,
    debug: bool | None = None,
    snapshot_root: str | Path | None = None,
) -> dict:
    """Build the shared BabyClaw backend object graph."""
    reasoning_settings = reasoning_settings or ReasoningSettings(mode="medium")
    planning_model = planning_model or DEFAULT_PLANNING_MODEL
    reasoning_model = reasoning_model or DEFAULT_REASONING_MODEL
    debug = BABYCLAW_DEBUG if debug is None else debug
    snapshot_root = (
        Path(snapshot_root).expanduser()
        if snapshot_root is not None
        else Path.home() / ".babyclaw_snapshots"
    )

    filesystem_guard = FilesystemGuard()

    transaction_manager = agents.TransactionManager(
        filesystem_guard=filesystem_guard,
        snapshot_root=snapshot_root,
    )

    execution_verifier = agents.ExecutionVerifier(
        filesystem_guard=filesystem_guard,
        debug=debug,
    )

    memory_store = agents.SQLiteMemoryStore(MEMORY_DB_PATH)
    memory = agents.MemoryAgent(memory_store=memory_store)

    for saved_path in memory.get_saved_accessible_path_values():
        filesystem_guard.approve(saved_path)

    saved_active_path = memory.get_active_accessible_path()

    if saved_active_path:
        filesystem_guard.set_active_directory(saved_active_path)

    executor = agents.ExecutorAgent(
        memory=memory,
        filesystem_guard=filesystem_guard,
        debug=debug,
    )

    response_generator = agents.ResponseGenerator(
        memory=memory,
        reasoning_model=reasoning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    plan_executor = agents.PlanExecutor(
        memory=memory,
        executor=executor,
        filesystem_guard=filesystem_guard,
        response_generator=response_generator,
        execution_verifier=execution_verifier,
        transaction_manager=transaction_manager,
        debug=debug,
    )

    reviewer = agents.ReviewerAgent(
        model=reasoning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    planner = agents.PlannerAgent(
        memory=memory,
        planning_model=planning_model,
        filesystem_guard=filesystem_guard,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    memory_writer = agents.MemoryWriter(
        model=planning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    memory_router = agents.MemoryRouter(
        model=planning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    coordinator = agents.CoordinatorAgent(
        planner=planner,
        plan_executor=plan_executor,
        response_generator=response_generator,
        reviewer=reviewer,
        memory=memory,
        model=planning_model,
        memory_router=memory_router,
        memory_writer=memory_writer,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    return {
        "reasoning_settings": reasoning_settings,
        "filesystem_guard": filesystem_guard,
        "transaction_manager": transaction_manager,
        "execution_verifier": execution_verifier,
        "memory_store": memory_store,
        "memory": memory,
        "memory_writer": memory_writer,
        "memory_router": memory_router,
        "executor": executor,
        "response_generator": response_generator,
        "plan_executor": plan_executor,
        "reviewer": reviewer,
        "planner": planner,
        "coordinator": coordinator,
    }
