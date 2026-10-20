"""Inbound events from financial partners. Authenticated by HMAC signature, idempotent by event id."""
import json

from flask import Blueprint, abort, current_app, jsonify, request

from .. import services
from ..partners import provider_allowed, verify_webhook

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


@bp.route("/bank/<provider>", methods=["POST"])
def bank_event(provider):
    if not provider_allowed(provider):
        abort(404)  # only the configured, available partner; sandbox events are refused when the sandbox is off
    body = request.get_data(cache=False, as_text=False)
    if not verify_webhook(body, request.headers.get("X-Depiqo-Signature"), current_app.config["BANK_WEBHOOK_SECRET"]):
        abort(401)
    try:
        event = json.loads(body)
        result = services.handle_bank_event(provider, event["type"], event["data"])
    except (KeyError, ValueError, TypeError, AttributeError, services.WorkflowError) as exc:
        return jsonify({"error": str(exc)[:200]}), 422
    return jsonify({"result": result})


@bp.route("/invest/<provider>", methods=["POST"])
def invest_event(provider):
    """0.5.0: events from the investment partner (account activated, deposit, order executed, withdrawal, fee)."""
    from .. import investing
    if not investing.provider_allowed(provider):
        abort(404)
    body = request.get_data(cache=False, as_text=False)
    if not verify_webhook(body, request.headers.get("X-Depiqo-Signature"), current_app.config["INVEST_WEBHOOK_SECRET"]):
        abort(401)
    try:
        event = json.loads(body)
        result = investing.handle_event(provider, event["type"], event["data"])
    except (KeyError, ValueError, TypeError, AttributeError, investing.InvestError) as exc:
        return jsonify({"error": str(exc)[:200]}), 422
    return jsonify({"result": result})
