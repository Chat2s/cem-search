import os
import glob
import pandas as pd
import streamlit as st
from groq import Groq

# --- 1. หน้าตาอินเทอร์เฟซ (Streamlit UI) ---
st.set_page_config(page_title="CXM Internal AI Search", page_icon="🔍", layout="wide")
st.title("🔍 CXM Knowledge AI Search - Coway Thailand")
st.caption("ระบบค้นหาข้อมูลและตอบคำถามภายในแผนก Customer Experience Management")

# ดึง API Key จาก Secrets
api_key_secret = st.secrets.get("GROQ_API_KEY", "")

with st.sidebar:
    st.header("⚙️ การตั้งค่าระบบ")
    if api_key_secret:
        groq_api_key = api_key_secret
        st.success("🔑 เชื่อมต่อ Groq API Key กลางเรียบร้อยแล้ว")
    else:
        groq_api_key = st.text_input("กรอก Groq API Key (ขึ้นต้นด้วย gsk_...):", type="password")

    uploaded_files = st.file_uploader(
        "อัปโหลดไฟล์เพิ่มชั่วคราว (PDF, Word, Excel):",
        type=["pdf", "docx", "xlsx", "csv"],
        accept_multiple_files=True
    )

# --- 2. ฟังก์ชันนับเคสแบบเป๊ะ 100% (Strict Date & Column Parsing) ---
@st.cache_data(show_spinner=False)
def get_all_file_paths():
    supported_extensions = ["*.xlsx", "*.csv", "*.pdf", "*.docx"]
    file_paths = []
    for ext in supported_extensions:
        file_paths.extend(glob.glob(ext))
    return file_paths

file_paths = get_all_file_paths()
system_files = [os.path.basename(p) for p in file_paths]

with st.sidebar:
    st.subheader("📚 เอกสารหลักในระบบ")
    if system_files:
        for f in system_files:
            st.markdown(f"- 📄 `{f}`")
    else:
        st.warning("ไม่พบไฟล์เอกสารในระบบ")

def analyze_and_summarize_exact(query):
    all_paths = get_all_file_paths()
    
    if uploaded_files:
        import tempfile
        for u_file in uploaded_files:
            f_ext = os.path.splitext(u_file.name)[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=f_ext) as tmp:
                tmp.write(u_file.getvalue())
                tmp_p = tmp.name
            if f_ext in [".xlsx", ".csv"]:
                all_paths.append(tmp_p)

    summary_text = ""

    for path in all_paths:
        file_name = os.path.basename(path)
        file_ext = os.path.splitext(file_name)[1].lower()

        if file_ext in [".xlsx", ".csv"]:
            try:
                xls = pd.ExcelFile(path) if file_ext == ".xlsx" else None
                sheet_names = xls.sheet_names if xls else ["Sheet1"]

                for sheet in sheet_names:
                    df = pd.read_excel(path, sheet_name=sheet) if xls else pd.read_csv(path)
                    total_rows = len(df)
                    summary_text += f"\n📁 **ไฟล์: {file_name} (แผ่นงาน: {sheet})** - รายการทั้งหมด {total_rows:,} แถว\n"

                    # ค้นหาคอลัมน์ที่เป็นวันที่สร้างเคส หรือ วันที่รับเรื่อง
                    date_cols = [c for c in df.columns if any(k in str(c).lower() for k in ["created", "date", "วัน", "เวลา", "time"])]
                    
                    m9_exact_count = 0
                    if date_cols:
                        for col in date_cols:
                            # แปลงคอลัมน์เป็นรูปแบบ Date จริงๆ (ป้องกันการไปนับเบอร์โทร 09x)
                            parsed_dates = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
                            # กรองเฉพาะเคสปี 2026 และ เดือน 9 (กันยายน)
                            m9_matches = parsed_dates[(parsed_dates.dt.month == 9) & (parsed_dates.dt.year == 2026)]
                            count = len(m9_matches)
                            if count > 0:
                                summary_text += f"  - นับจากคอลัมน์ `{col}` (เดือน 9/2026): **{count:,} เคส**\n"
                                m9_exact_count = max(m9_exact_count, count)

                    # กรณีไม่พบคอลัมน์วันที่ หรือนับแบบ Text Matching ป้องกันตกหล่น
                    if m9_exact_count == 0:
                        df_str = df.astype(str)
                        # กรองเฉพาะที่มี Pattern วันที่ เช่น 09-2026 หรือ /09/2026 เท่านั้น (ไม่เอาเบอร์โทร)
                        strict_m9 = df_str.apply(lambda c: c.str.contains('09-2026|/09/2026|2026-09|-09-2026', case=False, na=False)).any(axis=1)
                        summary_text += f"  - นับตาม Date Pattern เดือน 9/2026: **{strict_m9.sum():,} เคส**\n"

            except Exception as e:
                summary_text += f"ไม่สามารถประมวลผลไฟล์ {file_name} ได้: {e}\n"

    return summary_text

# --- 3. ประมวลผลและตอบคำถามด้วย Groq ---
if groq_api_key:
    clean_key = groq_api_key.strip()

    try:
        client = Groq(api_key=clean_key)

        if "messages" not in st.session_state:
            st.session_state.messages = []

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if user_query := st.chat_input("พิมพ์คำถามหรือข้อมูลที่ต้องการค้นหาที่นี่..."):
            st.session_state.messages.append({"role": "user", "content": user_query})
            with st.chat_message("user"):
                st.markdown(user_query)

            with st.chat_message("assistant"):
                with st.spinner("กำลังคำนวณและตรวจสอบวันที่ในคอลัมน์อย่างแม่นยำ..."):
                    analytics_summary = analyze_and_summarize_exact(user_query)

                    prompt = f"""คุณคือผู้ช่วย AI ประจำแผนก Customer Experience Management (CXM) ของบริษัท Coway Thailand
โปรดใช้สรุปผลสถิติตัวเลขที่คำนวณได้จริงจากคอลัมน์วันที่ด้านล่างนี้ ตอบคำถามของผู้ใช้
สรุปตัวเลขตามคอลัมน์วันที่แยกตามไฟล์อย่างแม่นยำ 100% ตรงตามไฟล์ Excel

สรุปสถิติตัวเลขจริงจากคอลัมน์วันที่:
{analytics_summary}

คำถามจากผู้ใช้:
{user_query}
"""
                    answer = None
                    last_err = None

                    try:
                        models_data = client.models.list()
                        active_models = [
                            m.id for m in models_data.data 
                            if m.id and not any(x in m.id.lower() for x in ["whisper", "guard", "orpheus", "vision", "audio", "safeguard"])
                        ]
                    except Exception:
                        active_models = []

                    fallback_models = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "groq/compound"]
                    candidate_models = active_models + [m for m in fallback_models if m not in active_models]

                    for model_name in candidate_models:
                        try:
                            chat_completion = client.chat.completions.create(
                                messages=[
                                    {"role": "system", "content": "คุณคือผู้ช่วย AI ของ Coway Thailand ตอบรายงานสถิติตัวเลขเป็นภาษาไทยอย่างแม่นยำ"},
                                    {"role": "user", "content": prompt}
                                ],
                                model=model_name,
                            )
                            answer = chat_completion.choices[0].message.content
                            if answer:
                                break
                        except Exception as err:
                            last_err = err
                            continue

                    if answer:
                        st.markdown(answer)
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                    else:
                        st.error(f"เกิดข้อผิดพลาดในการเรียกใช้โมเดล: {last_err}")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {e}")

else:
    st.info("👈 โปรดตั้งค่า Groq API Key ใน Secrets เพื่อเริ่มต้นใช้งาน")