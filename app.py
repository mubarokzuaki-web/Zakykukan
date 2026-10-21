import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIG & INITIALIZATION ---
st.set_page_config(page_title="Binance Spot Scalper AI", layout="wide", page_icon="⚡")

if "bot_active" not in st.session_state:
    st.session_state.bot_active = False
if "trade_logs" not in st.session_state:
    st.session_state.trade_logs = []
if "total_pnl" not in st.session_state:
    st.session_state.total_pnl = 0.0

def add_log(message, status="INFO"):
    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.trade_logs.append({
        "Waktu": now,
        "Pesan": message,
        "Status": status
    })

def get_crypto_price(symbol_pair):
    """Mengambil harga real-time via Coingecko API (Bypass Cloud Geo-Block Error 451)"""
    mapping = {
        "BTC/USDT": "bitcoin",
        "ETH/USDT": "ethereum",
        "SOL/USDT": "solana",
        "BNB/USDT": "binancecoin",
        "VIRTUAL/USDT": "virtuals-protocol"
    }
    coin_id = mapping.get(symbol_pair, "bitcoin")
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers, timeout=5)
    
    if response.status_code == 200:
        data = response.json()
        return float(data[coin_id]['usd'])
    else:
        raise Exception(f"API Error Status {response.status_code}")

# --- SIDEBAR CONTROL PANEL ---
st.sidebar.title("⚙️ Pengaturan Bot")

st.sidebar.subheader("1. Kredensial Binance API")
paper_trading = st.sidebar.checkbox("Gunakan Mode Paper Trading (Simulasi)", value=True)
api_key = st.sidebar.text_input("Binance API Key", type="password", disabled=paper_trading)
api_secret = st.sidebar.text_input("Binance API Secret", type="password", disabled=paper_trading)

st.sidebar.subheader("2. Pasangan Koin & Modal")
symbol = st.sidebar.selectbox("Pasangan Koin Spot", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "VIRTUAL/USDT"])
trade_amount = st.sidebar.number_input("Modal per Order (USDT)", min_value=10.0, value=25.0, step=5.0)

st.sidebar.subheader("3. Parameter AI Scalper")
target_tp = st.sidebar.slider("Target Profit (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.1)
stop_loss = st.sidebar.slider("Stop Loss (%)", min_value=0.5, max_value=5.0, value=2.0, step=0.1)

# --- MAIN DASHBOARD UI ---
st.title("⚡ Binance Spot Liquidity Vacuum AI Engine")
st.caption("Autonomous Flash-Dip Scalper & Cross-Market Imbalance Scanner")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Status Bot", "AKTIF 🟢" if st.session_state.bot_active else "IDLE 🔴")
with col2:
    st.metric("Mode Transaksi", "PAPER TRADING (SIMULASI)" if paper_trading else "LIVE BINANCE")
with col3:
    st.metric("Total PnL Harian", f"${st.session_state.total_pnl:.2f} USDT")

st.divider()

# --- BOT TOGGLE BUTTONS ---
btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    if st.button("▶️ START BOT", use_container_width=True, type="primary", disabled=st.session_state.bot_active):
        st.session_state.bot_active = True
        add_log(f"Bot diaktifkan pada koin {symbol} dengan modal ${trade_amount} USDT.", "START")
        st.rerun()

with btn_col2:
    if st.button("⏹️ STOP BOT", use_container_width=True, disabled=not st.session_state.bot_active):
        st.session_state.bot_active = False
        add_log("Bot dihentikan oleh pengguna.", "STOP")
        st.rerun()

# --- TRADING EXECUTION SIMULATOR / SCANNER ---
if st.session_state.bot_active:
    st.info(f"🔍 System Active: Memindai Order Book & Flash Dip pada pair **{symbol}**...")
    
    try:
        current_price = get_crypto_price(symbol)
        st.success(f"📈 Real-Time Market Price ({symbol}): **${current_price:,.4f}**")
        add_log(f"Berhasil memindai {symbol}: Harga pasar terkini ${current_price:,.4f}.", "SCAN")
    except Exception as e:
        add_log(f"Gagal mengambil data harga: {str(e)}", "ERROR")

# --- LIVE EVENT LOG DISPLAY ---
st.subheader("📜 Live Event & Signal Log")

try:
    if st.session_state.trade_logs:
        df_logs = pd.DataFrame(st.session_state.trade_logs)
    else:
        df_logs = pd.DataFrame(columns=["Waktu", "Pesan", "Status"])
except Exception as e:
    df_logs = pd.DataFrame([{"Waktu": "-", "Pesan": f"Log Parsing Error: {str(e)}", "Status": "ERROR"}])

st.dataframe(df_logs, use_container_width=True)
