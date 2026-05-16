"""Rule engine service — CRUD for image validation rules."""
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_rule import ImageRule


async def create_rule(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    description: Optional[str],
    rules: list[dict],
) -> ImageRule:
    rule = ImageRule(
        user_id=user_id,
        name=name,
        description=description,
        rules=rules,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_rules(db: AsyncSession, user_id: uuid.UUID) -> list[ImageRule]:
    result = await db.execute(
        select(ImageRule).where(ImageRule.user_id == user_id).order_by(ImageRule.created_at)
    )
    return list(result.scalars().all())


async def get_rule(
    db: AsyncSession, rule_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[ImageRule]:
    result = await db.execute(
        select(ImageRule).where(ImageRule.id == rule_id, ImageRule.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_rule(
    db: AsyncSession,
    rule_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    rules: Optional[list[dict]] = None,
) -> Optional[ImageRule]:
    rule = await get_rule(db, rule_id, user_id)
    if not rule:
        return None
    if name is not None:
        rule.name = name
    if description is not None:
        rule.description = description
    if rules is not None:
        rule.rules = rules
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(
    db: AsyncSession, rule_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    rule = await get_rule(db, rule_id, user_id)
    if not rule:
        return False
    await db.delete(rule)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Rule application helpers (for use in image_validation_service)
# ---------------------------------------------------------------------------

def apply_rules_to_extracted(extracted: dict, rules: list[dict]) -> list[dict]:
    """Apply a rule set to an extracted data dict.

    Each rule dict:
        {
            "field": "amount",
            "operator": "lt" | "gt" | "eq" | "ne" | "contains" | "not_contains" | "present" | "absent",
            "value": <any>,        # not required for present/absent
            "type": "numeric" | "text" | "presence",
            "label": "Human-readable rule description",
        }

    Returns a list of violation dicts:
        {"rule": label, "field": field, "extracted": value, "expected": ..., "passed": bool}
    """
    results = []
    for rule in rules:
        field = rule.get("field", "")
        operator = rule.get("operator", "")
        expected = rule.get("value")
        label = rule.get("label", f"{field} {operator} {expected}")
        rule_type = rule.get("type", "text")

        extracted_value = extracted.get(field)

        try:
            passed = _evaluate_rule(extracted_value, operator, expected, rule_type)
        except Exception:
            passed = False

        results.append(
            {
                "rule": label,
                "field": field,
                "extracted": extracted_value,
                "expected": expected,
                "operator": operator,
                "passed": passed,
            }
        )
    return results


def _evaluate_rule(
    extracted_value: object,
    operator: str,
    expected: object,
    rule_type: str,
) -> bool:
    if operator == "present":
        return extracted_value is not None and str(extracted_value).strip() != ""
    if operator == "absent":
        return extracted_value is None or str(extracted_value).strip() == ""

    if extracted_value is None:
        return False

    if rule_type == "numeric":
        ev = float(str(extracted_value).replace(",", "").replace("$", "").strip())
        ex = float(expected)
        if operator == "lt":
            return ev < ex
        if operator == "lte":
            return ev <= ex
        if operator == "gt":
            return ev > ex
        if operator == "gte":
            return ev >= ex
        if operator == "eq":
            return ev == ex
        if operator == "ne":
            return ev != ex

    # Text operators
    sv = str(extracted_value).lower()
    se = str(expected).lower()
    if operator == "eq":
        return sv == se
    if operator == "ne":
        return sv != se
    if operator == "contains":
        return se in sv
    if operator == "not_contains":
        return se not in sv
    if operator == "starts_with":
        return sv.startswith(se)
    if operator == "ends_with":
        return sv.endswith(se)

    return False
