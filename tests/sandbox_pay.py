"""Simulate the sandbox gateway calling our webhook (signed). Dev only.
Usage: python scripts/sandbox_pay.py <order_id> <amount> [base_url] [event_id]"""
import hashlib, hmac, json, os, sys, uuid
import requests

order_id, amount = sys.argv[1], int(sys.argv[2])
base = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:5000"
event = sys.argv[4] if len(sys.argv) > 4 else uuid.uuid4().hex
body = json.dumps({"event_id": event, "order_id": order_id, "transaction_id": "tx_" + event, "amount": amount}).encode()
sig = hmac.new(os.getenv("SANDBOX_WEBHOOK_SECRET", "sandbox-secret").encode(), body, hashlib.sha256).hexdigest()
r = requests.post(f"{base}/api/v1/webhooks/sandbox", data=body, headers={"X-Sandbox-Signature": sig, "Content-Type": "application/json"})
print(r.status_code, r.text)
