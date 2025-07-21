import datetime
import math
from nsepython import *
from scipy.stats import norm
import yfinance as yf
import pandas as pd
import crypto_telegram_bot

# --- Parameters ---
RISK_FREE_RATE = 0.068  # 6.8%
IV_THRESHOLD = 25       # IV Crush Warning
TRADING_START = datetime.time(9, 30)
TRADING_END = datetime.time(15, 15)

results = []
trend_map = {}

def detect_trend(symbol):
    index_symbol = "NIFTYBEES.NS" if symbol == "NIFTY" else "BANKBEES.NS"
    df = yf.download(index_symbol, period="1d", interval="1m", progress=False, auto_adjust=True)
    df.index = pd.to_datetime(df.index)
    df = df.tz_convert('Asia/Kolkata')  # Convert from UTC to IST
    print(df,"----")
    # Keep only data after 09:15 AM
    df = df.between_time("09:15", "15:25")  # Or "16:00" depending on your trading end time

    if df.empty or len(df) < 5:
        print(f"⚠️ Not enough data for {symbol} to detect trend.")
        trend_map[symbol] = "sideways"
        return "sideways"

    close_930 = float(df["Close"].iloc[-1].item())
    open_915 = float(df["Open"].iloc[0].item())
    pct_change = ((close_930 - open_915) / open_915) * 100

    trend = "sideways"
    if pct_change > 0.3:
        trend = "up"
    elif pct_change < -0.3:
        trend = "down"

    print(f"📉 {symbol} Trend (9:15–9:30): {trend.upper()} ({pct_change:.2f}%)")
    trend_map[symbol] = trend
    return trend

def black_scholes_price(S, K, T, r, sigma, option_type="call"):
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "call":
        price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = -norm.cdf(-d1)

    theta = (-S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))) / 365
    vega = S * norm.pdf(d1) * math.sqrt(T) / 100

    return price, delta, theta, vega


def get_best_option(symbol):
    # now = now_ist.time()
    # if now < TRADING_START or now > TRADING_END:
    #     print(f"\n⏳ Outside trading window ({TRADING_START} - {TRADING_END}). Skipping {symbol}.")
    #     return

    print(f"\n📊 Checking {symbol}...")
    try:
        trend = detect_trend(symbol)

        data = nse_optionchain_scrapper(symbol)
        expiry_dates = data['records']['expiryDates']
        expiry = expiry_dates[0]
        spot = float(data['records']['underlyingValue'])

        expiry_dt = datetime.datetime.strptime(expiry, "%d-%b-%Y")
        today = datetime.datetime.today()
        days_to_expiry = (expiry_dt - today).days
        T = days_to_expiry / 365 if days_to_expiry > 0 else 1 / 365  # expiry day logic

        print(f"➡️ Spot: {spot:.2f} | Expiry: {expiry} | T: {T:.4f} years")

        r = RISK_FREE_RATE
        best_call, best_put = None, None
        max_call_score, max_put_score = -1, -1

        for row in data['records']['data']:
            strike = row['strikePrice']
            for opt_type in ['CE', 'PE']:
                if opt_type not in row:
                    continue
                opt = row[opt_type]
                iv = opt.get('impliedVolatility', 0) / 100
                volume = opt.get('totalTradedVolume', 0)
                ltp = opt.get('lastPrice', 0)

                if iv == 0 or volume == 0 or ltp == 0:
                    continue

                if abs(strike - spot) > 200:
                    continue

                option_type = "call" if opt_type == "CE" else "put"
                theo_price, delta, theta, vega = black_scholes_price(spot, strike, T, r, iv, option_type)

                score = 0
                if theo_price > ltp:
                    score += 30
                score += min(volume / 1000, 20)
                score += delta * 20 if option_type == "call" else abs(delta) * 20
                score += vega * 10
                score += -theta * 5
                if iv * 100 > IV_THRESHOLD:
                    score -= 20  # IV crush risk

                stop_loss = round(ltp * 0.8, 2)  # 20% SL
                target = round(ltp + 2 * (ltp - stop_loss), 2)  # 1:2 R:R

                recommendation = (symbol, expiry, option_type.upper(), strike, ltp, theo_price, iv * 100, delta, theta, vega, volume, score, stop_loss, target)

                if option_type == "call" and score > max_call_score:
                    best_call = recommendation
                    max_call_score = score
                elif option_type == "put" and score > max_put_score:
                    best_put = recommendation
                    max_put_score = score

        def print_option(label, data):
            if not data:
                print(f"  No suitable {label} option found.")
                return
            symbol, expiry, typ, strike, ltp, theo, iv, delta, theta, vega, vol, score, sl, tgt = data
            print(f"\n🟢 Best {label.upper()} Option:")
            print(f"  Symbol: {symbol} | Expiry: {expiry} | Type: {typ} | Strike: {strike}  |  CMP: ₹{ltp}  |  Model: ₹{theo:.2f}")
            print(f"  IV: {iv:.2f}%  |  Δ: {delta:.2f}  |  θ: {theta:.2f}  |  Vega: {vega:.2f}")
            print(f"  Volume: {vol}  |  Success Score: {int(score)}%")
            print(f"  🎯 Target: ₹{tgt}  |  🛑 Stop Loss: ₹{sl}")
            results.append(data)

        print_option("CALL", best_call)
        print_option("PUT", best_put)

    except Exception as e:
        print(f"❌ Failed to process {symbol}: {e}")


# ✅ Symbols to analyze
symbols = ["NIFTY", "BANKNIFTY"]
for symbol in symbols:
    get_best_option(symbol)

# 🏆 Final Recommendation based on trend
if results:
    print("\n🏁 Final Trend-Based Recommendation:")
    final_candidates = []
    for res in results:
        symbol, _, typ, *_ = res
        trend = trend_map.get(symbol, "sideways")
        if trend == "up" and typ == "CALL":
            final_candidates.append(res)
        elif trend == "down" and typ == "PUT":
            final_candidates.append(res)
        elif trend == "sideways":
            final_candidates.append(res)  # allow both in sideways

    if final_candidates:
        best = max(final_candidates, key=lambda x: x[11])  # score
        symbol, expiry, typ, strike, ltp, theo, iv, delta, theta, vega, vol, score, sl, tgt = best
        print(f"\n🏆 Best Overall Recommendation ({trend_map[symbol].upper()} Trend):")
        print(f"  Symbol: {symbol} | Expiry: {expiry} | Type: {typ} | Strike: {strike}  |  CMP: ₹{ltp}  |  Model: ₹{theo:.2f}")
        print(f"  IV: {iv:.2f}%  |  Δ: {delta:.2f}  |  θ: {theta:.2f}  |  Vega: {vega:.2f}")
        print(f"  Volume: {vol}  |  Success Score: {int(score)}%")
        print(f"  🎯 Target: ₹{tgt}  |  🛑 Stop Loss: ₹{sl}")

        telegram_message = (
            f"\n🏆 Best Overall Recommendation ({trend_map[symbol].upper()} Trend):"
            f"\n  Symbol: {symbol} | Expiry: {expiry} | Type: {typ} | Strike: {strike}  |  CMP: ₹{ltp}  |  Model: ₹{theo:.2f}"
            f"\n IV: {iv:.2f}%  |  Δ: {delta:.2f}  |  θ: {theta:.2f}  |  Vega: {vega:.2f}"
            f"\n  Volume: {vol}  |  Success Score: {int(score)}%"
            f"\n  🎯 Target: ₹{tgt}  |  🛑 Stop Loss: ₹{sl}"
        )

        crypto_telegram_bot.send_message_telegram(telegram_message)
    else:
        print("❌ No final recommendation matched the market trend.")
else:
    print("❌ No option data available.")
