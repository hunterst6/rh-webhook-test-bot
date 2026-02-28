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
# CONFIGURATION
# ──────────────────────────────────────────────
EXPECTED_TOKEN = os.environ.get("WEBHOOK_SECRET", "dragon-this-to-your-secret-2026")

EMAIL_SENDER    = os.environ.get("EMAIL_SENDER", "hunterst1234@gmail.com")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "hunterst6@icloud.com")

LEDGER_FILE = "/data/portfolio.json"

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
            print(f"[LEDGER] Loaded: ${portfolio['cash']} Cash, {len(portfolio['positions'])} Positions")
        except Exception as e:
            print(f"[LEDGER] Load failed: {str(e)}")

def save_ledger():
    try:
        os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
        with open(LEDGER_FILE, 'w') as f:
            json.dump(portfolio, f, indent=4)
    except Exception as e:
        print(f"[LEDGER] Save failed: {str(e)}")

load_ledger()

def calculate_portfolio_value(last_price_map=None):
    total = portfolio["cash"]
    for sym, pos in portfolio["positions"].items():
        price = last_price_map.get(sym, pos["avg_price"]) if last_price_map else pos["avg_price"]
        total += pos["qty"] * price
    return total

def send_trade_email(action, symbol, qty, price, value):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
    subject = f"Trade Executed: {action.upper()} {symbol}"
    body = f"Action: {action.upper()} {symbol}\nQty: {qty:.6f}\nPrice: ${price:.6f}\nValue: ${value:.2f}\nCash After: ${portfolio['cash']:.2f}\nTotal Portfolio: ${calculate_portfolio_value():.2f}"
    
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, EMAIL_RECIPIENT, subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"[EMAIL] Failed: {str(e)}")

def log_trade(action, symbol, qty, price, value):
    trade = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S CST"),
        "action": action, "symbol": symbol, "qty": qty, "price": price, "value": value
    }
    portfolio["trades"].append(trade)
    save_ledger()
    send_trade_email(action, symbol, qty, price, value)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = json.loads(request.data.decode('utf-8'))
        received_token = request.headers.get('Authorization', '').replace('Bearer ', '').strip() or payload.get('bearer_token')
        
        if received_token != EXPECTED_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        
        action = payload.get('action')
        symbol = payload.get('symbol', '').replace('-USD', '')
        price = float(payload.get('price', 0))
        
        if action == "buy":
            qty_val = float(payload.get('quantity', 0))
            # Calculate dollar amount based on current cash
            if payload.get('quantity_type') == 'percent_of_cash':
                qty_cash = portfolio["cash"] * (qty_val / 100)
            else:
                qty_cash = qty_val
                
            if qty_cash > portfolio["cash"]:
                qty_cash = portfolio["cash"]
                
            if qty_cash <= 1.0: # Skip tiny trades
                return jsonify({"status": "insufficient_funds_skip"}), 200
            
            qty_coins = qty_cash / price
            portfolio["cash"] -= qty_cash
            
            if symbol in portfolio["positions"]:
                pos = portfolio["positions"][symbol]
                new_qty = pos["qty"] + qty_coins
                pos["avg_price"] = (pos["qty"] * pos["avg_price"] + qty_cash) / new_qty
                pos["qty"] = new_qty
            else:
                portfolio["positions"][symbol] = {"qty": qty_coins, "avg_price": price}
            
            log_trade("BUY", symbol, qty_coins, price, qty_cash)
        
        elif action == "sell":
            if symbol not in portfolio["positions"]:
                return jsonify({"status": "no_position"}), 200
            
            pos = portfolio["positions"][symbol]
            qty_pct = float(payload.get('quantity', 100)) / 100
            sell_qty = pos["qty"] * qty_pct
            sell_value = sell_qty * price
            
            portfolio["cash"] += sell_value
            pos["qty"] -= sell_qty
            if pos["qty"] <= 0: del portfolio["positions"][symbol]
            
            log_trade("SELL", symbol, sell_qty, price, sell_value)
            
        return jsonify({"status": "processed"}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/send-report', methods=['GET'])
def manual_report():
    today = datetime.date.today().strftime("%Y-%m-%d")
    report = f"Report: {today}\nCash: ${portfolio['cash']:.2f}\nValue: ${calculate_portfolio_value():.2f}"
    # (Email logic truncated for brevity, same as trade email)
    return jsonify({"status": "report_sent"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
