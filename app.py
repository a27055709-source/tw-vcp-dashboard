import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime
import json
import os
import base64

st.set_page_config(
    page_title="VCP 即時看盤與突破監控",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- 檔案與音效設定 -----------------
CONFIG_FILE = "vcp_config.json"
SOUND_FILE = "xopen.mp3"  # 世紀帝國突破音效檔

# ----------------- 檔案儲存與讀取函式 -----------------
def load_config():
    default_cfg = {
        "symbols_str": "2330, 2454, 3037, 6488, 2308, 2379, 3234, 3581, 6274",
        "grid_option": "9 檔 (3x3)",
        "alert_prices": {},
        "refresh_sec": 5,
        "lookback_days": 50
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
        except Exception:
            pass
    return default_cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def get_audio_base64(file_path):
    """將本地音檔轉為 Base64 字串，確保在瀏覽器與雲端皆能順利播放"""
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            data = f.read()
        ext = file_path.split(".")[-1].lower()
        mime = "audio/wav" if ext == "wav" else "audio/mpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return None

# ----------------- 初始化狀態 -----------------
if "config" not in st.session_state:
    st.session_state.config = load_config()

if "triggered_alerts" not in st.session_state:
    st.session_state.triggered_alerts = set()

cfg = st.session_state.config

# ----------------- 側邊欄配置 -----------------
st.sidebar.title("🎯 VCP 監控配置")

grid_options_list = ["1 檔 (1x1)", "4 檔 (2x2)", "9 檔 (3x3)", "16 檔 (4x4)"]
current_grid_idx = grid_options_list.index(cfg["grid_option"]) if cfg["grid_option"] in grid_options_list else 2

grid_option = st.sidebar.selectbox(
    "視窗排版佈局",
    options=grid_options_list,
    index=current_grid_idx
)

grid_mapping = {
    "1 檔 (1x1)": {"cols": 1, "max_stocks": 1, "height": 520},
    "4 檔 (2x2)": {"cols": 2, "max_stocks": 4, "height": 380},
    "9 檔 (3x3)": {"cols": 3, "max_stocks": 9, "height": 300},
    "16 檔 (4x4)": {"cols": 4, "max_stocks": 16, "height": 230}
}
current_grid = grid_mapping[grid_option]

user_input = st.sidebar.text_area(
    "VCP 觀察清單（代號以逗號分隔）",
    value=cfg.get("symbols_str", ""),
    height=80
)
all_symbols = [c.strip() for c in user_input.replace("\n", ",").split(",") if c.strip()]
active_symbols = all_symbols[:current_grid["max_stocks"]]

# 突破價位設定
st.sidebar.subheader("🔔 向上突破關鍵點位")
temp_alert_prices = {}
for sym in active_symbols:
    default_price = float(cfg.get("alert_prices", {}).get(sym, 0.0))
    val = st.sidebar.number_input(
        f"{sym} 關鍵價 (0為不啟用)",
        min_value=0.0,
        value=default_price,
        step=0.5,
        format="%.2f",
        key=f"target_{sym}"
    )
    temp_alert_prices[sym] = val

# 儲存與重設按鈕
c_btn1, c_btn2 = st.sidebar.columns(2)
with c_btn1:
    if st.button("💾 儲存目前設定", use_container_width=True):
        new_config = {
            "symbols_str": user_input,
            "grid_option": grid_option,
            "alert_prices": temp_alert_prices,
            "refresh_sec": cfg.get("refresh_sec", 5),
            "lookback_days": cfg.get("lookback_days", 50)
        }
        if save_config(new_config):
            st.session_state.config = new_config
            st.sidebar.success("✅ 設定已永久儲存！")
with c_btn2:
    if st.button("🔄 重設已觸發警報", use_container_width=True):
        st.session_state.triggered_alerts.clear()
        st.sidebar.info("警報狀態已清空！")

# 試聽音效按鈕
if st.sidebar.button("🔊 試聽通知與測試推播", use_container_width=True):
    st.session_state.test_alert = True
else:
    st.session_state.test_alert = False

refresh_sec = st.sidebar.selectbox("即時更新頻率", options=[3, 5, 10, 30], index=1, format_func=lambda x: f"{x} 秒")
lookback_days = st.sidebar.slider("日 K 顯示長度", min_value=30, max_value=90, value=cfg.get("lookback_days", 50))

# ----------------- 通知與音效觸發組件 -----------------
def trigger_alert_system(alert_items):
    msg_list = [f"{item['symbol']} 向上突破 {item['target']:.2f} (現價: {item['price']:.2f})" for item in alert_items]
    alert_text = "\\n".join(msg_list)

    audio_data_url = get_audio_base64(SOUND_FILE)

    if audio_data_url:
        # 播放指定的 xopen.mp3 音效
        audio_js = f"""
        const audio = new Audio("{audio_data_url}");
        audio.volume = 0.95;
        audio.play().catch(e => console.log("Audio blocked:", e));
        """
    else:
        # 備援機制：若找不到 xopen.mp3 檔案，使用預設合成雙音階嗶聲
        audio_js = """
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        function playTone(freq, delay, duration) {
            setTimeout(() => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(freq, ctx.currentTime);
                gain.gain.setValueAtTime(0.3, ctx.currentTime);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + duration);
            }, delay);
        }
        playTone(587.33, 0, 0.15);
        playTone(880.00, 160, 0.3);
        """

    js_code = f"""
    <script>
    try {{
        {audio_js}
    }} catch(e) {{
        console.log("Audio play error:", e);
    }}

    if (window.Notification) {{
        if (Notification.permission === "granted") {{
            new Notification("🚀 VCP 向上突破警報！", {{
                body: "{alert_text}",
                icon: "https://img.icons8.com/color/96/bullish.png"
            }});
        }} else if (Notification.permission !== "denied") {{
            Notification.requestPermission().then(permission => {{
                if (permission === "granted") {{
                    new Notification("🚀 VCP 向上突破警報！", {{ body: "{alert_text}" }});
                }}
            }});
        }}
    }}
    </script>
    """
    components.html(js_code, height=0, width=0)

if st.session_state.test_alert:
    trigger_alert_system([{"symbol": "測試突破", "target": 100.0, "price": 105.0}])
    st.toast("🔊 正在播放 xopen.mp3 測試音效！", icon="⚔️")

# ----------------- 資料抓取核心 -----------------
@st.cache_data(ttl=86400)
def resolve_ticker_suffix(symbol: str):
    for suffix in [".TW", ".TWO"]:
        t = yf.Ticker(f"{symbol}{suffix}")
        hist = t.history(period="3d")
        if not hist.empty:
            return f"{symbol}{suffix}"
    return None

@st.cache_data(ttl=300)
def get_historical_daily(ticker_str: str):
    stock = yf.Ticker(ticker_str)
    df = stock.history(period="8mo", interval="1d")
    if not df.empty:
        df.index = df.index.tz_localize(None).floor("D")
    return df

def fetch_live_vcp_data(symbol: str, lookback: int):
    ticker_str = resolve_ticker_suffix(symbol)
    if not ticker_str:
        return None

    daily = get_historical_daily(ticker_str)
    if daily is None or daily.empty:
        return None
    
    daily = daily.copy()
    stock = yf.Ticker(ticker_str)

    try:
        intraday = stock.history(period="1d", interval="1m")
    except Exception:
        intraday = pd.DataFrame()

    if not intraday.empty:
        live_open = intraday["Open"].iloc[0]
        live_high = intraday["High"].max()
        live_low = intraday["Low"].min()
        live_close = intraday["Close"].iloc[-1]
        live_vol = intraday["Volume"].sum()
        today_date = intraday.index[-1].tz_localize(None).floor("D")

        if daily.index[-1] == today_date:
            daily.loc[daily.index[-1], ["Open", "High", "Low", "Close", "Volume"]] = [
                live_open, live_high, live_low, live_close, live_vol
            ]
        else:
            live_row = pd.DataFrame([{
                "Open": live_open, "High": live_high, "Low": live_low,
                "Close": live_close, "Volume": live_vol
            }], index=[today_date])
            daily = pd.concat([daily, live_row])

    daily["MA10"] = daily["Close"].rolling(10).mean()
    daily["MA20"] = daily["Close"].rolling(20).mean()
    daily["MA50"] = daily["Close"].rolling(50).mean()
    daily["Vol_MA20"] = daily["Volume"].rolling(20).mean()

    chart_df = daily.tail(lookback).copy()
    prev_close = daily["Close"].iloc[-2] if len(daily) >= 2 else chart_df["Close"].iloc[0]
    curr_price = chart_df["Close"].iloc[-1]

    return {
        "symbol": symbol,
        "df": chart_df,
        "curr_price": curr_price,
        "prev_close": prev_close,
        "change": curr_price - prev_close,
        "pct_change": ((curr_price - prev_close) / prev_close) * 100,
        "today_vol": int(chart_df["Volume"].iloc[-1])
    }

# ----------------- Plotly 繪圖模組 -----------------
def create_vcp_candlestick(data, target_price: float, chart_height: int):
    df = data["df"]
    date_strings = df.index.strftime("%m/%d").tolist()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.78, 0.22]
    )

    fig.add_trace(go.Candlestick(
        x=date_strings,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        increasing_line_color="#eb4d4b", increasing_fillcolor="#eb4d4b",
        decreasing_line_color="#2ecc71", decreasing_fillcolor="#2ecc71",
        name="日K"
    ), row=1, col=1)

    for col_name, color in [("MA10", "#f1c40f"), ("MA20", "#e67e22"), ("MA50", "#3498db")]:
        fig.add_trace(go.Scatter(
            x=date_strings, y=df[col_name],
            mode="lines", line=dict(color=color, width=1.1), name=col_name
        ), row=1, col=1)

    if target_price > 0:
        fig.add_hline(
            y=target_price,
            line_dash="dash",
            line_color="#f39c12",
            line_width=1.5,
            annotation_text=f"突破 {target_price}",
            annotation_position="top right",
            annotation_font=dict(color="#f39c12", size=10),
            row=1, col=1
        )

    vol_colors = ["#eb4d4b" if c >= o else "#2ecc71" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(
        x=date_strings, y=df["Volume"],
        marker_color=vol_colors, showlegend=False, name="量"
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=date_strings, y=df["Vol_MA20"],
        mode="lines", line=dict(color="#9b59b6", width=1.1), name="20MA量"
    ), row=2, col=1)

    fig.update_layout(
        height=chart_height,
        margin=dict(l=5, r=35, t=5, b=5),
        xaxis=dict(type="category", rangeslider=dict(visible=False), showgrid=False),
        xaxis2=dict(type="category", showgrid=False),
        yaxis=dict(side="right", showgrid=True, gridcolor="#2c3e5020", tickfont=dict(size=9)),
        yaxis2=dict(side="right", showgrid=True, gridcolor="#2c3e5020", tickfont=dict(size=8)),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font=dict(size=9)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

# ----------------- 主監控畫面 (局部定時刷新) -----------------
@st.fragment(run_every=refresh_sec)
def render_dashboard():
    now_str = datetime.now().strftime("%H:%M:%S")
    st.caption(f"⚡ 即時連線中：{now_str} (每 {refresh_sec} 秒跳動 | 顯示 {len(active_symbols)} 檔)")

    if not active_symbols:
        st.info("請在側邊欄輸入股票代號。")
        return

    num_cols = current_grid["cols"]
    cols = st.columns(num_cols)
    new_alerts = []

    for idx, sym in enumerate(active_symbols):
        col = cols[idx % num_cols]
        target_p = temp_alert_prices.get(sym, 0.0)

        with col:
            with st.container(border=True):
                data = fetch_live_vcp_data(sym, lookback_days)
                if not data:
                    st.warning(f"代號 {sym} 讀取中...")
                    continue

                curr_p = data["curr_price"]
                sign = "+" if data["change"] > 0 else ""

                if target_p > 0:
                    if curr_p >= target_p and sym not in st.session_state.triggered_alerts:
                        st.session_state.triggered_alerts.add(sym)
                        new_alerts.append({"symbol": sym, "target": target_p, "price": curr_p})

                c1, c2 = st.columns([1, 1])
                with c1:
                    alert_status = " 🚀" if sym in st.session_state.triggered_alerts else ""
                    st.markdown(f"**{sym}**{alert_status}")
                with c2:
                    st.metric(
                        label="現價",
                        value=f"{curr_p:.2f}",
                        delta=f"{sign}{data['change']:.2f} ({sign}{data['pct_change']:.2f}%)",
                        delta_color="normal"
                    )

                fig = create_vcp_candlestick(data, target_p, current_grid["height"])
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if new_alerts:
        trigger_alert_system(new_alerts)
        for a in new_alerts:
            st.toast(f"🚀 {a['symbol']} 向上突破關鍵價 {a['target']:.2f}！現價 {a['price']:.2f}", icon="⚔️")

render_dashboard()