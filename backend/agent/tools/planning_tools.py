"""
Planning Tools

Tools for task planning and execution management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import RunContext

from agent.deps import AuraDeps


async def plan_task(
    ctx: "RunContext[AuraDeps]",
    task_description: str,
) -> str:
    """
    Create a structured plan for a complex task.

    Use this BEFORE starting any complex task that involves:
    - Multiple file changes
    - Several sequential steps
    - Refactoring or restructuring
    - Adding new features
    - Any task you're unsure how to approach

    The planner will analyze the task and create a step-by-step plan.

    Args:
        task_description: Detailed description of what you need to accomplish

    Returns:
        The created plan in markdown format, or error message
    """
    from agent.subagents.planner import create_plan_for_task
    from agent.planning import get_plan_manager

    try:
        # Create the plan using PlannerAgent
        plan = await create_plan_for_task(
            task=task_description,
            project_path=ctx.deps.project_path,
            project_name=ctx.deps.project_name,
        )

        if not plan:
            return f"""Error: Failed to create plan.

This can happen if:
1. The project path doesn't exist or has no files
2. The task description is unclear

Project path: {ctx.deps.project_path}

Try providing more specific details about what you want to accomplish, or proceed without a formal plan by breaking down the task yourself."""

        # Store the plan in the manager
        plan_manager = ctx.deps.plan_manager or get_plan_manager()
        session_id = ctx.deps.session_id
        project_path = ctx.deps.project_path

        # Register the plan
        await plan_manager.create_plan(
            goal=plan.goal,
            original_request=task_description,
            steps=[s.to_dict() for s in plan.steps],
            session_id=session_id,
            project_path=project_path,
            context=plan.context,
            complexity=plan.complexity,
            estimated_files=plan.estimated_files,
            risks=plan.risks,
            assumptions=plan.assumptions,
        )

        # Return the plan in markdown format
        return f"""# Plan Created Successfully

{plan.to_markdown()}

---

**Next Steps:**
1. Review the plan above
2. Use `get_current_plan` to see the plan at any time
3. Use `start_plan_execution` when ready to begin
4. Use `complete_plan_step` after finishing each step
"""

    except Exception as e:
        return f"Planning error: {str(e)}"


async def get_current_plan(ctx: "RunContext[AuraDeps]") -> str:
    """
    View the current plan and its progress.

    Use this to:
    - See what steps remain
    - Check progress on the plan
    - Review the overall goal

    Returns:
        Current plan in markdown format, or message if no plan exists
    """
    from agent.planning import get_plan_manager

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan. Use `plan_task` to create one."

    return plan.to_markdown()


async def start_plan_execution(ctx: "RunContext[AuraDeps]") -> str:
    """
    Start executing the current plan.

    This marks the plan as in-progress and returns the first step to work on.

    Returns:
        First step to execute, or error if no plan exists
    """
    from agent.planning import get_plan_manager, PlanStatus

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan. Use `plan_task` to create one first."

    if plan.status not in [PlanStatus.DRAFT, PlanStatus.APPROVED]:
        return f"Plan is already {plan.status.value}. Cannot start."

    # Approve and start
    await plan_manager.approve_plan(session_id, project_path=project_path)

    # Get first step
    step = await plan_manager.start_next_step(session_id, project_path=project_path)

    if not step:
        return "No steps to execute in this plan."

    return f"""# Starting Plan Execution

**Now working on Step {step.step_number}: {step.title}**

{step.description}

Files: {', '.join(step.files) if step.files else 'None specified'}
Verification: {step.verification or 'None specified'}

---

After completing this step, use `complete_plan_step` with a summary of what you did.
If this step fails, use `fail_plan_step` with the error.
"""


async def complete_plan_step(
    ctx: "RunContext[AuraDeps]",
    summary: str,
) -> str:
    """
    Mark the current plan step as completed and move to the next.

    Call this after successfully completing a step in the plan.

    Args:
        summary: Brief summary of what was accomplished

    Returns:
        Next step to work on, or completion message
    """
    from agent.planning import get_plan_manager, PlanStatus

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan."

    current = plan.current_step
    if not current:
        return "No step currently in progress."

    # Complete the current step
    await plan_manager.complete_current_step(summary, session_id, project_path=project_path)

    # Refresh plan
    plan = await plan_manager.get_plan(session_id)

    # Check if plan is complete
    if plan.status == PlanStatus.COMPLETED:
        return f"""# Plan Completed! ✅

All {len(plan.steps)} steps have been completed.

**Summary:**
{chr(10).join(f'- Step {s.step_number}: {s.title} ✅' for s in plan.steps)}

The task "{plan.goal}" has been accomplished.
"""

    # Start next step
    next_step = await plan_manager.start_next_step(session_id, project_path=project_path)

    if not next_step:
        progress = plan.progress
        return f"""Step completed, but no more steps available.

Progress: {progress['completed']}/{progress['total']} steps completed
Remaining pending: {progress['pending']}

Check the plan with `get_current_plan` for details.
"""

    return f"""# Step Completed ✅

**Completed:** {current.title}
Summary: {summary}

---

**Now working on Step {next_step.step_number}: {next_step.title}**

{next_step.description}

Files: {', '.join(next_step.files) if next_step.files else 'None specified'}
Verification: {next_step.verification or 'None specified'}
"""


async def fail_plan_step(
    ctx: "RunContext[AuraDeps]",
    error: str,
) -> str:
    """
    Mark the current plan step as failed.

    Use this when a step cannot be completed due to an error.

    Args:
        error: Description of what went wrong

    Returns:
        Status update and options for proceeding
    """
    from agent.planning import get_plan_manager

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan."

    current = plan.current_step
    if not current:
        return "No step currently in progress."

    # Mark as failed
    await plan_manager.fail_current_step(error, session_id, project_path=project_path)

    return f"""# Step Failed ❌

**Failed:** Step {current.step_number}: {current.title}
Error: {error}

---

**Options:**
1. Try to fix the issue and retry by using `start_plan_execution` again
2. Skip this step with `skip_plan_step` and continue
3. Abandon the plan with `abandon_plan`

Use `get_current_plan` to see the full plan status.
"""


async def skip_plan_step(
    ctx: "RunContext[AuraDeps]",
    reason: str,
) -> str:
    """
    Skip the current plan step and move to the next.

    Use this when a step is not needed or should be skipped.

    Args:
        reason: Why this step is being skipped

    Returns:
        Next step to work on
    """
    from agent.planning import get_plan_manager, StepStatus

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan."

    current = plan.current_step
    if not current:
        return "No step currently in progress."

    # Mark as skipped
    await plan_manager.update_step(
        current.step_id, StepStatus.SKIPPED, reason, session_id=session_id, project_path=project_path
    )

    # Get next step
    next_step = await plan_manager.start_next_step(session_id, project_path=project_path)

    if not next_step:
        return f"Step skipped. No more steps available. Use `get_current_plan` to see status."

    return f"""# Step Skipped ⏭️

**Skipped:** {current.title}
Reason: {reason}

---

**Now working on Step {next_step.step_number}: {next_step.title}**

{next_step.description}
"""


async def abandon_plan(ctx: "RunContext[AuraDeps]") -> str:
    """
    Abandon the current plan.

    Use this to cancel the current plan and start fresh.

    Returns:
        Confirmation message
    """
    from agent.planning import get_plan_manager

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan to abandon."

    await plan_manager.cancel_plan(session_id, project_path=project_path)

    return f"""# Plan Abandoned

The plan "{plan.goal}" has been cancelled.

Progress at time of abandonment:
- Completed: {plan.progress['completed']} steps
- Failed: {plan.progress['failed']} steps
- Pending: {plan.progress['pending']} steps

You can create a new plan with `plan_task`.
"""


# =============================================================================
# Tool Registration Helper
# =============================================================================

def register_planning_tools(agent):
    """
    Register all planning tools with an agent.

    Args:
        agent: PydanticAI Agent instance
    """
    agent.tool(plan_task)
    agent.tool(get_current_plan)
    agent.tool(start_plan_execution)
    agent.tool(complete_plan_step)
    agent.tool(fail_plan_step)
    agent.tool(skip_plan_step)
    agent.tool(abandon_plan)
