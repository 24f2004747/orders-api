from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import time
import base64

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assignment values
TOTAL_ORDERS = 54
RATE_LIMIT = 19
WINDOW = 10  # seconds

# Fixed catalog of orders
catalog = [
    {
        "id": i,
        "item": f"Order-{i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# Stores
idempotency_store = {}
rate_limit_store = {}


class OrderCreate(BaseModel):
    item: str = "sample"


def check_rate_limit(client_id: str):
    now = time.time()

    timestamps = rate_limit_store.get(client_id, [])

    # Keep only requests in last 10 seconds
    timestamps = [t for t in timestamps if now - t < WINDOW]

    if len(timestamps) >= RATE_LIMIT:
        retry_after = max(1, int(WINDOW - (now - timestamps[0])) + 1)

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(retry_after)
            },
        )

    timestamps.append(now)
    rate_limit_store[client_id] = timestamps


@app.get("/")
def home():
    return {"status": "ok"}


@app.post("/orders", status_code=201)
def create_order(
    order: OrderCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    client_id: str = Header("default", alias="X-Client-Id"),
):
    check_rate_limit(client_id)

    # Same key -> return same order
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    created = {
        "id": str(uuid.uuid4()),
        "item": order.item,
    }

    idempotency_store[idempotency_key] = created

    return created


@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: str | None = None,
    client_id: str = Header("default", alias="X-Client-Id"),
):
    check_rate_limit(client_id)

    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor.encode()).decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    end = min(start + limit, TOTAL_ORDERS)

    items = catalog[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
