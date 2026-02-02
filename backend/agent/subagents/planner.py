"""
Planner Subagent

Specialized agent for analyzing complex tasks and creating structured plans.
This agent is called automatically or explicitly when facing multi-step tasks.

The planner:
1. Analyzes the task requirements
2. Identifies files that need to be modified
3. Breaks down the work into discrete steps
4. Identifies dependencies between steps
5. Highlights potential risks
6. Creates a structured Plan object

Output:
The planner returns a JSON structure that can be converted to a Plan object.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, RunContext

from agent.subagents.base import (
    Subagent,
    SubagentConfig,
    SubagentResult,
    register_subagent,
)
from agent.planning import Plan, PlanStep, StepType

logger = logging.getLogger(__name__)


# =============================================================================
# Dependencies
# =============================================================================

@dataclass
class PlannerDeps:
    """Dependencies for the planner agent."""
    project_path: str
    project_name: str = ""
    existing_files: list[str] = None

    def __post_init__(self):
        if self.existing_files is None:
            self.existing_files = []
        if not self.project_name and self.project_path:
            self.project_name = Path(self.project_path).name


# =============================================================================
# Planner Agent
# =============================================================================

PLANNER_SYSTEM_PROMPT = """You are a planning assistant. Analyze tasks and create structured execution plans.

WORKFLOW:
1. Use think() to briefly analyze the task (1 call max)
2. Optionally use list_files() if you need file info (1 call max)
3. Call create_structured_plan() to output the plan

IMPORTANT: You MUST call create_structured_plan within your first 2-3 responses. Do not over-analyze.

When calling create_structured_plan, provide:
- goal: Brief summary of what to achieve
- context: Relevant background
- steps: 3-5 concrete steps, each with {title, description, type, files, depends_on, verification}
- risks: 1-2 potential issues
- assumptions: What you assumed about the project

Step types: analysis, edit, create, compile, verify
"""


@register_subagent("planner")
class PlannerAgent(Subagent[PlannerDeps]):
    """
    Planner subagent for creating structured task plans.

    This agent analyzes complex tasks and creates step-by-step plans
    that can be executed by the main agent.

    Tools:
        - think: Reason through the task
        - list_files: List project files
        - create_structured_plan: Output the final plan
    """

    def __init__(self, project_path: str = "", **kwargs):
        config = SubagentConfig(
            name="planner",
            description="Analyze complex tasks and create structured execution plans",
            max_iterations=4,  # Limited iterations
            timeout=45.0,  # 45 seconds max
            use_haiku=True,  # Use Haiku for speed
        )
        super().__init__(config)
        self._default_project_path = project_path
        self._created_plan: dict | None = None

    @property
    def system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPT

    def _create_deps(self, context: dict[str, Any]) -> PlannerDeps:
        """Create dependencies for planner agent."""
        project_path = context.get("project_path", self._default_project_path)

        # Get existing files
        existing_files = []
        if project_path:
            try:
                path = Path(project_path)
                if path.exists():
                    existing_files = [
                        str(f.relative_to(path))
                        for f in path.rglob("*")
                        if f.is_file() and not f.name.startswith(".")
                    ]
            except Exception:
                pass

        return PlannerDeps(
            project_path=project_path,
            project_name=context.get("project_name", ""),
            existing_files=existing_files[:100],  # Limit to 100 files
        )

    def get_created_plan(self) -> dict | None:
        """Get the plan created by the last run."""
        return self._created_plan

    def _create_agent(self) -> Agent[PlannerDeps, str]:
        """Create the planner agent with tools."""
        # Store reference for capturing plan
        planner_self = self

        agent = Agent(
            model=self._get_model(),
            system_prompt=self.system_prompt,
            deps_type=PlannerDeps,
            retries=1,  # Reduced retries for speed
        )

        @agent.tool
        async def think(ctx: RunContext[PlannerDeps], thought: str) -> str:
            """
            Briefly reason about the task before creating a plan.

            Use this ONCE to analyze:
            - What the task requires
            - How to break it down into steps
            - What files might be involved

            Args:
                thought: Your brief analysis

            Returns:
                Acknowledgment - now create the plan
            """
            return "Analysis noted. Now call create_structured_plan to output your plan."

        @agent.tool
        async def list_files(
            ctx: RunContext[PlannerDeps],
            directory: str = ".",
            pattern: str = "*",
        ) -> str:
            """
            List files in the project directory.

            Use this ONCE if you need to know what files exist.
            After getting file info, immediately call create_structured_plan.

            Args:
                directory: Directory relative to project root
                pattern: Glob pattern (e.g., "*.tex")

            Returns:
                List of files
            """
            project_path = ctx.deps.project_path
            if not project_path:
                if ctx.deps.existing_files:
                    return "Files: " + ", ".join(ctx.deps.existing_files[:20])
                return "No project path. Make assumptions about files."

            full_path = Path(project_path) / directory
            if not full_path.exists():
                return f"Directory not found. Make assumptions."

            try:
                if pattern == "*":
                    files = list(full_path.iterdir())
                else:
                    files = list(full_path.glob(pattern))

                items = []
                for f in sorted(files)[:20]:
                    if f.name.startswith('.'):
                        continue
                    items.append(f.name)

                return "Files: " + ", ".join(items) if items else "No matching files."
            except Exception as e:
                return f"Error listing files: {e}"

        @agent.tool
        async def create_structured_plan(
            ctx: RunContext[PlannerDeps],
            goal: str,
            context: str,
            steps: list[dict],
            risks: list[str],
            assumptions: list[str],
        ) -> str:
            """
            Create the final structured plan.

            Call this when you've analyzed the task and are ready to output the plan.

            Args:
                goal: What the plan achieves (e.g., "Add methodology section to paper")
                context: Relevant background information
                steps: List of step objects with: title, description, type, files, depends_on, verification
                risks: List of potential issues
                assumptions: List of assumptions made

            Returns:
                Confirmation that plan was created
            """
            # Validate steps
            validated_steps = []
            for i, step in enumerate(steps):
                validated_step = {
                    "title": step.get("title", f"Step {i + 1}"),
                    "description": step.get("description", ""),
                    "type": step.get("type", "other"),
                    "files": step.get("files", []),
                    "depends_on": [],  # Will convert from step numbers
                    "verification": step.get("verification", ""),
                }

                # Convert depends_on from step numbers to step_ids
                # (will be resolved later since we don't have IDs yet)
                raw_depends = step.get("depends_on", [])
                if raw_depends:
                    validated_step["depends_on_numbers"] = raw_depends

                validated_steps.append(validated_step)

            plan_data = {
                "goal": goal,
                "context": context,
                "steps": validated_steps,
                "risks": risks,
                "assumptions": assumptions,
                "complexity": min(len(validated_steps), 5),
                "estimated_files": list(set(
                    f for step in validated_steps for f in step.get("files", [])
                )),
            }

            # Store the plan for retrieval
            planner_self._created_plan = plan_data

            # Return summary
            return f"""Plan created successfully!

Goal: {goal}
Steps: {len(validated_steps)}
Files: {len(plan_data['estimated_files'])}
Risks: {len(risks)}

The plan has been saved and is ready for execution."""

        return agent

    async def run(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> SubagentResult:
        """
        Run the planner on a task.

        This override captures the created plan from the tool.
        """
        self._created_plan = None  # Reset
        result = await super().run(task, context)

        # If plan was created, include it in the output
        if self._created_plan:
            result.output = json.dumps(self._created_plan, indent=2)

        return result


# =============================================================================
# Helper Functions
# =============================================================================

async def create_plan_for_task(
    task: str,
    project_path: str,
    project_name: str = "",
) -> Plan | None:
    """
    Convenience function to create a plan for a task.

    Args:
        task: The task to plan
        project_path: Path to the project
        project_name: Name of the project

    Returns:
        Plan object if successful, None otherwise
    """
    from agent.planning import Plan, PlanStep, StepType

    planner = PlannerAgent(project_path=project_path)
    context = {
        "project_path": project_path,
        "project_name": project_name,
    }

    result = await planner.run(task, context)

    if not result.success or not planner.get_created_plan():
        logger.error(f"Planning failed: {result.error or result.output}")
        return None

    plan_data = planner.get_created_plan()

    # Convert to Plan object
    plan = Plan(
        goal=plan_data.get("goal", task),
        original_request=task,
        context=plan_data.get("context", ""),
        complexity=plan_data.get("complexity", 1),
        estimated_files=plan_data.get("estimated_files", []),
        risks=plan_data.get("risks", []),
        assumptions=plan_data.get("assumptions", []),
    )

    # Add steps
    steps_data = plan_data.get("steps", [])
    step_id_map = {}  # Map step numbers to IDs

    for i, step_data in enumerate(steps_data):
        step = PlanStep(
            step_number=i + 1,
            title=step_data.get("title", f"Step {i + 1}"),
            description=step_data.get("description", ""),
            step_type=StepType(step_data.get("type", "other")),
            files=step_data.get("files", []),
            verification=step_data.get("verification", ""),
        )
        plan.steps.append(step)
        step_id_map[i + 1] = step.step_id

    # Resolve dependencies (convert step numbers to step IDs)
    for i, step_data in enumerate(steps_data):
        depends_on_numbers = step_data.get("depends_on_numbers", [])
        for num in depends_on_numbers:
            if num in step_id_map and num != i + 1:  # Don't depend on self
                plan.steps[i].depends_on.append(step_id_map[num])

    return plan
