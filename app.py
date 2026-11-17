import streamlit as st
import ccxt
import pandas as pd
import time
import threading
import os
from datetime import datetime

st.set_page_config(page_title="My AI Trading Bot", page_icon="📈", layout="centered")

# جلب المفاتيح من إعدادات السيرفر الآمنة (Secrets / Env Variables)
API_KEY = os.getenv("BINANCE_API_KEY", "")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

# حالة البوت المشتركة بين الخلفية والواجهة
if "bot_state" not in st.session_state:
    st.session_state.bot_state = {
        "running": False,
        "status": "في انتظار التشغيل...",
        "current_price": 0.0,
        "in_position": False,
        "buy_price": 0.0,
        "target_price": 0.0,
        "stop_price": 0.0,
        "capital_usdt": 10.0,  # يعادل ~100 درهم
        "total_profit_usdt": 0.0,
        "history": []
    }

state = st.session_state.bot_state

def run_trading_bot(api_key, secret_key, bot_data):
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret_key,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    exchange.set_sandbox_mode(True)  # وضع التجريب Testnet
    symbol = 'BTC/USDT'

    while bot_data["running"]:
        try:
            bot_data["status"] = "يراقب السوق ويحلل الفرص 🔍"
            bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # حساب المؤشرات وتحديد الأهداف تلقائياً
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            df['rsi'] = 100 - (100 / (1 + (gain / loss)))

            volatility = (df['high'].iloc[-1] - df['low'].iloc[-1]) / df['close'].iloc[-1]
            tp_pct = max(0.008, min(0.02, volatility * 1.5))  # ربح تلقائي بين 0.8% و 2%
            sl_pct = tp_pct * 0.6                             # حماية تلقائية

            price = float(df['close'].iloc[-1])
            ema20 = float(df['ema20'].iloc[-1])
            rsi = float(df['rsi'].iloc[-1])
            bot_data["current_price"] = price

            # قرار الشراء
            if not bot_data["in_position"]:
                if price > ema20 and rsi < 48:
                    amount = round(bot_data["capital_usdt"] / price, 5)
                    exchange.create_market_buy_order(symbol, amount)
                    bot_data["buy_price"] = price
                    bot_data["target_price"] = round(price * (1 + tp_pct), 2)
                    bot_data["stop_price"] = round(price * (1 - sl_pct), 2)
                    bot_data["in_position"] = True
                    bot_data["status"] = "داخل صفقة شراء 🟢"
                    bot_data["history"].insert(0, {
                        "الوقت": datetime.now().strftime("%H:%M:%S"),
                        "العملية": "BUY 🟢",
                        "الثمن ($)": price,
                        "الربح (DH)": 0.0
                    })

            # قرار البيع (جني الأرباح أو وقف الخسارة)
            else:
                if price >= bot_data["target_price"] or price <= bot_data["stop_price"]:
                    amount = round(bot_data["capital_usdt"] / bot_data["buy_price"], 5)
                    exchange.create_market_sell_order(symbol, amount)
                    pnl_usdt = (price - bot_data["buy_price"]) * amount
                    pnl_dh = round(pnl_usdt * 10, 2)
                    bot_data["total_profit_usdt"] += pnl_usdt
                    bot_data["capital_usdt"] += pnl_usdt
                    bot_data["in_position"] = False
                    label = "SELL (ربح ✅)" if pnl_usdt > 0 else "SELL (حماية 🛡️)"
                    bot_data["history"].insert(0, {
                        "الوقت": datetime.now().strftime("%H:%M:%S"),
                        "العملية": label,
                        "الثمن ($)": price,
                        "الربح (DH)": pnl_dh
                    })

            time.sleep(20)  # فحص السوق كل 20 ثانية
        except Exception as e:
            bot_data["status"] = f"تنبيه تقني: {str(e)[:60]}"
            time.sleep(15)

# --- واجهة لوحة التحكم (Dashboard) ---
st.title("🤖 لوحة تحكم البوت الأوتوماتيكي")

# تشغيل البوت تلقائياً إذا كانت المفاتيح موجودة
if API_KEY and SECRET_KEY and not state["running"]:
    state["running"] = True
    thread = threading.Thread(target=run_trading_bot, args=(API_KEY, SECRET_KEY, state), daemon=True)
    thread.start()

st.info(f"**حالة البوت:** {state['status']}")

col1, col2, col3 = st.columns(3)
capital_dh = round(state["capital_usdt"] * 10, 2)
profit_dh = round(state["total_profit_usdt"] * 10, 2)

col1.metric("الرصيد الحالي", f"{capital_dh} DH", f"{profit_dh} DH")
col2.metric("سعر البيتكوين الآن", f"{state['current_price']}$")
col3.metric("الوضعية", "شاري 🟢" if state["in_position"] else "ينتظر ⏳")

if state["in_position"]:
    st.success(f"🎯 **ثمن الشراء:** {state['buy_price']}$ | **هدف البيع:** {state['target_price']}$ | **وقف الخسارة:** {state['stop_price']}$")

st.subheader("📜 سجل الصفقات والأرباح")
if state["history"]:
    st.dataframe(pd.DataFrame(state["history"]), use_container_width=True)
else:
    st.write("البوت يراقب السوق حالياً، ستظهر الصفقات هنا بمجرد التنفيذ.")

if st.button("🔄 تحديث البيانات الآن"):
    st.rerun()
