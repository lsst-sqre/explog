from __future__ import annotations

__all__ = ["find_messages"]

import datetime
import typing

import fastapi
import sqlalchemy as sa

from ..message import ExposureFlag, Message
from ..shared_state import SharedState, get_shared_state

router = fastapi.APIRouter()


@router.get("/messages/", response_model=typing.List[Message])
async def find_messages(
    site_ids: typing.List[str] = fastapi.Query(
        None,
        title="Site IDs.",
    ),
    obs_id: str = fastapi.Query(
        None,
        title="Observation ID (a string) contains...",
    ),
    instruments: typing.List[str] = fastapi.Query(
        None,
        title="Names of instruments (e.g. HSC)",
    ),
    min_day_obs: int = fastapi.Query(
        None,
        title="Minimum day of observation, inclusive; "
        "an integer of the form YYYYMMDD",
    ),
    max_day_obs: int = fastapi.Query(
        None,
        title="Maximum day of observation, exclusive; "
        "an integer of the form YYYYMMDD",
    ),
    message_text: str = fastapi.Query(
        None,
        title="Message text contains...",
    ),
    user_ids: typing.List[str] = fastapi.Query(
        None,
        title="User IDs",
    ),
    user_agents: typing.List[str] = fastapi.Query(
        None,
        title="User agent (which app created the message)",
    ),
    is_human: bool = fastapi.Query(
        None,
        title="Was the message created by a human being?",
    ),
    is_valid: bool = fastapi.Query(
        True,
        title="Is the message valid " "(False if deleted or superseded)?",
        default_value=True,
    ),
    exposure_flags: typing.List[ExposureFlag] = fastapi.Query(
        None,
        title="List of exposure flag values",
    ),
    min_date_added: datetime.datetime = fastapi.Query(
        None,
        title="Minimum date the exposure was added, inclusive; "
        "TAI as an ISO string with no timezone information",
    ),
    max_date_added: datetime.datetime = fastapi.Query(
        None,
        title="Maximum date the exposure was added, exclusive; "
        "TAI as an ISO string with no timezone information",
    ),
    has_date_invalidated: bool = fastapi.Query(
        None,
        title="Does this message have a non-null " "date_invalidated?",
    ),
    min_date_invalidated: datetime.datetime = fastapi.Query(
        None,
        title="Minimum date the is_valid flag was last toggled, inclusive, "
        "TAI as an ISO string with no timezone information",
    ),
    max_date_invalidated: datetime.datetime = fastapi.Query(
        None,
        title="Maximum date the is_valid flag was last toggled, exclusive, "
        "TAI as an ISO string with no timezone information",
    ),
    has_parent_id: bool = fastapi.Query(
        None,
        title="Does this message have a " "non-null parent ID?",
    ),
    order_by: typing.List[str] = fastapi.Query(
        None,
        title="Fields to sort by. "
        "Prefix a name with - for descending order, e.g. -id.",
    ),
    offset: int = fastapi.Query(
        0,
        title="The number of messages to skip.",
    ),
    limit: int = fastapi.Query(
        50, title="The maximum number of number of messages to return."
    ),
    state: SharedState = fastapi.Depends(get_shared_state),
) -> list[Message]:
    """Find messages."""
    el_table = state.exposurelog_db.table

    # Names of selection arguments
    select_arg_names = (
        "site_ids",
        "obs_id",
        "instruments",
        "min_day_obs",
        "max_day_obs",
        "message_text",
        "user_ids",
        "user_agents",
        "is_human",
        "is_valid",
        "exposure_flags",
        "min_date_added",
        "max_date_added",
        "has_date_invalidated",
        "min_date_invalidated",
        "max_date_invalidated",
        "has_parent_id",
        "order_by",
    )

    async with state.exposurelog_db.engine.acquire() as connection:
        conditions = []
        order_by_columns = []
        # Handle minimums and maximums
        for key in select_arg_names:
            value = locals()[key]
            if value is None:
                continue
            if key.startswith("min_"):
                column = getattr(el_table.c, key[4:])
                conditions.append(column >= value)
            elif key.startswith("max_"):
                column = getattr(el_table.c, key[4:])
                conditions.append(column < value)
            elif key.startswith("has_"):
                column = getattr(el_table.c, key[4:])
                if value:
                    conditions.append(column != None)  # noqa
                else:
                    conditions.append(column == None)  # noqa
            elif key in (
                "site_ids",
                "instruments",
                "user_ids",
                "user_agents",
                "exposure_flags",
            ):
                # Value is a list; field name is key without the final "s".
                column = getattr(el_table.c, key[:-1])
                conditions.append(column.in_(value))
            elif key in ("message_text", "obs_id"):
                column = getattr(el_table.c, key)
                conditions.append(column.contains(value))
            elif key in ("is_human", "is_valid"):
                column = getattr(el_table.c, key)
                conditions.append(column == value)
            elif key == "order_by":
                for item in value:
                    if item.startswith("-"):
                        column = getattr(el_table.c, item[1:])
                        order_by_columns.append(sa.sql.desc(column))
                    else:
                        column = getattr(el_table.c, item)
                        order_by_columns.append(sa.sql.asc(column))
                column = el_table.c.exposure_flag

            else:
                raise RuntimeError(f"Bug: unrecognized key: {key}")
        full_conditions = sa.sql.and_(*conditions)
        result_proxy = await connection.execute(
            el_table.select()
            .where(full_conditions)
            .order_by(*order_by_columns)
            .limit(limit)
            .offset(offset)
        )
        messages = []
        async for row in result_proxy:
            messages.append(Message(**row))

    return messages
