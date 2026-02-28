from flask import Flask, request, jsonify
import os
import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback
import sys

app = Flask(__name__)

# Force logs to show up immediately in Render
def vprint(message):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}")
    sys.stdout.flush()

# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────
EXPECTED_TOKEN = os.environ.get("WEBHOOK_SECRET", "dragon-this-to-your-secret-2026")

EMAIL_SENDER    = os.environ.get("EMAIL_SENDER", "hunterst1234@gmail.com")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "hunterst6@icloud.com")

# Use a persistent path for Render
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
            vprint(f"✅ LEDGER LOADED: ${portfolio['cash']:.2f} Cash available.")
        except Exception as e:
            vprint(f"❌ LEDGER LOAD FAILED: {str(e)}")

def save_ledger():
    try:
        os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
        with open(LEDGER_FILE, 'w') as f:
            json.dump(portfolio, f, indent=4)
    except Exception as e:
        vprint(f"❌ LEDGER SAVE FAILED: {str(e)}")

load_ledger()

def calculate_portfolio_value():
    total = portfolio["cash"]
    for sym, pos in portfolio["positions"].items():
        total += pos["qty"] * pos["avg_price"]
    return total

def send_trade_email(action, symbol, qty, price, value):
    subject = f"Trade Executed: {action.upper()} {symbol}"
    body = f"Action: {action.upper()} {symbol}\nQty: {qty:.6f}\nPrice: ${price:.6f}\nValue: ${value:.2f}\nCash Remaining: ${portfolio['cash']:.2f}"
    
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, EMAIL_RECIPIENT, subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        vprint(f"📧 Email sent for {symbol}")
    except Exception as e:
        vprint(f"📧 Email failed: {str(e)}")

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
        # 1. IMMEDIATE LOGGING OF INCOMING DATA
        raw_data = request.data.decode('utf-8')
        vprint(f"📥 INCOMING WEBHOOK: {raw_data}")
        payload = json.loads(raw_data)
        
        # 2. AUTHENTICATION CHECK
        received_token = request.headers.get('Authorization', '').replace('Bearer ', '').strip() or payload.get('bearer_token')
        if received_token != EXPECTED_TOKEN:
            vprint("⚠️ UNAUTHORIZED: Token mismatch.")
            return jsonify({"error": "Unauthorized"}), 401
        
        action = payload.get('action')
        symbol = payload.get('symbol', '').replace('-USD', '')
        price = float(payload.get('price', 0))
        
        # 3. BUY LOGIC
        if action == "buy":
            qty_val = float(payload.get('quantity', 0))
            if payload.get('quantity_type') == 'percent_of_cash':
                qty_cash = portfolio["cash"] * (qty_val / 100)
                vprint(f"💰 BUY REQUEST: {qty_val}% of cash (${portfolio['cash']:.2f}) -> Target: ${qty_cash:.2f}")
            else:
                qty_cash = qty_val
                
            if qty_cash > portfolio["cash"]:
                vprint(f"⚠️ SCALING DOWN: Not enough cash. Adjusting ${qty_cash:.2f} to ${portfolio['cash']:.2f}")
                qty_cash = portfolio["cash"]
                
            if qty_cash <= 1.0:
                vprint("⏭️ SKIPPED: Portfolio is already fully invested (Balance too low).")
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
            
            vprint(f"🚀 EXECUTED BUY: {qty_coins:.6f} {symbol} at ${price:.4f}")
            log_trade("BUY", symbol, qty_coins, price, qty_cash)
        
        # 4. SELL LOGIC
        elif action == "sell":
            if symbol not in portfolio["positions"]:
                vprint(f"⏭️ SKIPPED SELL: No open position for {symbol}.")
                return jsonify({"status": "no_position"}), 200
            
            pos = portfolio["positions"][symbol]
            qty_pct = float(payload.get('quantity', 100)) / 100
            sell_qty = pos["qty"] * qty_pct
            sell_value = sell_qty * price
            
            portfolio["cash"] += sell_value
            pos["qty"] -= sell_qty
            if pos["qty"] <= 0: 
                del portfolio["positions"][symbol]
            
            vprint(f"📉 EXECUTED SELL: {sell_qty:.6f} {symbol} at ${price:.4f}. Recovered ${sell_value:.2f}")
            log_trade("SELL", symbol, sell_qty, price, sell_value)
            
        return jsonify({"status": "processed"}), 200
    except Exception as e:
        vprint(f"💥 CRITICAL ERROR: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    vprint("🤖 BOT STARTING...")
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
