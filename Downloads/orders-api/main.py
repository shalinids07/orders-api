from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from collections import defaultdict, deque
import time
import uuid
import json

app = FastAPI()

# -----------------------
# CORS
# -----------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 58
RATE_LIMIT = 17
WINDOW = 10

# -----------------------
# Fixed Orders
# -----------------------
orders_catalog = [
    {
        "id": i,
        "name": f"order-{i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -----------------------
# Memory
# -----------------------
idempotency_store = {}
client_requests = defaultdict(deque)

# -----------------------
# Request Model
# -----------------------
class OrderIn(BaseModel):
    item: Optional[str] = None
    quantity: Optional[int] = None


# -----------------------
# Rate Limiter Middleware
# -----------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client_id = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    q = client_requests[client_id]

    while q and now - q[0] >= WINDOW:
        q.popleft()

    if len(q) >= RATE_LIMIT:

        retry_after = max(
            1,
            int(WINDOW - (now - q[0])) + 1
        )

        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            },
            headers={
                "Retry-After": str(retry_after)
            }
        )

    q.append(now)

    response = await call_next(request)

    return response


# -----------------------
# POST /orders
# -----------------------
@app.post("/orders", status_code=201)
async def create_order(
    order: Optional[OrderIn] = None,
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key"
    )
):

    if idempotency_key is None:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key"
        )

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    created = {
        "id": str(uuid.uuid4()),
        "item": order.item if order else None,
        "quantity": order.quantity if order else None,
    }

    idempotency_store[idempotency_key] = created

    return created


# -----------------------
# GET /orders
# -----------------------
@app.get("/orders")
async def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

    limit = max(1, min(limit, 100))

    start = 0

    if cursor:
        try:
            decoded = json.loads(cursor)
            start = int(decoded.get("index", 0))
        except:
            start = 0

    items = orders_catalog[start:start + limit]

    next_cursor = None

    next_index = start + len(items)

    if next_index < len(orders_catalog):
        next_cursor = json.dumps(
            {
                "index": next_index
            }
        )

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# -----------------------
# Root
# -----------------------
@app.get("/")
async def root():
    return {
        "status": "ok"
    }
