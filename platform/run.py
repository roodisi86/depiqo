"""Development server. In production run with a WSGI server, for example:
    gunicorn -w 3 -b 0.0.0.0:8000 "run:app"

Send pending bank and invest instructions and push messages (run from cron or a scheduler, every minute is fine):
    python3 run.py dispatch
"""
import sys

from app import create_app

app = create_app()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "dispatch":
        from app import services
        with app.app_context():
            result = services.dispatch_instructions()
        if result["blocked"]:
            print(f"Niet verstuurd: {result['blocked']}")
            sys.exit(1)
        print(f"Verstuurd: {result['sent']}, opnieuw proberen: {result['retry']}, mislukt: {result['failed']}, overgeslagen: {result['skipped']}")
        from app import investing
        with app.app_context():
            inv = investing.dispatch()  # 0.5.0: instructions to the investment partner, same rules
            fees = investing.accrue_fees() if not inv["blocked"] else 0
        print("Beleggen: " + (f"niet verstuurd: {inv['blocked']}" if inv["blocked"] else
                              f"verstuurd: {inv['sent']}, mislukt: {inv['failed']}, servicekosten: {fees}"))
        from app import notify
        with app.app_context():
            push = notify.dispatch()  # 0.6.0: push messages to Expo (skipped in sandbox)
            receipts = notify.check_receipts()
        print(f"Push: verstuurd {push['sent']}, mislukt {push['failed']}, overgeslagen {push['skipped']}, ontvangstbewijzen {receipts}")
    else:
        app.run(host="127.0.0.1", port=5000, debug=False)
