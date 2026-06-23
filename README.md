# Product Browse API

Cursor-based pagination over 200,000 products — fast, stable, and correct even while data changes.

**Live API:** `https://codevector-products-api-8t7a.onrender.com`  
**Docs:** `https://codevector-products-api-8t7a.onrender.com/docs`

## The core problem

> "If 50 new products are added while someone is browsing, they must not see the same product twice or miss one."

Standard `OFFSET` pagination breaks this guarantee:

```
Page 1: OFFSET 0  → rows 1-20   ✅
[5 new products inserted]
Page 2: OFFSET 20 → rows 21-40  ❌ rows 16-20 appear again (shifted)
```

Cursor-based pagination fixes this:

```
Page 1: WHERE created_at < NOW() ORDER BY created_at DESC → rows 1-20  ✅
[5 new products inserted — they go to the top, not into our window]
Page 2: WHERE created_at < [cursor] ORDER BY created_at DESC → rows 21-40 ✅
```

## Why cursor pagination is also faster

- `OFFSET 100000` forces Postgres to scan and discard 100,000 rows
- `WHERE (created_at, id) < (:t, :id)` hits the composite index directly — O(log n)

## API

### GET /products

```
GET /products?limit=20
GET /products?category=Electronics&limit=20
GET /products?cursor=<next_cursor>&limit=20
GET /products?category=Electronics&cursor=<next_cursor>
```

Response:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Premium Widget 4821",
      "category": "Electronics",
      "price": 299.99,
      "created_at": "2024-07-15T10:00:00Z",
      "updated_at": "2024-07-15T10:00:00Z"
    }
  ],
  "next_cursor": "eyJ0IjogIjIwMjQtMDctMTVUMTA...",
  "has_next": true,
  "count": 20
}
```

Pass `next_cursor` as `cursor` in your next request to get the next page.

### GET /categories

Returns all distinct categories.

### GET /health

Health check.

## Database index

```sql
-- Used for all queries (with or without category filter)
CREATE INDEX idx_products_created_at_id
    ON products (created_at DESC, id DESC);

-- Used when category filter is active
CREATE INDEX idx_products_category_created_at_id
    ON products (category, created_at DESC, id DESC);
```

## Setup

### 1. Free database (Neon)

1. Go to [neon.tech](https://neon.tech) → create free project
2. Copy the connection string

### 2. Run locally

```bash
git clone https://github.com/Akleshsoni/codevector-products-api
cd codevector-products-api
pip install -r requirements.txt

cp .env.example .env
# Add your DATABASE_URL to .env

# Seed 200,000 products (takes ~5 seconds)
python scripts/seed.py

# Start API
uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

### 3. Deploy to Render (free)

1. Push to GitHub
2. Go to [render.com](https://render.com) → New Web Service → connect repo
3. Add `DATABASE_URL` environment variable
4. Deploy — runs `render.yaml` automatically

## Seed script

`scripts/seed.py` generates 200,000 products using PostgreSQL `COPY` (bulk insert):

- **Loop INSERT**: ~60-120 seconds for 200K rows
- **COPY method**: ~3-5 seconds for 200K rows

Data is randomized across 10 categories, realistic price range, and spread over 2 years of timestamps so ordering is meaningful.

## What I'd improve with more time

1. **Search** — full-text search on product name using PostgreSQL `tsvector`
2. **Caching** — Redis cache for the first page of popular categories
3. **Rate limiting** — per-IP request limiting on the browse endpoint
4. **Metrics** — query latency tracking with Prometheus

## How I used AI

Used Claude to help structure the cursor encoding/decoding logic and to double-check the composite index design. The core pagination approach (cursor vs offset tradeoffs) I worked out myself — it's a well-known database pattern. Claude suggested using `asyncpg.copy_records_to_table` for the seed script which I verified in the asyncpg docs and confirmed was the right approach.

## Author

Aklesh Soni — [github.com/Akleshsoni](https://github.com/Akleshsoni)
