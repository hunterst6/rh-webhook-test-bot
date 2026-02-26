from flask import Flask, request, jsonify
import os
import datetime

app = Flask(__name__)

# Your secret (same as Pine input — keep in sync!)
EXPECTED_TOKEN = os.environ.get("WEBHOOK_SECRET", "dragon-this-to-your-secret-2026")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.json
        
        # Security: check bearer_token field in JSON
        received_token = payload.get('bearer_token')
        if received_token != EXPECTED_TOKEN:
            print(f"Unauthorized token: {received_token}")
            return jsonify({"error": "Unauthorized"}), 401
        
        received_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
        
        log = f"[{received_time}] AUTHORIZED WEBHOOK RECEIVED:\n"
        log += f"Full Payload: {payload}\n"
        log += f"Symbol: {payload.get('symbol', 'N/A')}\n"
        log += f"Action: {payload.get('action', 'N/A')}\n"
        log += f"Quantity: {payload.get('quantity', 'N/A')} ({payload.get('quantity_type', 'N/A')})\n"
        log += f"Price: {payload.get('price', 'N/A')}\n"
        
        print(log)
        
        return jsonify({
            "status": "received",
            "message": "Webhook processed successfully"
        }), 200
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
