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

# --- 2. ฟังก์ชันวิเคราะห์และนับข้อมูลแบบครอบคลุมทั้งไฟล์ ---
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

def analyze_excel_data(query):
    """ ให้ Pandas วนอ่านทุกแถวจนถึงแถวสุดท้าย และทำการสรุปสถิติให้ AI """
    all_paths = get_all_file_paths()
    context_summary = ""
    
    # รวมไฟล์อัปโหลดชั่วคราวด้วย
    if uploaded_files:
        import tempfile
        for u_file in uploaded_files:
            f_ext = os.path.splitext(u_file.name)[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=f_ext) as tmp:
                tmp.write(u_file.getvalue())
                tmp_p = tmp.name
            if f_ext in [".xlsx", ".csv"]:
                all_paths.append(tmp_p)

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
                    context_summary += f"\n=== สรุปไฟล์ {file_name} (แผ่นงาน: {sheet}) ทั้งหมด {total_rows} รายการ ===\n"
                    
                    # แปลงคอลัมน์ที่เป็นวันที่ให้อยู่ในรูปแบบ datetime เพื่อให้นับตามเดือนได้แม่นยำ
                    date_cols = [col for col in df.columns if any(x in str(col).lower() for x in ["date", "time", "วัน", "เวลา"])]
                    
                    # ค้นหาคำว่า '09', 'sep', 'september' หรือ 'เดือน 9'
                    filtered_df = df[df.astype(str).apply(lambda x: x.str.contains('09-202|sep|september|/09/|-09-', case=False, na=False)).any(axis=1)]
                    sep_count = len(filtered_df)
                    
                    context_summary += f"- จำนวนเคสทั้งหมดในไฟล์: {total_rows} แถว\n"
                    context_summary += f"- สแกนพบเคสที่มีข้อมูลเดือน 9 (Sep/September/09): รวม {sep_count} รายการ\n"
                    
                    # สุ่มตัวอย่าง 20 แถวจากเคสเดือน 9 เพื่อให้ AI เห็นโครงสร้าง
                    if not filtered_df.empty:
                        context_summary += "ตัวอย่างเคสเดือน 9:\n"
                        for idx, row in filtered_df.head(25).iterrows():
                            row_vals = " | ".join([f"{c}: {v}" for c, v in row.items() if pd.notna(v)])
                            context_summary += f"  แถว {idx+1}: {row_vals}\n"

            except Exception as e:
                context_summary += f"ไม่สามารถประมวลผลไฟล์ {file_name} ได้: {e}\n"

    return context_summary

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
                with st.spinner("กำลังสแกนอ่านไฟล์ Excel ครบทุกแถวจนถึงแถวสุดท้าย..."):
                    context_data = analyze_excel_data(user_query)

                    prompt = f"""คุณคือผู้ช่วย AI ประจำแผนก Customer Experience Management (CXM) ของบริษัท Coway Thailand
โปรดใช้ผลสรุปการประมวลผลข้อมูลจากไฟล์ Excel ด้านล่างนี้ ตอบคำถามของผู้ใช้อย่างแม่นยำ
ระบุจำนวนเคสเดือน 9 หรือตัวเลขที่ค้นพบตามผลสรุปสถิติจริง ห้ามตอบว่า 'ไม่มีข้อมูล' หากในผลสรุปมีจำนวนเคสระบุไว้

ผลสรุปสถิติจากการสแกนทุกแถวในเอกสาร:
{context_data}

คำถามจากผู้ใช้:
{user_query}
"""
                    answer = None
                    last_err = None

                    candidate_models = [
                        "llama-3.1-8b-instant",
                        "llama-3.3-70b-versatile",
                        "groq/compound"
                    ]

                    for model_name in candidate_models:
                        try:
                            chat_completion = client.chat.completions.create(
                                messages=[
                                    {"role": "system", "content": "คุณคือผู้ช่วย AI ของ Coway Thailand ตอบเป็นภาษาไทยอย่างแม่นยำตามสถิติที่ได้รับ"},
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