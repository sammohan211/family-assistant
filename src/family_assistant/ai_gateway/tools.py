"""Tool registry for assistant-triggered actions (PRD Section 11.5).

Each tool is (Pydantic args schema, handler). Handlers receive validated args,
a DB session, and the authenticated user, and return a ToolResult that the
orchestrator records on the AssistantInteraction row.

Tool execution always goes through the same service-layer functions that the
HTML forms use — there are no parallel mutation paths.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.models import User
from family_assistant.exercise.services import create_exercise_entry
from family_assistant.family_member.models import FamilyMember
from family_assistant.grocery.services import (
    create_grocery_item,
    mark_grocery_item_purchased,
)
from family_assistant.lunch_plan.services import (
    PACKED_STATUSES,
    create_lunch_plan_entry,
)
from family_assistant.meal_plan.services import MEAL_TYPES, create_meal_plan_entry
from family_assistant.memory.services import (
    MEMORY_TYPES,
    SUBJECT_TYPES,
    create_memory,
    list_memories,
)


@dataclass
class ToolResult:
    outcome: Literal["success", "validation_error", "runtime_error", "not_found"]
    affected_table: str | None = None
    affected_ids: list[int] = field(default_factory=list)
    data: dict[str, Any] | None = None
    error: str | None = None


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GroceryItemArgs(_StrictModel):
    name: str
    category: str | None = None
    quantity: int | None = None
    unit: str | None = None
    notes: str | None = None


class GroceryAddItemsArgs(_StrictModel):
    items: list[GroceryItemArgs] = Field(min_length=1)


class GroceryMarkPurchasedArgs(_StrictModel):
    item_ids: list[int] = Field(min_length=1)


class MealPlanCreateEntryArgs(_StrictModel):
    date: date
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    title: str
    notes: str | None = None
    is_favorite: bool = False


class LunchItemArgs(_StrictModel):
    name: str
    notes: str | None = None


class LunchPlanCreateEntryArgs(_StrictModel):
    family_member_id: int
    date: date
    items: list[LunchItemArgs] = Field(min_length=1)
    notes: str | None = None
    packed_status: Literal["planned", "packed"] = "planned"


class ExerciseLogActivityArgs(_StrictModel):
    activity_type: str
    duration_minutes: int = Field(ge=1)
    date: date
    notes: str | None = None


class MemoryCreateArgs(_StrictModel):
    subject_type: Literal["household", "user", "family_member"]
    subject_id: int | None = None
    memory_type: Literal[
        "preference",
        "food_preference",
        "restriction",
        "routine",
        "planning_constraint",
        "frequently_used",
    ]
    content: str
    is_hard_restriction: bool = False
    tags: list[str] = Field(default_factory=list)


class MemorySearchArgs(_StrictModel):
    query: str | None = None
    subject_type: Literal["household", "user", "family_member"] | None = None
    subject_id: int | None = None
    memory_type: (
        Literal[
            "preference",
            "food_preference",
            "restriction",
            "routine",
            "planning_constraint",
            "frequently_used",
        ]
        | None
    ) = None
    limit: int = Field(default=20, ge=1, le=100)


def _handle_grocery_add_items(args: GroceryAddItemsArgs, db: DbSession, user: User) -> ToolResult:
    created: list[int] = []
    for item in args.items:
        row = create_grocery_item(
            db,
            user=user,
            name=item.name,
            category=item.category,
            quantity=item.quantity,
            unit=item.unit,
            notes=item.notes,
        )
        created.append(row.id)
    return ToolResult(outcome="success", affected_table="grocery_items", affected_ids=created)


def _handle_grocery_mark_purchased(
    args: GroceryMarkPurchasedArgs, db: DbSession, user: User
) -> ToolResult:
    updated: list[int] = []
    missing: list[int] = []
    for item_id in args.item_ids:
        row = mark_grocery_item_purchased(db, item_id=item_id, user=user)
        if row is None:
            missing.append(item_id)
        else:
            updated.append(row.id)
    if missing and not updated:
        return ToolResult(
            outcome="not_found",
            affected_table="grocery_items",
            error=f"No grocery items found with ids {missing}",
        )
    return ToolResult(
        outcome="success",
        affected_table="grocery_items",
        affected_ids=updated,
        data={"missing_ids": missing} if missing else None,
    )


def _handle_meal_plan_create_entry(
    args: MealPlanCreateEntryArgs, db: DbSession, user: User
) -> ToolResult:
    row = create_meal_plan_entry(
        db,
        user=user,
        entry_date=args.date,
        meal_type=args.meal_type,
        title=args.title,
        notes=args.notes,
        is_favorite=args.is_favorite,
    )
    return ToolResult(outcome="success", affected_table="meal_plan_entries", affected_ids=[row.id])


def _handle_lunch_plan_create_entry(
    args: LunchPlanCreateEntryArgs, db: DbSession, user: User
) -> ToolResult:
    if db.get(FamilyMember, args.family_member_id) is None:
        return ToolResult(
            outcome="not_found",
            affected_table="family_members",
            error=f"FamilyMember {args.family_member_id} does not exist",
        )
    row = create_lunch_plan_entry(
        db,
        user=user,
        family_member_id=args.family_member_id,
        entry_date=args.date,
        items=[item.model_dump(exclude_none=True) for item in args.items],
        notes=args.notes,
        packed_status=args.packed_status,
    )
    return ToolResult(outcome="success", affected_table="lunch_plan_entries", affected_ids=[row.id])


def _handle_exercise_log_activity(
    args: ExerciseLogActivityArgs, db: DbSession, user: User
) -> ToolResult:
    row = create_exercise_entry(
        db,
        user=user,
        activity_type=args.activity_type,
        duration_minutes=args.duration_minutes,
        entry_date=args.date,
        notes=args.notes,
    )
    return ToolResult(outcome="success", affected_table="exercise_entries", affected_ids=[row.id])


def _handle_memory_create(args: MemoryCreateArgs, db: DbSession, user: User) -> ToolResult:
    row = create_memory(
        db,
        user=user,
        subject_type=args.subject_type,
        subject_id=args.subject_id,
        memory_type=args.memory_type,
        content=args.content,
        is_hard_restriction=args.is_hard_restriction,
        tags=args.tags,
        source="assistant",
    )
    return ToolResult(outcome="success", affected_table="memories", affected_ids=[row.id])


def _handle_memory_search(args: MemorySearchArgs, db: DbSession, user: User) -> ToolResult:
    rows = list_memories(
        db,
        subject_type=args.subject_type,
        subject_id=args.subject_id,
        memory_type=args.memory_type,
        query=args.query,
        limit=args.limit,
    )
    return ToolResult(
        outcome="success",
        affected_table="memories",
        affected_ids=[],
        data={
            "matches": [
                {
                    "id": m.id,
                    "subject_type": m.subject_type,
                    "subject_id": m.subject_id,
                    "memory_type": m.memory_type,
                    "content": m.content,
                    "is_hard_restriction": m.is_hard_restriction,
                    "tags": list(m.tags),
                }
                for m in rows
            ]
        },
    )


Handler = Callable[[Any, DbSession, User], ToolResult]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    args_model: type[BaseModel]
    handler: Handler
    description: str


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            name="grocery.add_items",
            args_model=GroceryAddItemsArgs,
            handler=_handle_grocery_add_items,
            description="Add one or more items to the grocery list.",
        ),
        ToolSpec(
            name="grocery.mark_purchased",
            args_model=GroceryMarkPurchasedArgs,
            handler=_handle_grocery_mark_purchased,
            description=(
                "Mark one or more grocery items as purchased. "
                "Use the item_id from the open grocery list in context."
            ),
        ),
        ToolSpec(
            name="meal_plan.create_entry",
            args_model=MealPlanCreateEntryArgs,
            handler=_handle_meal_plan_create_entry,
            description="Create one meal plan entry for a date and meal_type.",
        ),
        ToolSpec(
            name="lunch_plan.create_entry",
            args_model=LunchPlanCreateEntryArgs,
            handler=_handle_lunch_plan_create_entry,
            description=(
                "Create one school lunch entry for a family member on a date. "
                "Use the family_member_id from the family members list in context."
            ),
        ),
        ToolSpec(
            name="exercise.log_activity",
            args_model=ExerciseLogActivityArgs,
            handler=_handle_exercise_log_activity,
            description="Log an exercise activity for the current user.",
        ),
        ToolSpec(
            name="memory.create",
            args_model=MemoryCreateArgs,
            handler=_handle_memory_create,
            description=(
                "Create a household, user, or family-member memory (preference, restriction, etc.)."
            ),
        ),
        ToolSpec(
            name="memory.search",
            args_model=MemorySearchArgs,
            handler=_handle_memory_search,
            description="Search memories by keyword and/or subject and memory_type.",
        ),
    ]
}


@dataclass
class ValidatedToolCall:
    name: str
    args: BaseModel
    raw_args: dict[str, Any]


@dataclass
class ToolValidationError:
    name: str
    raw_args: dict[str, Any]
    error: str


def validate_tool_call(
    name: str, raw_args: dict[str, Any]
) -> ValidatedToolCall | ToolValidationError:
    spec = TOOLS.get(name)
    if spec is None:
        return ToolValidationError(name=name, raw_args=raw_args, error=f"Unknown tool: {name}")
    try:
        args = spec.args_model.model_validate(raw_args)
    except ValidationError as exc:
        return ToolValidationError(name=name, raw_args=raw_args, error=str(exc))
    return ValidatedToolCall(name=name, args=args, raw_args=raw_args)


def execute_tool_call(call: ValidatedToolCall, db: DbSession, user: User) -> ToolResult:
    spec = TOOLS[call.name]
    try:
        return spec.handler(call.args, db, user)
    except Exception as exc:
        return ToolResult(outcome="runtime_error", error=f"{type(exc).__name__}: {exc}")


def tool_catalog() -> list[dict[str, Any]]:
    """Render the tool catalog for inclusion in the LLM prompt."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "args_schema": spec.args_model.model_json_schema(),
        }
        for spec in TOOLS.values()
    ]


__all__ = [
    "MEAL_TYPES",
    "MEMORY_TYPES",
    "PACKED_STATUSES",
    "SUBJECT_TYPES",
    "TOOLS",
    "ToolResult",
    "ToolSpec",
    "ToolValidationError",
    "ValidatedToolCall",
    "execute_tool_call",
    "tool_catalog",
    "validate_tool_call",
]
