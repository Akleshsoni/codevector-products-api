"""
Product Browse API — CodeVector Labs Take-Home Task
Cursor-based pagination for 200,000 products, newest first, with category filter.

Why cursor-based pagination?
- OFFSET pagination: SELECT ... OFFSET 50000 scans 50,000 rows every time -> slow
- Cursor pagination: SELECT ... WHERE created_at < :cursor -> uses index -> O(log n)
- Stable: new inserts don't shift pages, so no duplicates or skipped rows
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncpg
import os
from datetime import datetime
from typing import Optional
import base64
import json

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/products_db")


async def get_pool():
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price NUMERIC(10,2) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_products_created_at_id
                ON products (created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_products_category_created_at_id
                ON products (category, created_at DESC, id DESC);
        """)
    yield
    await pool.close()


app = FastAPI(
    title="Product Browse API",
    description="Cursor-based pagination for 200K products - fast, stable, correct",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def encode_cursor(created_at: datetime, id: str) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "id": id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    payload = json.loads(base64.urlsafe_b64decode(cursor).decode())
    return datetime.fromisoformat(payload["t"]), payload["id"]


@app.get("/")
async def root():
    return {
        "name": "Product Browse API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": ["/products", "/categories", "/health"],
        "total_products": 200000
    }



@app.get("/")
async def root():
    return {"name": "Product Browse API", "version": "1.0.0", "docs": "/docs", "endpoints": ["/products", "/categories", "/health"], "total_products": 200000}

@app.get("/products", summary="Browse products - newest first")
async def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
):
    async with pool.acquire() as conn:
        params = []
        conditions = []

        if category:
            params.append(category)
            conditions.append(f"category = ${len(params)}")

        if cursor:
            cursor_time, cursor_id = decode_cursor(cursor)
            params.append(cursor_time)
            params.append(cursor_id)
            t = len(params) - 1
            i = len(params)
            conditions.append(
                f"(created_at, id) < (${t}::timestamptz, ${i}::uuid)"
            )

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        params.append(limit + 1)
        query = f"""
            SELECT id, name, category, price, created_at, updated_at
            FROM products
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ${len(params)}
        """

        rows = await conn.fetch(query, *params)

    has_next = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_next:
        last = items[-1]
        next_cursor = encode_cursor(last["created_at"], str(last["id"]))

    return {
        "items": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "category": r["category"],
                "price": float(r["price"]),
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in items
        ],
        "next_cursor": next_cursor,
        "has_next": has_next,
        "count": len(items),
    }


@app.get("/categories", summary="List all categories")
async def list_categories():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT category FROM products ORDER BY category"
        )
    return {"categories": [r["category"] for r in rows]}


@app.get("/health")
async def health():
    return {"status": "ok"}
