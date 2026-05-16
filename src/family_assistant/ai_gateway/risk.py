"""Confirmation policy classifier (PRD Section 11.6).

Pure function: given a list of validated tool calls, return the highest
applicable risk tier. The MVP tool set only does creates, marks, and reads —
update/delete tools land later. Threshold for "bulk" is more than 3.
"""

from typing import Literal

from family_assistant.ai_gateway.tools import (
    GroceryAddItemsArgs,
    GroceryMarkPurchasedArgs,
    LunchPlanCreateEntryArgs,
    MealPlanCreateEntryArgs,
    MemoryCreateArgs,
    ValidatedToolCall,
)

RiskTier = Literal["low", "medium", "high"]

BULK_THRESHOLD = 3


def _call_risk(call: ValidatedToolCall) -> RiskTier:
    args = call.args

    if isinstance(args, GroceryAddItemsArgs):
        return "medium" if len(args.items) > BULK_THRESHOLD else "low"

    if isinstance(args, GroceryMarkPurchasedArgs):
        return "medium" if len(args.item_ids) > BULK_THRESHOLD else "low"

    if isinstance(args, MealPlanCreateEntryArgs | LunchPlanCreateEntryArgs):
        return "low"

    if isinstance(args, MemoryCreateArgs):
        return "high" if args.is_hard_restriction else "low"

    return "low"


def classify(calls: list[ValidatedToolCall]) -> RiskTier:
    if not calls:
        return "low"
    if len(calls) > BULK_THRESHOLD:
        return "medium"
    ranking = {"low": 0, "medium": 1, "high": 2}
    return max((_call_risk(c) for c in calls), key=ranking.__getitem__)
