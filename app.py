from flask import Flask, request, jsonify
import os
import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback

app = Flask(__name__)

# CONFIG
EXPECTED_TOKEN = os.environ.get("WEBHOOK_SECRET", "dragon-this-to-your-secret-2026")

EMAIL_SENDER    = os.environ.get("EMAIL_SENDER", "hunterst1234@gmail.com")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "hunterst6@icloud.com")

LEDGER_FILE = "/data/portfolio.json"

# PORTFOLIO STATE – added realized_profit
portfolio = {
    "cash": 20000.0,
    "positions": {},  # {"DOGE": {"qty": 50000, "avg_price": 0.10}}
    "trades": [],
    "realized_profit": 0.0  # cumulative realized profit/loss from sells
}

def load_ledger():
    global portfolio
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, 'r') as f:
                loaded = json.load(f)
                portfolio.update(loaded)
            print(f"Loaded ledger: {len(portfolio['trades'])} trades, "
                  f"realized P/L ${portfolio['realized_profit']:.2f}")
        except Exception as e:
            print(f"Load failed: {e}. Starting fresh.")
    else:
        print("No ledger file - starting fresh")

def save_ledger():
    try:
        os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
        with open(LEDGER_FILE, 'w') as f:
            json.dump(portfolio, f, indent=4)
        print(f"Saved ledger - realized P/L ${portfolio['realized_profit']:.2f}")
    except Exception as e:
        print(f"Save failed: {e}")

load_ledger()

def calculate_unrealized_pnl(current_prices=None):
    """Unrealized profit/loss = sum (current_price - avg_price) * qty"""
    if current_prices is None:
        current_prices = {}  # fallback: use avg_price (zero unrealized)
    pnl = 0.0
    for sym, pos in portfolio["positions"].items():
        price = current_prices.get(sym, pos["avg_price"])
        pnl += (price - pos["avg_price"]) * pos["qty"]
    return pnl

def calculate_total_value(current_prices=None):
    return portfolio["cash"] + sum(
        pos["qty"] * current_prices.get(sym, pos["avg_price"])
        for sym, pos in portfolio["positions"].items()
    ) + calculate_unrealized_pnl(current_prices)

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
    print(f"Total Value: ${calculate_total_value({symbol: price}):.2f}")
    
    save_ledger()
    
    # Send instant email
    send_trade_email(action, symbol, qty, price, value)

def send_trade_email(action, symbol, qty, price, value):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
    subject = f"Trade Executed: {action.upper()} {symbol} - {timestamp}"
    
    body = f"{action.upper()} {symbol} executed\n\n"
    body += f"Time: {timestamp}\n"
    body += f"Quantity: {qty:.6f}\n"
    body += f"Price: ${price:.6f}\n"
    body += f"Value: ${value:.2f}\n"
    body += f"Cash after: ${portfolio['cash']:.2f}\n"
    
    if action == "sell":
        # Calculate realized profit for this sell
        pos = portfolio["positions"].get(symbol, {"avg_price": 0})
        cost_basis = qty * pos["avg_price"]
        realized_pnl = value - cost_basis
        portfolio["realized_profit"] += realized_pnl
        body += f"Cost basis: ${cost_basis:.2f}\n"
        body += f"Realized P/L this trade: ${realized_pnl:.2f}\n"
        body += f"Cumulative realized P/L: ${portfolio['realized_profit']:.2f}\n"
    
    body += f"Total Value: ${calculate_total_value({symbol: price}):.2f}\n"
    
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        print(f"Trade email sent: {subject}")
    except Exception as e:
        print(f"Trade email failed: {str(e)}")

def send_daily_email():
    today = datetime.date.today().strftime("%Y-%m-%d")
    report = f"Daily Paper Trade Report - {today}\n\n"
    report += f"Cash: ${portfolio['cash']:.2f}\n"
    report += "Positions:\n"
    for sym, pos in portfolio["positions"].items():
        report += f"  {sym}: {pos['qty']:.2f} @ avg ${pos['avg_price']:.6f}\n"
    
    total_value = calculate_total_value()
    unrealized_pnl = calculate_unrealized_pnl()
    report += f"\nEstimated Total Value: ${total_value:.2f}\n"
    report += f"Unrealized P/L: ${unrealized_pnl:.2f}\n"
    report += f"Cumulative Realized P/L: ${portfolio['realized_profit']:.2f}\n"
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
        print("Daily email sent successfully!")
    except Exception as e:
        print(f"Daily email failed: {str(e)}")

# ──────────────────────────────────────────────
# WEBHOOK ENDPOINT
# ──────────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        raw_body = request.data.decode('utf-8', errors='ignore').strip()
        print(f"RAW BODY RECEIVED: {raw_body}")
        
        if not raw_body:
            return jsonify({"error": "Empty body"}), 400
        
        payload = json.loads(raw_body)
        
        received_token = payload.get('bearer_token')
        if received_token != EXPECTED_TOKEN:
            print(f"Unauthorized token: {received_token}")
            return jsonify({"error": "Unauthorized"}), 401
        
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

# MANUAL ENDPOINTS
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
        portfolio = {
            "cash": 20000.0,
            "positions": {},
            "trades": [],
            "realized_profit": 0.0
        }
        save_ledger()
        return jsonify({"status": "ledger_reset", "cash": 20000.0}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
