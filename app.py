from flask import Flask, request, jsonify
import os
import datetime

app = Flask(__name__)

# Change this to a strong secret you create (used for basic security)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change-this-to-your-secret-2026")

@app.route('/webhook', methods=['POST'])
def webhook():
    # Check secret from header (we'll set this in TradingView and Render)
    auth_header = request.headers.get('Authorization')
    if auth_header != f"Bearer {WEBHOOK_SECRET}":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        payload = request.json
        received_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
        
        log = f"[{received_time}] TEST WEBHOOK RECEIVED:\n"
        log += f"Full Payload: {payload}\n"
        log += f"Symbol: {payload.get('symbol', 'N/A')}\n"
        log += f"Action: {payload.get('action', 'N/A')}\n"
        log += f"Quantity: {payload.get('quantity', 'N/A')} ({payload.get('quantity_type', 'N/A')})\n"
        log += f"Price: {payload.get('price', 'N/A')}\n"
        
        print(log)  # Shows in Render logs
        
        return jsonify({
            "status": "test-received",
            "message": "Webhook logged successfully - no real action taken",
            "payload": payload
        }), 200
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
