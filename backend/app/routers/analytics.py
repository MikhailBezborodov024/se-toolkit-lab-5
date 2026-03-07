"""Router for analytics endpoints.

Each endpoint performs SQL aggregation queries on the interaction data
populated by the ETL pipeline. All endpoints require a `lab` query
parameter to filter results by lab (e.g., "lab-01").
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import select, func, case
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models.item import ItemRecord
from app.models.learner import Learner
from app.models.interaction import InteractionLog

router = APIRouter()


@router.get("/scores")
async def get_scores(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Score distribution histogram for a given lab."""
    # Transform "lab-04" -> "Lab 04" for title matching
    lab_title_part = lab.replace("-", " ").title()
    
    # Find the lab item
    stmt = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.ilike(f"%{lab_title_part}%")
    )
    result = await session.exec(stmt)
    lab_item = result.first()
    
    if not lab_item:
        return [
            {"bucket": "0-25", "count": 0},
            {"bucket": "26-50", "count": 0},
            {"bucket": "51-75", "count": 0},
            {"bucket": "76-100", "count": 0},
        ]
    
    # Find task items that belong to this lab
    stmt = select(ItemRecord.id).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    )
    result = await session.exec(stmt)
    task_ids = [r for r in result]
    
    if not task_ids:
        return [
            {"bucket": "0-25", "count": 0},
            {"bucket": "26-50", "count": 0},
            {"bucket": "51-75", "count": 0},
            {"bucket": "76-100", "count": 0},
        ]
    
    # Build bucket CASE expression
    bucket_case = case(
        (InteractionLog.score <= 25, "0-25"),
        (InteractionLog.score <= 50, "26-50"),
        (InteractionLog.score <= 75, "51-75"),
        else_="76-100"
    )
    
    # Query: group by bucket, count interactions
    stmt = select(
        bucket_case.label("bucket"),
        func.count(InteractionLog.id).label("count")
    ).where(
        InteractionLog.item_id.in_(task_ids),
        InteractionLog.score.isnot(None)
    ).group_by(bucket_case)
    
    result = await session.exec(stmt)
    bucket_counts = {row.bucket: row.count for row in result}
    
    # Always return all four buckets
    return [
        {"bucket": "0-25", "count": bucket_counts.get("0-25", 0)},
        {"bucket": "26-50", "count": bucket_counts.get("26-50", 0)},
        {"bucket": "51-75", "count": bucket_counts.get("51-75", 0)},
        {"bucket": "76-100", "count": bucket_counts.get("76-100", 0)},
    ]


@router.get("/pass-rates")
async def get_pass_rates(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Per-task pass rates for a given lab."""
    lab_title_part = lab.replace("-", " ").title()
    
    # Find the lab item
    stmt = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.ilike(f"%{lab_title_part}%")
    )
    result = await session.exec(stmt)
    lab_item = result.first()
    
    if not lab_item:
        return []
    
    # Find task items that belong to this lab
    stmt = select(ItemRecord).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    ).order_by(ItemRecord.title)
    result = await session.exec(stmt)
    tasks = result.all()
    
    results = []
    for task in tasks:
        stmt = select(
            func.round(func.avg(InteractionLog.score), 1).label("avg_score"),
            func.count(InteractionLog.id).label("attempts")
        ).where(
            InteractionLog.item_id == task.id,
            InteractionLog.score.isnot(None)
        )
        res = await session.exec(stmt)
        row = res.first()
        if row and row.attempts > 0:
            results.append({
                "task": task.title,
                "avg_score": float(row.avg_score) if row.avg_score else 0.0,
                "attempts": row.attempts
            })
    
    return results


@router.get("/timeline")
async def get_timeline(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Submissions per day for a given lab."""
    lab_title_part = lab.replace("-", " ").title()
    
    # Find the lab item
    stmt = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.ilike(f"%{lab_title_part}%")
    )
    result = await session.exec(stmt)
    lab_item = result.first()
    
    if not lab_item:
        return []
    
    # Find task items that belong to this lab
    stmt = select(ItemRecord.id).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    )
    result = await session.exec(stmt)
    task_ids = [r for r in result]
    
    if not task_ids:
        return []
    
    # Group by date, count submissions
    # Use func.date() for SQLite/PostgreSQL compatibility
    stmt = select(
        func.date(InteractionLog.created_at).label("date"),
        func.count(InteractionLog.id).label("submissions")
    ).where(
        InteractionLog.item_id.in_(task_ids)
    ).group_by(
        func.date(InteractionLog.created_at)
    ).order_by(
        func.date(InteractionLog.created_at)
    )
    
    result = await session.exec(stmt)
    
    return [
        {"date": row.date, "submissions": row.submissions}
        for row in result
    ]


@router.get("/groups")
async def get_groups(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
):
    """Per-group performance for a given lab."""
    lab_title_part = lab.replace("-", " ").title()
    
    # Find the lab item
    stmt = select(ItemRecord).where(
        ItemRecord.type == "lab",
        ItemRecord.title.ilike(f"%{lab_title_part}%")
    )
    result = await session.exec(stmt)
    lab_item = result.first()
    
    if not lab_item:
        return []
    
    # Find task items that belong to this lab
    stmt = select(ItemRecord.id).where(
        ItemRecord.type == "task",
        ItemRecord.parent_id == lab_item.id
    )
    result = await session.exec(stmt)
    task_ids = [r for r in result]
    
    if not task_ids:
        return []
    
    # Join interactions with learners, group by student_group
    stmt = select(
        Learner.student_group.label("group"),
        func.round(func.avg(InteractionLog.score), 1).label("avg_score"),
        func.count(func.distinct(Learner.id)).label("students")
    ).join(
        Learner, InteractionLog.learner_id == Learner.id
    ).where(
        InteractionLog.item_id.in_(task_ids),
        InteractionLog.score.isnot(None)
    ).group_by(
        Learner.student_group
    ).order_by(
        Learner.student_group
    )
    
    result = await session.exec(stmt)
    
    return [
        {
            "group": row.group,
            "avg_score": float(row.avg_score) if row.avg_score else 0.0,
            "students": row.students
        }
        for row in result
    ]