"""
Seed script — generates 200,000 products fast.

Approach: PostgreSQL COPY (bulk insert) instead of individual INSERTs.
- Loop INSERT for 200K rows: ~60-120 seconds
- COPY with generated data: ~3-5 seconds
- We generate data in Python, stream it into asyncpg's copy_to_table

Run: python scripts/seed.py
"""

import asyncio
import asyncpg
import os
import random
import uuid
from datetime import datetime, timezone, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/products_db")

CATEGORIES = [
    "Electronics", "Clothing", "Books", "Home & Kitchen",
    "Sports", "Toys", "Beauty", "Automotive", "Garden", "Food",
]

ADJECTIVES = [
    "Premium", "Classic", "Modern", "Eco", "Smart", "Ultra",
    "Pro", "Lite", "Max", "Plus", "Essential", "Deluxe",
]

NOUNS = [
    "Widget", "Gadget", "Toolkit", "Bundle", "Kit", "Set",
    "Pack", "Unit", "Device", "System", "Module", "Panel",
]

TOTAL = 200_000
BATCH_SIZE = 10_000  # stream in batches so memory stays low


def random_product():
    name = f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)} {random.randint(100, 9999)}"
    category = random.choice(CATEGORIES)
    price = round(random.uniform(9.99, 4999.99), 2)
    # Spread created_at over last 2 years so ordering is meaningful
    offset_seconds = random.randint(0, 2 * 365 * 24 * 3600)
    created_at = datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)
    updated_at = created_at + timedelta(seconds=random.randint(0, 86400))
    return (str(uuid.uuid4()), name, category, price, created_at, updated_at)


async def seed():
    print(f"Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)

    # Ensure table exists
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

    # Check existing count
    existing = await conn.fetchval("SELECT COUNT(*) FROM products")
    if existing >= TOTAL:
        print(f"Already have {existing} products — skipping seed.")
        await conn.close()
        return

    needed = TOTAL - existing
    print(f"Seeding {needed:,} products using COPY (bulk insert)...")

    start = asyncio.get_event_loop().time()
    inserted = 0

    while inserted < needed:
        batch_count = min(BATCH_SIZE, needed - inserted)
        records = [random_product() for _ in range(batch_count)]

        # asyncpg copy_records_to_table is the fastest bulk insert method
        await conn.copy_records_to_table(
            "products",
            records=records,
            columns=["id", "name", "category", "price", "created_at", "updated_at"],
        )

        inserted += batch_count
        elapsed = asyncio.get_event_loop().time() - start
        rate = inserted / elapsed if elapsed > 0 else 0
        print(f"  {inserted:>7,} / {needed:,} inserted  ({rate:,.0f} rows/sec)")

    total_time = asyncio.get_event_loop().time() - start
    final_count = await conn.fetchval("SELECT COUNT(*) FROM products")
    print(f"\nDone! {final_count:,} products in database. Time: {total_time:.1f}s")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
