from flask import Flask, request, jsonify
import os
import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback

app = Flask(__name__)

# === CONFIG ===
EXPECTED_TOKEN = os.environ.get("WEBHOOK_SECRET", "dragon-this-to-your-secret-2026")

EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "hunterst1234@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "hunterst6@icloud.com")

# Persistent disk path (match what you set in Render Disk mount path)
LEDGER_FILE = "/data/portfolio.json"  # Change to "/var/data/portfolio.json" if you kept default

# === LOAD / SAVE LEDGER ===
def load_ledger():
    global portfolio
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, 'r') as f:
                loaded = json.load(f)
                portfolio.update(loaded)
            print(f"Loaded persistent ledger from {LEDGER_FILE}")
        except Exception as e:
            print(f"Failed to load ledger: {e}. Starting fresh.")
    else:
        print(f"No ledger file at {LEDGER_FILE} - starting fresh")

def save_ledger():
    try:
        os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)  # Create dir if missing
        with open(LEDGER_FILE, 'w') as f:
            json.dump(portfolio, f, indent=4)
        print(f"Saved ledger to {LEDGER_FILE}")
    except Exception as e:
        print(f"Failed to save ledger: {e}")

# Initial ledger
portfolio = {
    "cash": 20000.0,
    "positions": {},
    "trades": []
}
load_ledger()  # Load on startup

def calculate_portfolio_value(last_price_map=None):
    total = portfolio["cash"]
    for sym, pos in portfolio["positions"].items():
        price = last_price_map.get(sym, pos["avg_price"]) if last_price_map else pos["avg_price"]
        total += pos["qty"] * price
    return total

def log_trade(action, symbol, qty, price, value):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
    trade = {
        "time": timestamp,
        "action": action,
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "value": value,
        "cash_after": portfolio["cash"],
        "positions_after": portfolio["positions"].copy()
    }
    portfolio["trades"].append(trade)
    
    print(f"[{timestamp}] {action.upper()} {symbol} | Qty: {qty:.6f} @ ${price:.6f} | Value: ${value:.2f}")
    print(f"Cash: ${portfolio['cash']:.2f} | Positions: {portfolio['positions']}")
    print(f"Estimated Total Value: ${calculate_portfolio_value({symbol: price}):.2f}")
    
    save_ledger()  # Save after every trade

def send_daily_email():
    today = datetime.date.today().strftime("%Y-%m-%d")
    report = f"9-Coin Fusion Paper Trading Report - {today}\n\n"
    report += f"Cash: ${portfolio['cash']:.2f}\n"
    report += "Positions:\n"
    for sym, pos in portfolio["positions"].items():
        report += f"  {sym}: {pos['qty']:.2f} @ avg ${pos['avg_price']:.6f}\n"
    
    total_value = calculate_portfolio_value()
    report += f"\nEstimated Total Value: ${total_value:.2f}\n"
    report += f"Total Trades: {len(portfolio['trades'])}\n"
    
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = f"Daily Paper Trade Report - {today}"
    msg.attach(MIMEText(report, 'plain'))

    try:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S CST')}] Starting SMTP...")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.set_debuglevel(1)
        server.ehlo()
        server.starttls()
        server.ehlo()
        print("Attempting login...")
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        print("Login successful")
        print("Sending message...")
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Email failed: {str(e)}")
        traceback.print_exc()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # First try normal JSON parse
        payload = request.get_json(silent=True)
        
        # If that fails (wrong/missing Content-Type), force parse from raw body
        if payload is None and request.data:
            try:
                raw_body = request.data.decode('utf-8').strip()
                if raw_body:
                    payload = json.loads(raw_body)
                else:
                    payload = {}
            except json.JSONDecodeError as e:
                print(f"JSON fallback parse failed: {str(e)} - Raw body: {raw_body}")
                return jsonify({"error": "Invalid JSON body"}), 400
        
        if payload is None:
            print("No payload received at all")
            return jsonify({"error": "No payload"}), 400
        
        # Now process as normal
        received_token = payload.get('bearer_token')
        if received_token != EXPECTED_TOKEN:
            print(f"Unauthorized token received: {received_token}")
            return jsonify({"error": "Unauthorized"}), 401
        
        # Your existing trade logic here
        action = payload.get('action')
        symbol_raw = payload.get('symbol', '')
        symbol = symbol_raw.replace('-USD', '')
        price = float(payload.get('price', 0))
        
        print(f"Received valid payload: {payload}")
        # ... rest of buy/sell simulation ...
        
        return jsonify({"status": "processed"}), 200
    
    except Exception as e:
        print(f"Webhook processing error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/send-report', methods=['GET'])
def manual_report():
    send_daily_email()
    return jsonify({"status": "report_attempted"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
