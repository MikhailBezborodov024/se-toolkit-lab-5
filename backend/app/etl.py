"""ETL pipeline: fetch data from the autochecker API and load it into the database."""

from datetime import datetime

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings import settings


# ---------------------------------------------------------------------------
# Extract — fetch data from the autochecker API
# ---------------------------------------------------------------------------


async def fetch_items() -> list[dict]:
    """Fetch the lab/task catalog from the autochecker API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.autochecker_api_url}/api/items",
            auth=(settings.autochecker_email, settings.autochecker_password)
        )
        response.raise_for_status()
        return response.json()


async def fetch_logs(since: datetime | None = None) -> list[dict]:
    """Fetch check results from the autochecker API."""
    all_logs = []
    current_since = since
    
    async with httpx.AsyncClient() as client:
        while True:
            params = {"limit": 500}
            if current_since:
                params["since"] = current_since.isoformat()
            
            response = await client.get(
                f"{settings.autochecker_api_url}/api/logs",
                params=params,
                auth=(settings.autochecker_email, settings.autochecker_password)
            )
            response.raise_for_status()
            data = response.json()
            
            logs = data.get("logs", [])
            all_logs.extend(logs)
            
            if not data.get("has_more", False):
                break
            
            # Update since to the last log's submitted_at
            if logs:
                current_since = datetime.fromisoformat(logs[-1]["submitted_at"])
            else:
                break
    
    return all_logs


# ---------------------------------------------------------------------------
# Load — insert fetched data into the local database
# ---------------------------------------------------------------------------


async def load_items(items: list[dict], session: AsyncSession) -> int:
    """Load items (labs and tasks) into the database."""
    from app.models.item import ItemRecord
    from sqlmodel import select
    
    new_count = 0
    lab_map = {}  # lab_short_id -> ItemRecord
    
    # Process labs first
    for item in items:
        if item.get("type") == "lab":
            title = item["title"]
            
            # Check if exists
            stmt = select(ItemRecord).where(
                ItemRecord.type == "lab",
                ItemRecord.title == title
            )
            result = await session.exec(stmt)
            existing = result.first()
            
            if not existing:
                new_item = ItemRecord(type="lab", title=title)
                session.add(new_item)
                await session.flush()  # Get the ID
                new_count += 1
                existing = new_item
            
            # Map lab short ID to record
            lab_short_id = item["lab"]
            lab_map[lab_short_id] = existing
    
    # Process tasks
    for item in items:
        if item.get("type") == "task":
            title = item["title"]
            lab_short_id = item["lab"]
            parent_lab = lab_map.get(lab_short_id)
            
            if not parent_lab:
                continue
            
            # Check if exists
            stmt = select(ItemRecord).where(
                ItemRecord.type == "task",
                ItemRecord.title == title,
                ItemRecord.parent_id == parent_lab.id
            )
            result = await session.exec(stmt)
            existing = result.first()
            
            if not existing:
                new_item = ItemRecord(
                    type="task",
                    title=title,
                    parent_id=parent_lab.id
                )
                session.add(new_item)
                new_count += 1
    
    await session.commit()
    return new_count


async def load_logs(
    logs: list[dict], items_catalog: list[dict], session: AsyncSession
) -> int:
    """Load interaction logs into the database."""
    from app.models.learner import Learner
    from app.models.interaction import InteractionLog
    from app.models.item import ItemRecord
    from sqlmodel import select
    
    # Build lookup: (lab_short_id, task_short_id) -> title
    item_lookup = {}
    for item in items_catalog:
        lab_id = item["lab"]
        task_id = item.get("task")
        title = item["title"]
        item_lookup[(lab_id, task_id)] = title
    
    new_count = 0
    
    for log in logs:
        # 1. Find or create learner
        stmt = select(Learner).where(Learner.external_id == log["student_id"])
        result = await session.exec(stmt)
        learner = result.first()
        
        if not learner:
            learner = Learner(
                external_id=log["student_id"],
                student_group=log.get("group", "")
            )
            session.add(learner)
            await session.flush()
        
        # 2. Find matching item
        lab_id = log["lab"]
        task_id = log.get("task")
        item_title = item_lookup.get((lab_id, task_id))
        
        if not item_title:
            continue
        
        stmt = select(ItemRecord).where(ItemRecord.title == item_title)
        result = await session.exec(stmt)
        item = result.first()
        
        if not item:
            continue
        
        # 3. Check if interaction already exists (idempotency)
        stmt = select(InteractionLog).where(
            InteractionLog.external_id == log["id"]
        )
        result = await session.exec(stmt)
        existing = result.first()
        
        if existing:
            continue
        
        # 4. Create new interaction
        interaction = InteractionLog(
            external_id=log["id"],
            learner_id=learner.id,
            item_id=item.id,
            kind="attempt",
            score=log["score"],
            checks_passed=log["passed"],
            checks_total=log["total"],
            created_at=datetime.fromisoformat(log["submitted_at"])
        )
        session.add(interaction)
        new_count += 1
    
    await session.commit()
    return new_count


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def sync(session: AsyncSession) -> dict:
    """Run the full ETL pipeline."""
    from app.models.interaction import InteractionLog
    from sqlmodel import select, func
    
    # Step 1: Fetch and load items
    items = await fetch_items()
    await load_items(items, session)
    
    # Step 2: Determine last synced timestamp
    stmt = select(func.max(InteractionLog.created_at))
    result = await session.exec(stmt)
    last_synced = result.first()
    
    since = last_synced if last_synced else None
    
    # Step 3: Fetch and load logs
    logs = await fetch_logs(since=since)
    new_records = await load_logs(logs, items, session)
    
    # Get total records
    stmt = select(func.count(InteractionLog.id))
    result = await session.exec(stmt)
    total_records = result.first() or 0
    
    return {
        "new_records": new_records,
        "total_records": total_records
    }