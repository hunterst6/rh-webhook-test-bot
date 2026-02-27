from flask import Flask, request, jsonify
import os
import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback

app = Flask(__name__)

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
EXPECTED_TOKEN = os.environ.get("WEBHOOK_SECRET", "dragon-this-to-your-secret-2026")

EMAIL_SENDER    = os.environ.get("EMAIL_SENDER", "hunterst1234@gmail.com")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "hunterst6@icloud.com")

LEDGER_FILE = "/data/portfolio.json"  # Change to "/var/data/portfolio.json" if your mount path is different

# ──────────────────────────────────────────────
# LEDGER STATE
# ──────────────────────────────────────────────
portfolio = {
    "cash": 20000.0,
    "positions": {},
    "trades": []
}

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
        os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
        with open(LEDGER_FILE, 'w') as f:
            json.dump(portfolio, f, indent=4)
        print(f"Saved ledger to {LEDGER_FILE}")
    except Exception as e:
        print(f"Failed to save ledger: {e}")

load_ledger()

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
    
    save_ledger()

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
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Email failed: {str(e)}")
        traceback.print_exc()

# ──────────────────────────────────────────────
# WEBHOOK ENDPOINT - FORCE JSON PARSE
# ──────────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Step 1: Try normal JSON parse
        payload = request.get_json(silent=True)
        
        # Step 2: If failed, force parse from raw body (ignores Content-Type)
        if payload is None:
            raw_body = request.data.decode('utf-8', errors='ignore').strip()
            print(f"Raw request body received: {raw_body}")  # LOG RAW BODY FOR DEBUG
            if raw_body:
                try:
                    payload = json.loads(raw_body)
                except json.JSONDecodeError as e:
                    print(f"JSON parse from raw body failed: {str(e)}")
                    return jsonify({"error": "Invalid JSON"}), 400
            else:
                print("Empty request body")
                return jsonify({"error": "Empty body"}), 400
        
        if payload is None:
            print("No payload after all attempts")
            return jsonify({"error": "No payload"}), 400
        
        # Token check (body or header)
        received_token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            received_token = auth_header[7:].strip()
        if received_token is None:
            received_token = payload.get('bearer_token')
        
        if received_token != EXPECTED_TOKEN:
            print(f"Unauthorized token: {received_token}")
            return jsonify({"error": "Unauthorized"}), 401
        
        # Process trade
        action = payload.get('action')
        symbol_raw = payload.get('symbol', '')
        symbol = symbol_raw.replace('-USD', '')
        price = float(payload.get('price', 0))
        
        if price <= 0:
            return jsonify({"error": "Invalid price"}), 400
        
        print(f"Processing {action} for {symbol} @ ${price}")
        
        if action == "buy":
            qty_cash = float(payload.get('quantity', 0))
            if qty_cash > portfolio["cash"]:
                qty_cash = portfolio["cash"]
            if qty_cash <= 0:
                return jsonify({"status": "zero_buy"}), 200
            
            qty_coins = qty_cash / price
            portfolio["cash"] -= qty_cash
            
            if symbol in portfolio["positions"]:
                pos = portfolio["positions"][symbol]
                new_qty = pos["qty"] + qty_coins
                new_avg = (pos["qty"] * pos["avg_price"] + qty_coins * price) / new_qty
                pos["qty"] = new_qty
                pos["avg_price"] = new_avg
            else:
                portfolio["positions"][symbol] = {"qty": qty_coins, "avg_price": price}
            
            log_trade("BUY", symbol, qty_coins, price, qty_cash)
        
        elif action == "sell":
            if symbol not in portfolio["positions"]:
                print(f"No position in {symbol} to sell")
                return jsonify({"status": "no_position"}), 200
            
            pos = portfolio["positions"][symbol]
            qty_percent = float(payload.get('quantity', 100)) / 100 if payload.get('quantity_type') == 'percent_of_equity' else 1.0
            sell_qty = pos["qty"] * qty_percent
            
            sell_value = sell_qty * price
            portfolio["cash"] += sell_value
            pos["qty"] -= sell_qty
            
            if pos["qty"] <= 0:
                del portfolio["positions"][symbol]
            
            log_trade("SELL", symbol, sell_qty, price, sell_value)
        
        return jsonify({"status": "processed"}), 200
    
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────────────────────
# MANUAL REPORT & RESET
# ──────────────────────────────────────────────
@app.route('/send-report', methods=['GET'])
def manual_report():
    send_daily_email()
    return jsonify({"status": "report_sent"}), 200

@app.route('/reset-ledger', methods=['GET'])
def reset_ledger():
    global portfolio
    try:
        if os.path.exists(LEDGER_FILE):
            os.remove(LEDGER_FILE)
            print(f"Deleted ledger file: {LEDGER_FILE}")
        portfolio = {
            "cash": 20000.0,
            "positions": {},
            "trades": []
        }
        save_ledger()
        return jsonify({"status": "ledger_reset", "cash": 20000.0}), 200
    except Exception as e:
        print(f"Reset failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
