from flask import Flask, request, jsonify
import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# === CONFIG (set these in Render Environment Variables for security) ===
EXPECTED_TOKEN = "dragon-this-to-your-secret-2026"  # Must match your Pine script secretToken

# Email config (add these as env vars on Render)
EMAIL_SENDER = "yourgmail@gmail.com"          # Your Gmail address
EMAIL_PASSWORD = "your-16-char-app-password"  # Gmail App Password (not regular password)
EMAIL_RECIPIENT = "your-email@example.com"    # Where daily reports go

# === PAPER TRADING LEDGER (in-memory — resets on restart) ===
portfolio = {
    "cash": 20000.0,                          # Starting virtual capital
    "positions": {},                          # e.g. {"DOGE": {"qty": 50000, "avg_price": 0.10}}
    "trades": []                              # List of all simulated trades
}

def calculate_portfolio_value(last_price_map=None):
    """Estimate total value (cash + positions). Uses last known price if available."""
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
    report = f"9-Coin Fusion Paper Trading Daily Summary - {today}\n\n"
    
    report += f"Starting Cash: $20000.00\n"
    report += f"Current Cash: ${portfolio['cash']:.2f}\n"
    
    report += "\nCurrent Positions:\n"
    for sym, pos in portfolio["positions"].items():
        report += f"  {sym}: {pos['qty']:.2f} coins @ avg ${pos['avg_price']:.6f}\n"
    
    total_value = calculate_portfolio_value()  # Approximate without current prices
    report += f"\nEstimated Total Portfolio Value: ${total_value:.2f}\n"
    
    report += f"\nTotal Trades: {len(portfolio['trades'])}\n"
    report += f"Recent Trades (last 5):\n"
    for trade in portfolio["trades"][-5:]:
        report += f"  {trade['time']} | {trade['action']} {trade['symbol']} | {trade['qty']:.2f} @ ${trade['price']:.6f}\n"
    
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
        print(f"Daily email sent to {EMAIL_RECIPIENT}")
    except Exception as e:
        print(f"Email failed: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.json
        
        # Security: check bearer_token inside JSON
        received_token = payload.get('bearer_token')
        if received_token != EXPECTED_TOKEN:
            print(f"Unauthorized token received: {received_token}")
            return jsonify({"error": "Unauthorized"}), 401
        
        action = payload.get('action')
        symbol_raw = payload.get('symbol', '')
        symbol = symbol_raw.replace('-USD', '')  # Clean to DOGE, PEPE, etc.
        price = float(payload.get('price', 0))
        
        if price <= 0:
            return jsonify({"error": "Invalid or missing price"}), 400
        
        if action == "buy":
            qty_cash = float(payload.get('quantity', 0))
            if qty_cash > portfolio["cash"]:
                qty_cash = portfolio["cash"]  # Can't overspend
            
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
        
        # Optional: Send daily email manually for testing (remove later)
        # if action == "sell":  # e.g., trigger on sells
        #     send_daily_email()
        
        return jsonify({
            "status": "paper_trade_processed",
            "portfolio_summary": {
                "cash": portfolio["cash"],
                "positions": portfolio["positions"],
                "total_value_estimate": calculate_portfolio_value({symbol: price})
            }
        }), 200
    
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Optional test route to trigger daily email manually (GET http://your-url/send-report)
@app.route('/send-report', methods=['GET'])
def manual_report():
    send_daily_email()
    return jsonify({"status": "daily_report_sent"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
