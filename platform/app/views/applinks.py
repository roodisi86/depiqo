"""Universal links (iOS) and App Links (Android) for the tenant app, and the web fallback for /app-link/*.

/t/<token> (an invitation) and /app-link/* open the app when it is installed. Without the app the
browser shows the existing web pages: /t/ is the invitation page itself, /app-link/* redirects to
the matching wallet page.
"""
from flask import Blueprint, abort, current_app, jsonify, redirect, url_for

bp = Blueprint("applinks", __name__)

APP_PATHS = ("/t/*", "/app-link/*")


def _ios_app_id():
    team = current_app.config.get("APP_IOS_TEAM_ID")
    if not team:
        if current_app.config.get("ENV_NAME") == "production":
            return None
        team = "TEAMID0000"  # development placeholder, so the file can be inspected
    return f"{team}.{current_app.config['APP_BUNDLE_ID']}"


@bp.route("/.well-known/apple-app-site-association")
def apple_app_site_association():
    app_id = _ios_app_id()
    if not app_id:
        abort(404)
    return jsonify({
        "applinks": {
            "apps": [],
            "details": [{
                "appIDs": [app_id], "appID": app_id,
                "components": [{"/": "/t/*", "comment": "Uitnodiging van de verhuurder"},
                               {"/": "/app-link/*", "comment": "Links uit meldingen en e-mails"}],
                "paths": list(APP_PATHS),
            }],
        },
        "webcredentials": {"apps": [app_id]},
    })


@bp.route("/.well-known/assetlinks.json")
def assetlinks():
    certs = [c.strip().upper() for c in (current_app.config.get("ANDROID_SHA256_CERT") or "").split(",") if c.strip()]
    if not certs:
        if current_app.config.get("ENV_NAME") == "production":
            abort(404)
        certs = ["00:" * 31 + "00"]  # development placeholder
    return jsonify([{
        "relation": ["delegate_permission/common.handle_all_urls", "delegate_permission/common.get_login_creds"],
        "target": {"namespace": "android_app", "package_name": current_app.config["APP_BUNDLE_ID"], "sha256_cert_fingerprints": certs},
    }])


@bp.route("/app-link/")
@bp.route("/app-link/<path:rest>")
def app_link(rest=""):
    """Without the app: the same place on the website (login first when needed)."""
    parts = [p for p in rest.split("/") if p]
    if len(parts) == 2 and parts[0] == "borg":
        return redirect(url_for("wallet.deposit", pid=parts[1]))
    if parts and parts[0] == "beleggen":
        return redirect(url_for("invest.index"))
    if parts and parts[0] == "beveiliging":
        return redirect(url_for("auth.security"))
    return redirect(url_for("wallet.home"))
