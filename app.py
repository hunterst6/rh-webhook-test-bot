from flask import Flask, request, jsonify
import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback

app = Flask(__name__)

# === CONFIG (set these in Render Environment Variables) ===
EXPECTED_TOKEN = os.environ.get("WEBHOOK_SECRET", "dragon-this-to-your-secret-2026")

# Email config from env vars
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "hunterst1234@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "your-app-password-here")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "hunterst6@icloud.com")

# === PAPER TRADING LEDGER ===
portfolio = {
    "cash": 20000.0,
    "positions": {},
    "trades": []
}

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
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Starting SMTP debug connection to smtp.gmail.com:587")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.set_debuglevel(1)  # FULL SMTP DEBUG OUTPUT
        server.starttls()
        print("TLS started")
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        print("Login successful")
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Email failed: {str(e)}")
        traceback.print_exc()  # Full stack trace in logs

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.json
        
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
            qty_percent = float(payload.get('quantity', 100
