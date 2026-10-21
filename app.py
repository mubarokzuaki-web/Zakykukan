import streamlit as st
import ccxt
import time
import threading
import pandas as pd
from datetime import datetime

# ==========================================
# KONFIGURASI HALAMAN STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Binance Spot Liquidity Vacuum Bot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# ENGINE TRADING & LOGIKA KETIDAKSEIMBANGAN
# ==========================================
class LiquidityVacuumBot:
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.stop_event = threading.Event()
        
        # Konfigurasi runtime
        self.exchange = None
        self.symbol = "BTC/USDT"
        self.trade_amount_usdt = 20.0
        self.tp_pct = 1.0
        self.sl_pct = 0.8
        self.vacuum_threshold = 0.35  # Imbalance threshold (35% dominasi bid)
        self.paper_trading = True
        
        # State Data
        self.logs = []
        self.pnl_history = []
        self.current_position = None  # Format: {'entry_price': x, 'amount': y, 'symbol': s}
        self.current_price = 0.0
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.imbalance = 0.0
        self.total_pnl = 0.0

    # --- PENGAMAN LOG DATAFRAME ---
try:
    if hasattr(bot, 'logs') and bot.logs:
        df_logs = pd.DataFrame(bot.logs)
    else:
        df_logs = pd.DataFrame(columns=["Waktu", "Pesan", "Status"])
except Exception as e:
    df_logs = pd.DataFrame([{"Waktu": "-", "Pesan": f"Log error: {str(e)}", "Status": "INFO"}])

st.dataframe(df_logs, use_container_width=True)

    def start(self, api_key, api_secret, symbol, amount_usdt, tp, sl, threshold, paper_trading, use_testnet):
        if self.is_running:
            return

        self.symbol = symbol
        self.trade_amount_usdt = amount_usdt
        self.tp_pct = tp
        self.sl_pct = sl
        self.vacuum_threshold = threshold
        self.paper_trading = paper_trading

        # Inisialisasi CCXT Binance
        exchange_config = {
            'apiKey': api_key.strip(),
            'secret': api_secret.strip(),
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        }
        
        try:
            self.exchange = ccxt.binance(exchange_config)
            if use_testnet and not self.paper_trading:
                self.exchange.set_sandbox_mode(True)
                self.add_log("Mode: Binance SPOT TESTNET aktif", "WARNING")
            elif self.paper_trading:
                self.add_log("Mode: PAPER TRADING (Simulasi Tanpa Risiko Saldo)", "SUCCESS")
            else:
                self.add_log("Mode: REAL BINANCE SPOT LIVE TRADING", "WARNING")
        except Exception as e:
            self.add_log(f"Gagal inisialisasi API: {str(e)}", "ERROR")
            return

        self.stop_event.clear()
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.add_log(f"Bot AKTIF memonitor pasangan {self.symbol}")

    def stop(self):
        if not self.is_running:
            return
        self.stop_event.set()
        self.is_running = False
        self.add_log("Perintah STOP diterima. Bot berhenti.", "WARNING")

    def _calculate_order_book_imbalance(self, order_book, depth=10):
        bids = order_book['bids'][:depth]
        asks = order_book['asks'][:depth]
        
        bid_vol = sum(b[1] for b in bids)
        ask_vol = sum(a[1] for a in asks)
        
        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return 0.0
            
        # Rumus Order Book Imbalance: (Bids - Asks) / (Bids + Asks)
        # Nilai berkisar antara -1 (Semua Ask / Jual) sampai +1 (Semua Bid / Beli)
        imbalance = (bid_vol - ask_vol) / total_vol
        return imbalance

    def _run_loop(self):
        while not self.stop_event.is_set():
            try:
                # 1. Ambil Order Book L2
                order_book = self.exchange.fetch_order_book(self.symbol, limit=20)
                if not order_book['bids'] or not order_book['asks']:
                    time.sleep(1)
                    continue

                self.best_bid = order_book['bids'][0][0]
                self.best_ask = order_book['asks'][0][0]
                self.current_price = (self.best_bid + self.best_ask) / 2.0
                
                # 2. Analisis Ketidakseimbangan (Liquidity Vacuum)
                self.imbalance = self._calculate_order_book_imbalance(order_book, depth=10)
                
                # 3. Logika Eksekusi Jika Belum Punya Posisi
                if self.current_position is None:
                    # Trigger Liquidity Vacuum Rebound:
                    # Ketika Bid sangat tebal sementara Ask menipis mendadak (Imbalance > threshold)
                    if self.imbalance >= self.vacuum_threshold:
                        entry_price = self.best_bid
                        qty = self.trade_amount_usdt / entry_price
                        
                        self.add_log(
                            f"⚡ VACUUM DETECTED! Imbalance: {self.imbalance:+.2%}. Membuka Limit Buy di {entry_price:.4f}",
                            "SUCCESS"
                        )
                        
                        if not self.paper_trading:
                            try:
                                order = self.exchange.create_limit_buy_order(self.symbol, qty, entry_price)
                                self.add_log(f"Order Terkirim ID: {order['id']}")
                            except Exception as ex:
                                self.add_log(f"Gagal order Real: {str(ex)}", "ERROR")
                                time.sleep(3)
                                continue

                        # Catat posisi aktif
                        self.current_position = {
                            'entry_price': entry_price,
                            'amount': qty,
                            'symbol': self.symbol,
                            'time': datetime.now().strftime("%H:%M:%S"),
                            'tp_price': entry_price * (1 + (self.tp_pct / 100)),
                            'sl_price': entry_price * (1 - (self.sl_pct / 100))
                        }
                        self.add_log(
                            f"Posisi Dibuka: Qty={qty:.5f} @ {entry_price:.4f} | TP={self.current_position['tp_price']:.4f} | SL={self.current_position['sl_price']:.4f}"
                        )
                
                # 4. Logika Monitoring & Exit Jika Sedang Memegang Posisi
                else:
                    pos = self.current_position
                    entry = pos['entry_price']
                    current = self.current_price
                    qty = pos['amount']
                    gain_pct = ((current - entry) / entry) * 100

                    # Evaluasi Take Profit
                    if current >= pos['tp_price']:
                        pnl_nominal = (current - entry) * qty
                        self.total_pnl += pnl_nominal
                        self.pnl_history.append({"Waktu": datetime.now().strftime("%H:%M:%S"), "P&L (USDT)": pnl_nominal, "Tipe": "TAKE PROFIT"})
                        self.add_log(f"🎯 TAKE PROFIT TERCAPAI di {current:.4f}! Profit: +${pnl_nominal:.2f} ({gain_pct:+.2f}%)", "SUCCESS")
                        
                        if not self.paper_trading:
                            try:
                                self.exchange.create_limit_sell_order(self.symbol, qty, self.best_ask)
                            except Exception as ex:
                                self.add_log(f"Gagal Sell TP: {str(ex)}", "ERROR")

                        self.current_position = None

                    # Evaluasi Stop Loss
                    elif current <= pos['sl_price']:
                        pnl_nominal = (current - entry) * qty
                        self.total_pnl += pnl_nominal
                        self.pnl_history.append({"Waktu": datetime.now().strftime("%H:%M:%S"), "P&L (USDT)": pnl_nominal, "Tipe": "STOP LOSS"})
                        self.add_log(f"🛑 STOP LOSS TERSENTUH di {current:.4f}! Rugi: ${pnl_nominal:.2f} ({gain_pct:+.2f}%)", "ERROR")
                        
                        if not self.paper_trading:
                            try:
                                self.exchange.create_market_sell_order(self.symbol, qty)
                            except Exception as ex:
                                self.add_log(f"Gagal Sell SL: {str(ex)}", "ERROR")

                        self.current_position = None

                # Jeda polling interval agar aman dari batasan rate limit Binance
                time.sleep(1.0)

            except Exception as e:
                self.add_log(f"Kesalahan Loop: {str(e)}", "ERROR")
                time.sleep(2.0)

# ==========================================
# SINGLETON INSTANCE BOT UNTUK STREAMLIT
# ==========================================
@st.cache_resource
def get_bot():
    return LiquidityVacuumBot()

bot = get_bot()

# ==========================================
# SIDEBAR KONTROL & PENGATURAN
# ==========================================
with st.sidebar:
    st.title("⚙️ Pengaturan Bot")
    
    st.subheader("1. Kredensial Binance API")
    mode_simulasi = st.checkbox("Gunakan Mode Paper Trading (Simulasi)", value=True, help="Aktifkan ini untuk testing instan tanpa modal sungguhan")
    use_testnet = st.checkbox("Binance Testnet Mode", value=False, disabled=mode_simulasi)
    
    api_key = st.text_input("Binance API Key", type="password", placeholder="Masukkan API Key jika Live", disabled=mode_simulasi)
    api_secret = st.text_input("Binance API Secret", type="password", placeholder="Masukkan Secret Key jika Live", disabled=mode_simulasi)
    
    st.subheader("2. Pasangan Koin & Modal")
    symbol_pilihan = st.selectbox(
        "Pasangan Koin Spot",
        ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"],
        index=0
    )
    modal_trade = st.number_input("Modal per Order (USDT)", min_value=11.0, max_value=10000.0, value=25.0, step=5.0)

    st.subheader("3. Strategi Liquidity Vacuum")
    vacuum_sensitivitas = st.slider("Ambang Imbalance Order Book", min_value=0.15, max_value=0.70, value=0.35, step=0.05,
                                    help="0.35 berarti volume bid 35% lebih dominan daripada ask pada kedalaman Top 10")
    tp_persen = st.number_input("Target Profit (%)", min_value=0.2, max_value=15.0, value=1.0, step=0.1)
    sl_persen = st.number_input("Stop Loss (%)", min_value=0.2, max_value=10.0, value=0.8, step=0.1)

    st.markdown("---")
    
    # Tombol Kontrol Utama
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        start_pressed = st.button("▶ START BOT", use_container_width=True, type="primary", disabled=bot.is_running)
    with col_btn2:
        stop_pressed = st.button("⏹ STOP BOT", use_container_width=True, disabled=not bot.is_running)

    if start_pressed:
        if not mode_simulasi and (not api_key or not api_secret):
            st.error("Masukkan API Key & Secret untuk mode Real/Testnet!")
        else:
            bot.start(
                api_key=api_key,
                api_secret=api_secret,
                symbol=symbol_pilihan,
                amount_usdt=modal_trade,
                tp=tp_persen,
                sl=sl_persen,
                threshold=vacuum_sensitivitas,
                paper_trading=mode_simulasi,
                use_testnet=use_testnet
            )
            st.rerun()

    if stop_pressed:
        bot.stop()
        st.rerun()

# ==========================================
# DASHBOARD UTAMA
# ==========================================
st.title("⚡ Binance Spot Liquidity Vacuum Bot")
st.caption("Deteksi instan Flash Dip & Ketidakseimbangan Kedalaman Order Book L2 di Pasar Spot")

# Tampilan Status Bar
status_col1, status_col2, status_col3 = st.columns(3)
with status_col1:
    if bot.is_running:
        st.success("🟢 STATUS: BOT RUNNING (ACTIVE)")
    else:
        st.warning("⚪ STATUS: BOT IDLE (STOPPED)")

with status_col2:
    mode_text = "SIMULASI (PAPER TRADING)" if bot.paper_trading else "LIVE BINANCE"
    st.info(f"Mode Operasi: **{mode_text}**")

with status_col3:
    st.info(f"Pasangan: **{bot.symbol}**")

st.markdown("---")

# Metrik Real-Time Order Book & PnL
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.metric("Harga Saat Ini", f"${bot.current_price:,.4f}" if bot.current_price > 0 else "$0.00")

with m2:
    # Tampilkan Imbalance dengan indikator warna
    imb_pct = bot.imbalance * 100
    st.metric(
        "Order Book Imbalance (Top 10)", 
        f"{imb_pct:+.2f}%", 
        delta=f"Target Pemicu: > {bot.vacuum_threshold*100:.0f}%"
    )

with m3:
    spread = (bot.best_ask - bot.best_bid) if bot.best_ask > 0 else 0
    st.metric("Spread Terbaik", f"${spread:,.4f}")

with m4:
    color_pnl = "normal" if bot.total_pnl >= 0 else "inverse"
    st.metric("Total P&L Harian", f"${bot.total_pnl:+,.2f} USDT")

st.markdown("---")

# Area Status Posisi Aktif
st.subheader("📌 Status Posisi Saat Ini")
if bot.current_position:
    pos = bot.current_position
    cur_p = bot.current_price
    pnl_unrealized = ((cur_p - pos['entry_price']) / pos['entry_price']) * 100
    pnl_val = (cur_p - pos['entry_price']) * pos['amount']
    
    pos_c1, pos_c2, pos_c3, pos_c4 = st.columns(4)
    pos_c1.info(f"**Waktu Masuk:** {pos['time']}")
    pos_c2.info(f"**Harga Beli:** ${pos['entry_price']:.4f}")
    pos_c3.info(f"**TP / SL:** ${pos['tp_price']:.4f} / ${pos['sl_price']:.4f}")
    pos_c4.metric("Unrealized P&L", f"${pnl_val:+.2f}", f"{pnl_unrealized:+.2f}%")
else:
    st.write("Tidak ada posisi terbuka. Bot sedang mencari anomali Liquidity Vacuum...")

st.markdown("---")

# Log Transaksi & Sinyal Real-Time
col_log, col_history = st.columns([2, 1])

with col_log:
    st.subheader("📜 Live Event & Signal Log")
    if bot.logs:
        df_logs = pd.DataFrame(bot.logs)
        st.dataframe(df_logs, use_container_width=True, height=260)
    else:
        st.write("Menunggu aktivitas bot...")

with col_history:
    st.subheader("📊 Riwayat Transaksi")
    if bot.pnl_history:
        df_pnl = pd.DataFrame(bot.pnl_history)
        st.dataframe(df_pnl, use_container_width=True, height=260)
    else:
        st.write("Belum ada riwayat transaksi yang ditutup.")

# Auto-refresh UI setiap 2 detik saat bot aktif agar metrik terupdate langsung
if bot.is_running:
    time.sleep(2)
    st.rerun()
