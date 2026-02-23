import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import base64
import json

# --- ページ設定 ---
st.set_page_config(page_title="Portfolio Migration Analyzer", layout="wide")

# --- ユーティリティ関数 ---
def decode_base64_to_json(b64_str):
    try:
        padding = '=' * (4 - len(b64_str) % 4)
        json_str = base64.b64decode(b64_str + padding).decode('utf-8')
        return json.loads(json_str)
    except Exception:
        return None

def encode_json_to_base64(data_dict):
    json_str = json.dumps(data_dict)
    return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

def get_portfolio_tickers(config):
    if not config or "assets" not in config:
        return []
    return [asset["ticker"] for asset in config["assets"]]

# --- 1. URLパラメータからの読み込みと初期値設定 ---
default_b64_before = "eyJ0b3RhbF9pbnZlc3RtZW50IjogMTAwMDAuMCwgInJpc2tfZnJlZV9yYXRlIjogMC4wLCAicmViYWxhbmNlX2ZyZXEiOiAiV2Vla2x5IiwgInN0YXJ0X2RhdGUiOiAiMjAyNS0wMi0yMyIsICJhc3NldHMiOiBbeyJ0aWNrZXIiOiAiU1BZIiwgInR5cGUiOiAiTG9uZyIsICJhbGxvY2F0aW9uX3BjdCI6IDUwLjAsICJtYXJnaW5fcmF0aW8iOiAxMDAuMH0sIHsidGlja2VyIjogIlRMVCIsICJ0eXBlIjogIkxvbmciLCAiYWxsb2NhdGlvbl9wY3QiOiAzMC4wLCAibWFyZ2luX3JhdGlvIjogMTAwLjB9XX0="
default_b64_after = "eyJ0b3RhbF9pbnZlc3RtZW50IjogMTAwMDAuMCwgInJpc2tfZnJlZV9yYXRlIjogMC4wLCAicmViYWxhbmNlX2ZyZXEiOiAiV2Vla2x5IiwgInN0YXJ0X2RhdGUiOiAiMjAyNS0wMi0yMyIsICJhc3NldHMiOiBbeyJ0aWNrZXIiOiAiUVFRIiwgInR5cGUiOiAiTG9uZyIsICJhbGxvY2F0aW9uX3BjdCI6IDcwLjAsICJtYXJnaW5fcmF0aW8iOiAxMDAuMH0sIHsidGlja2VyIjogIkdMRCIsICJ0eXBlIjogIkxvbmciLCAiYWxsb2NhdGlvbl9wY3QiOiAzMC4wLCAibWFyZ2luX3JhdGlvIjogMTAwLjB9XX0="

init_values = {
    "before": default_b64_before,
    "after": default_b64_after,
    "window": 120,
    "z_threshold": 1.0
}

query_params = st.query_params
if "config" in query_params:
    decoded_config = decode_base64_to_json(query_params["config"])
    if decoded_config:
        init_values.update(decoded_config)
        st.toast("URLから設定を読み込みました！", icon="✅")

st.title("🔄 ポートフォリオ移行タイミング判定 (Z-Score)")

# --- 2. サイドバー設定 ---
with st.sidebar:
    st.header("⚙️ 設定")
    window = st.slider("分析期間 (移動平均日数)", 50, 300, value=int(init_values["window"]))
    z_threshold = st.slider("移行判断しきい値 (Zスコア)", 0.5, 3.0, value=float(init_values["z_threshold"]), step=0.1)
    
    st.markdown("---")
    b64_before_input = st.text_area("Before ポートフォリオ (Base64)", value=init_values["before"], height=100)
    b64_after_input = st.text_area("After ポートフォリオ (Base64)", value=init_values["after"], height=100)

    st.markdown("---")
    if st.button("現在の構成をURLに保存"):
        current_config = {
            "before": b64_before_input,
            "after": b64_after_input,
            "window": window,
            "z_threshold": z_threshold
        }
        b64_url_param = encode_json_to_base64(current_config)
        st.query_params["config"] = b64_url_param
        st.success("URLに保存しました。ブラウザのアドレスバーをコピーしてください。")

config_before = decode_base64_to_json(b64_before_input)
config_after = decode_base64_to_json(b64_after_input)

if not config_before or not config_after:
    st.error("Base64データのデコードに失敗しました。正しい形式か確認してください。")
    st.stop()

# --- 3. データ取得とポートフォリオ指数の計算 ---
all_tickers = list(set(get_portfolio_tickers(config_before) + get_portfolio_tickers(config_after)))

@st.cache_data(ttl=3600)
def fetch_data(tickers):
    data = yf.download(tickers, period="2y", auto_adjust=True)['Close'].ffill().dropna()
    return data

try:
    with st.spinner('市場データを取得中...'):
        price_df = fetch_data(all_tickers)

    def calc_portfolio_index(price_df, config):
        ret_df = price_df.pct_change().fillna(0)
        portfolio_ret = pd.Series(0.0, index=price_df.index)
        
        for asset in config["assets"]:
            ticker = asset["ticker"]
            weight = asset["allocation_pct"] / 100.0
            
            # 空売りの判定（Shortの場合はリターンを反転させる）
            if asset.get("type", "Long").lower() == "short":
                weight = -abs(weight)
            else:
                weight = abs(weight)

            if isinstance(ret_df, pd.DataFrame) and ticker in ret_df.columns:
                portfolio_ret += ret_df[ticker] * weight
            else:
                portfolio_ret += ret_df * weight
                
        portfolio_index = (1 + portfolio_ret).cumprod()
        return portfolio_index

    # 指数計算
    df_results = pd.DataFrame(index=price_df.index)
    df_results['Before_Index'] = calc_portfolio_index(price_df, config_before)
    df_results['After_Index'] = calc_portfolio_index(price_df, config_after)

    # 移行判定ロジック (Z-Score)
    df_results['Log_Ratio'] = np.log(df_results['After_Index'] / df_results['Before_Index'])
    df_results['Mean'] = df_results['Log_Ratio'].rolling(window=window).mean()
    df_results['Std'] = df_results['Log_Ratio'].rolling(window=window).std()
    df_results['Z_Score'] = (df_results['Log_Ratio'] - df_results['Mean']) / df_results['Std']

    valid_data = df_results.dropna()
    latest = valid_data.iloc[-1]
    prev = valid_data.iloc[-2]
    current_z = latest['Z_Score']

    # --- 4. メイン表示 ---
    st.subheader("📊 分析結果")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.metric("現在のZスコア", f"{current_z:.2f}", delta=f"{current_z - prev['Z_Score']:.2f}", delta_color="inverse")
        st.caption("マイナスが大きいほど『After』が相対的に割安")

    with c2:
        if current_z < -z_threshold:
            status, color, instruction = "✅ 移行推奨 (今すぐ)", "green", "Afterが相対的に割安です。移行の好機です。"
        elif current_z > z_threshold:
            status, color, instruction = "⚠️ 待機 (移行非推奨)", "red", "Afterが相対的に割高です。Before維持を推奨。"
        else:
            status, color, instruction = "☕ ニュートラル", "gray", "統計的な大きな乖離はありません。"
        
        st.markdown(f"### 判定: :{color}[{status}]")
        st.write(instruction)

    with c3:
        with st.expander("構成銘柄を確認"):
            st.write("**Before:**", ", ".join(get_portfolio_tickers(config_before)))
            st.write("**After:**", ", ".join(get_portfolio_tickers(config_after)))

    # --- ポートフォリオ構成の比較テーブル ---
    st.markdown("---")
    st.subheader("📋 ポートフォリオ構成の比較")
    
    def prepare_display_df(config):
        df = pd.DataFrame(config["assets"])
        if "type" in df.columns:
            df["display_pct"] = df.apply(
                lambda x: -abs(x["allocation_pct"]) if str(x["type"]).lower() == "short" else abs(x["allocation_pct"]), 
                axis=1
            )
        else:
            df["display_pct"] = df["allocation_pct"]
            
        res_df = df[["ticker", "display_pct"]].copy()
        res_df.columns = ["銘柄", "配分 (%)"]
        return res_df.set_index("銘柄")

    col_table1, col_table2 = st.columns(2)
    with col_table1:
        st.markdown("**【Before】現在の構成**")
        st.table(prepare_display_df(config_before))
    with col_table2:
        st.markdown("**【After】目標の構成**")
        st.table(prepare_display_df(config_after))

    # チャート表示
    st.markdown("---")
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("価格指数の比較 (基準日=1.0)")
        fig_price = go.Figure()
        fig_price.add_trace(go.Scatter(x=valid_data.index, y=valid_data['Before_Index'], name='Before', line=dict(color='gray')))
        fig_price.add_trace(go.Scatter(x=valid_data.index, y=valid_data['After_Index'], name='After', line=dict(color='blue')))
        fig_price.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=-0.2, yanchor="top", x=0.5, xanchor="center"))
        st.plotly_chart(fig_price, use_container_width=True)

    with col_chart2:
        st.subheader("移行タイミング指標 (Z-Score)")
        fig_z = go.Figure()
        fig_z.add_trace(go.Scatter(x=valid_data.index, y=valid_data['Z_Score'], name='Z-Score', fill='tozeroy'))
        fig_z.add_hline(y=-z_threshold, line_dash="dash", line_color="green", annotation_text="割安")
        fig_z.add_hline(y=z_threshold, line_dash="dash", line_color="red", annotation_text="割高")
        fig_z.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_z, use_container_width=True)

except Exception as e:
    st.error(f"分析中にエラーが発生しました: {e}")

# --- 5. 実践！移行実行＆コストシミュレーター ---
st.markdown("---")
st.header("🧮 移行実行シミュレーター")

col_s1, col_s2, col_s3, col_s4 = st.columns(4)
with col_s1:
    current_value = st.number_input("現在の運用総額 (USD)", value=float(config_before.get("total_investment", 10000.0)), step=1000.0)
with col_s2:
    unrealized_gain = st.number_input("うち含み益 (USD)", value=2000.0, step=500.0)
with col_s3:
    tax_rate = st.number_input("譲渡益税率 (%)", value=20.315, step=1.0) / 100.0
with col_s4:
    fee_rate = st.number_input("売買手数料率 (%)", value=0.5, step=0.1) / 100.0

if st.button("移行後の目標保有額を計算", type="primary"):
    tax_cost = max(0, unrealized_gain) * tax_rate
    fee_cost = current_value * fee_rate
    net_value = current_value - tax_cost - fee_cost
    
    st.markdown("### 💰 資金の推移")
    c_res1, c_res2, c_res3 = st.columns(3)
    c_res1.metric("移行前 総資産", f"${current_value:,.2f}")
    c_res2.metric("移行コスト", f"-${(tax_cost + fee_cost):,.2f}", delta_color="inverse")
    c_res3.metric("再投資可能額", f"${net_value:,.2f}")
    
    st.markdown("### 🎯 移行後の目標買付額")
    calc_cols = st.columns(len(config_after["assets"]))
    for i, asset in enumerate(config_after["assets"]):
        target_amt = net_value * (asset["allocation_pct"] / 100.0)
        with calc_cols[i]:
            st.success(f"**{asset['ticker']}**")
            st.write(f"買付額: **${target_amt:,.2f}**")
