import streamlit as st
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.llms.openai import OpenAI
import os
import json
import re
import uuid
from datetime import datetime, timedelta

# === OpenAI 設定 ===
os.environ["OPENAI_API_KEY"] = "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"
llm = OpenAI(model="gpt-3.5-turbo", temperature=0.5, system_prompt="你是一位客服 AI，請使用繁體中文回答所有問題。")
Settings.llm = llm

# === Calendar 檔案 ===
calendar_file = "calendar.json"

def load_calendar():
    if os.path.exists(calendar_file):
        with open(calendar_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_calendar(data):
    with open(calendar_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

calendar = load_calendar()

# === 套餐資料 ===
wash_options = {
    "標準洗": {
        "轎車/旅行車": {"price": 1500, "time": 60},
        "小休旅/休旅車": {"price": 2000, "time": 90},
        "商務車": {"price": 2500, "time": 90},
        "特殊車": {"price": "來電報價", "time": 120}
    },
    "精緻洗": {
        "轎車/旅行車": {"price": 2000, "time": 90},
        "小休旅/休旅車": {"price": 2500, "time": 120},
        "商務車": {"price": 3000, "time": 135},
        "特殊車": {"price": "來電報價", "time": 150}
    },
    "高級美容": {
        "轎車/旅行車": {"price": 3000, "time": 135},
        "小休旅/休旅車": {"price": 4000, "time": 180},
        "商務車": {"price": 4500, "time": 185},
        "特殊車": {"price": "來電報價", "time": 210}
    }
}

package_descriptions = {
    "標準洗": "外觀沖洗與擦拭",
    "精緻洗": "外觀沖洗含內裝清潔保養吸塵與輪框清潔",
    "高級美容": "全套服務含銀離子空氣清淨與鍍膜打蠟"
}

# 營業時間
opening_time = datetime.strptime("08:00", "%H:%M").time()
closing_time = datetime.strptime("20:00", "%H:%M").time()

# === LlamaIndex 知識庫 ===
@st.cache_resource
def load_index():
    documents = SimpleDirectoryReader(input_dir="data", encoding="utf-8", errors="ignore").load_data()
    return VectorStoreIndex.from_documents(documents)

index = load_index()
query_engine = index.as_query_engine(response_mode="compact")

# === 預約處理 ===
def handle_booking(text):
    # 查詢特定訂單
    if "查" in text and "訂單" in text:
        match = re.search(r"(\w{8}-\w{4}-\w{4}-\w{4}-\w{12})", text)
        if match:
            order_id = match.group(1)
            for t, record in calendar.items():
                if record.get("訂單號") == order_id:
                    return (
                        f"📋 訂單號：{order_id}\n🕒 時間：{t}\n🚗 車型：{record['車型']}\n🧼 套餐：{record['套餐']}"
                    )
            return "❌ 查無此訂單號碼。"

    if "查" in text and "預約" in text:
        if not calendar:
            return "目前尚無任何預約紀錄。"
        return "目前預約如下：\n" + "\n".join(
            [f"{k}：{v['車型']} / {v['套餐']}（訂單號碼：{v['訂單號']}）" for k, v in sorted(calendar.items())]
        )

    if "取消" in text:
        match = re.search(r"取消.*?(\w{8}-\w{4}-\w{4}-\w{4}-\w{12})", text)
        if match:
            order_id = match.group(1)
            for time_str, record in list(calendar.items()):
                if record.get("訂單號") == order_id:
                    del calendar[time_str]
                    save_calendar(calendar)
                    return f"✅ 已成功取消預約（訂單號：{order_id}）。"
            return "❌ 找不到此訂單號碼。"
        return "請提供要取消的訂單號碼。"

    if "方案" in text or "服務" in text:
        return "洗車方案如下：\n" + "\n".join([f"{k}：{v}" for k, v in package_descriptions.items()])

    # 時間標準化
    text = text.replace("今天", datetime.now().strftime("%Y-%m-%d"))
    text = text.replace("明天", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))

    # 預約語句解析
    pattern = r"(?:我要預約洗車)?\s*(\d{4}-\d{2}-\d{2})\s*(?:下午)?\s*(\d{1,2}):?(\d{2})?.*?(轎車/旅行車|小休旅/休旅車|商務車|特殊車).*?(標準洗|精緻洗|高級美容)?"
    match = re.search(pattern, text)
    if match:
        date, hour, minute, car_type, package = match.groups()
        hour = int(hour)
        minute = int(minute or 0)
        package = package or "標準洗"
        time_str = f"{date} {hour:02}:{minute:02}"
        requested_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")

        info = wash_options.get(package, {}).get(car_type)
        if not info:
            return "⚠️ 找不到車型或方案。"

        duration = info['time']
        price = info['price']
        req_end = requested_time + timedelta(minutes=duration)

        if requested_time.time() < opening_time:
            return "❌ 該時段尚未開始營業，營業時間為 08:00 - 20:00"
        if req_end.time() > closing_time:
            return f"❌ 此項目需約 {duration} 分鐘，無法在 20:00 打烊前完成，請提早安排。"

        for t_str, record in calendar.items():
            exist_start = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            exist_info = wash_options.get(record['套餐'], {}).get(record['車型'])
            if not exist_info:
                continue
            exist_end = exist_start + timedelta(minutes=exist_info['time'])
            if requested_time < exist_end and req_end > exist_start:
                return f"❌ 該時段已有預約（{t_str}），請改約其他時間。"

        order_id = str(uuid.uuid4())
        calendar[time_str] = {"車型": car_type, "套餐": package, "訂單號": order_id}
        save_calendar(calendar)
        return (
            f"✅ 已預約 {time_str}\n"
            f"🚗 車型：{car_type}，🧼 套餐：{package}\n"
            f"💰 價格：{price}，🕒 預估時間：約 {duration} 分鐘\n"
            f"📌 訂單號碼：{order_id}"
        )

    return "請提供完整預約資訊（例如：預約 2025-06-01 14:00 商務車 高級美容）"

# === Streamlit UI ===
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

st.title("🧽 洗香香 專業汽車美容客服 AI")
st.markdown("請輸入問題，例如：")
st.markdown("""
- 我要預約洗車 2025-06-01 10:30 小休旅/休旅車 高級美容
- 查一下目前的預約
- 查詢訂單 你的訂單號
- 取消預約 你的訂單號
""")
st.image("https://i.imgur.com/OcxLqTv.png", caption="價目表", width=500)

user_input = st.text_input("你問：")
if user_input:
    booking_response = handle_booking(user_input)
    if booking_response:
        answer = booking_response
    else:
        try:
            response = query_engine.query(user_input)
            answer = str(response.response).strip()
        except Exception as e:
            answer = f"⚠️ 無法處理查詢內容：{e}"

    st.session_state.chat_history.append(("你", user_input))
    st.session_state.chat_history.append(("客服 AI", answer))

for sender, message in st.session_state.chat_history:
    color = "#ffe6e6" if sender == "你" else "#fff8dc"
    label = "🙋‍♂️ 你：" if sender == "你" else "🤖 客服 AI："
    st.markdown(
        f"""
        <div style='background-color:{color}; padding:10px; border-radius:10px; margin-bottom:10px;'>
            <strong>{label}</strong><br>{message}
        </div>
        """, unsafe_allow_html=True
    )
