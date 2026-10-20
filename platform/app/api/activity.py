"""Combined history: the tenant's deposit events (the ones the wallet shows) and their invest transactions,
newest first, one typed list with a cursor."""
from flask import g, jsonify

from .. import db, investing
from . import ApiError, bp, make_cursor, money, page_args, tenant_api
from .deposits import event_json
from .me import TENANT_EVENT_TYPES

SOURCES = ("deposit_event", "invest_transaction")  # rank in this order for equal timestamps (higher rank first)


def _after(cursor, rank):
    """SQL condition and parameters for rows that come after the cursor in (at DESC, rank DESC, id DESC) order."""
    if not cursor:
        return "", []
    at, cur_rank, cur_id = cursor
    if rank < cur_rank:
        return " AND x.at <= ?", [at]
    if rank > cur_rank:
        return " AND x.at < ?", [at]
    return " AND (x.at < ? OR (x.at = ? AND x.id < ?))", [at, at, cur_id]


@bp.route("/activity", methods=["GET"])
@tenant_api
def activity():
    limit, cursor = page_args()
    if cursor and (len(cursor) != 3 or not isinstance(cursor[0], str) or cursor[1] not in (0, 1) or not isinstance(cursor[2], int)):
        raise ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
    items = []
    if g.tenant_ids:
        tph = ",".join("?" * len(g.tenant_ids))
        eph = ",".join("?" * len(TENANT_EVENT_TYPES))
        cond, params = _after(cursor, 0)
        for e in db.all_(f"SELECT x.*, d.pid, d.reference FROM deposit_events x JOIN deposits d ON d.id = x.deposit_id "
                         f"WHERE d.tenant_id IN ({tph}) AND d.status != 'concept' AND x.type IN ({eph}){cond} "
                         f"ORDER BY x.at DESC, x.id DESC LIMIT ?", (*g.tenant_ids, *TENANT_EVENT_TYPES, *params, limit + 1)):
            ev = event_json(e)
            items.append(((e["at"], 0, e["id"]), ev | {"type": "deposit_event", "event_type": ev["type"], "deposit_pid": e["pid"],
                                                        "deposit_reference": e["reference"]}))
    acct = investing.account_for_user(g.api_user["id"])
    if acct:
        cond, params = _after(cursor, 1)
        for t in db.all_(f"SELECT x.* FROM invest_transactions x WHERE x.account_id = ?{cond} ORDER BY x.at DESC, x.id DESC LIMIT ?",
                         (acct["id"], *params, limit + 1)):
            items.append(((t["at"], 1, t["id"]), {"type": "invest_transaction", "id": t["id"], "at": t["at"], "key": f"invest_{t['kind']}",
                                                   "params": {"amount_cents": t["amount_cents"]}, "kind": t["kind"],
                                                   "amount": money(t["amount_cents"]), "day": t["day"], "message": t["description"]}))
    items.sort(key=lambda x: x[0], reverse=True)
    page = items[:limit]
    return jsonify({"items": [i for _, i in page],
                    "next_cursor": make_cursor(list(page[-1][0])) if len(items) > limit and page else None})
