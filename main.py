from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
import math

app = FastAPI()

# ---- Sisend mudel (handshake + weekly) ----
class DecisionRequest(BaseModel):
    # Handshake
    handshake: Optional[bool] = False
    ping: Optional[str] = None
    seed: Optional[int] = None

    # Weekly (v1.2)
    mode: Optional[str] = None                 # "blackbox" | "glassbox"
    week: Optional[int] = None
    weeks_total: Optional[int] = None
    weeks: Optional[List[Dict[str, Any]]] = None

    # Ühilduvus /docs kiireks testiks
    inventory: Optional[int] = None
    backlog: Optional[int] = None
    incoming_orders: Optional[int] = None
    arriving_shipments: Optional[int] = None
    role: Optional[str] = None
    week_compat: Optional[int] = None

# ---- PARAMEETRID (vähem agressiivne, väiksem ladu) ----
SAFETY  = {"retailer": 6,  "wholesaler": 10, "distributor": 14, "factory": 18}
KAPPA   = {"retailer": 0.45, "wholesaler": 0.55, "distributor": 0.60, "factory": 0.65}
LOW_THR = {"retailer": 6,  "wholesaler": 8,  "distributor": 10, "factory": 12}
MIN_ORD = {"retailer": 1,  "wholesaler": 2,  "distributor": 3,  "factory": 4}
CAP_BUF = {"retailer": 8,  "wholesaler": 10, "distributor": 12, "factory": 14}
DEADBAND = {"retailer": 1, "wholesaler": 2, "distributor": 2, "factory": 3}   # UUS
ROLES = ("retailer", "wholesaler", "distributor", "factory")

def order_for_role(rname: str, rstate: Dict[str, Any]) -> int:
    role    = rname.lower()
    safety  = SAFETY.get(role, 12)
    kappa   = KAPPA.get(role, 0.65)
    low_thr = LOW_THR.get(role, 9)
    min_ord = MIN_ORD.get(role, 2)
    cap_buf = CAP_BUF.get(role, 20)
    db      = DEADBAND.get(role, 1)

    inv = int(rstate.get("inventory", 0) or 0)
    bkl = int(rstate.get("backlog", 0) or 0)
    inc = int(rstate.get("incoming_orders", 0) or 0)
    arr = int(rstate.get("arriving_shipments", 0) or 0)

    effective = inv + arr
    target = safety + inc + bkl

    # --- deadband: väga väikse puudujäägi korral ei telli üldse
    gap = target - effective
    if gap <= db:
        gap = 0
    elif gap < 0:
        gap = 0

    order = math.ceil(kappa * gap)

    if effective < low_thr:
        order = max(order, min_ord)

    cap = (inc + bkl) + cap_buf
    if order > cap:
        order = cap

    if order < 0:
        order = 0
    return int(order)

@app.post("/api/decision")
def decide(req: DecisionRequest):
    # ---- v1.2 HANDSHAKE ----
    if req.handshake:
        return {
            "ok": True,
            "student_email": "krissu@taltech.ee",
            "algorithm_name": "BeerBotBaseline",
            "version": "v1.0.0",
            "supports": {"blackbox": True, "glassbox": False},
            "message": "BeerBot ready"
        }

    # ---- v1.2 WEEKLY STEP ----
    if req.weeks:
        last = req.weeks[-1]
        roles_block = (last.get("roles") or {}) if isinstance(last, dict) else {}
        orders: Dict[str, int] = {}
        for rname in ROLES:
            rstate = roles_block.get(rname, {}) if isinstance(roles_block, dict) else {}
            orders[rname] = order_for_role(rname, rstate)
        return {"orders": orders}

    # ---- Ühilduvus /docs kiireks testimiseks ----
    if req.role is not None or any(v is not None for v in [req.inventory, req.backlog, req.incoming_orders, req.arriving_shipments]):
        rname = (req.role or "retailer").lower()
        rstate = {
            "inventory": req.inventory or 0,
            "backlog": req.backlog or 0,
            "incoming_orders": req.incoming_orders or 0,
            "arriving_shipments": req.arriving_shipments or 0,
        }
        one = order_for_role(rname, rstate)
        return {"orders": {r: (one if r == rname else one) for r in ROLES}}

    # Vaikimisi ohutu vastus
    return {"orders": {r: 10 for r in ROLES}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

