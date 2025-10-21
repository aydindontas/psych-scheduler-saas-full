import requests

def send_whatsapp_text(access_token: str, phone_number_id: str, to: str, text: str):
    # Real Cloud API call (uncomment to use production):
    # url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    # headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    # payload = {"messaging_product":"whatsapp", "to": to, "type":"text", "text":{"body": text}}
    # return requests.post(url, headers=headers, json=payload, timeout=10).json()
    # For demo (no token) we just mimic success:
    return {"ok": True, "queued": True}
