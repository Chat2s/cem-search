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

# --- 2. ฟังก์ชันวิเคราะห์และนับจำนวนด้วย Pandas (ส่งเฉพาะสรุปสถิติตัวเลขให้ AI) ---
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

def analyze_and_summarize(query):
    """ คำนวณยอดและสรุปสถิติด้วย Pandas ให้เสร็จเรียบร้อยก่อนส่งให้ AI เพื่อป้องกัน Token เกิน Limit """
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
                    summary_text += f"\n📁 **ไฟล์: {file_name} (แผ่นงาน: {sheet})** - รวมทั้งหมด {total_rows:,} รายการ\n"

                    # แปลงข้อมูลคอลัมน์ทั้งหมดเป็นสตริงเพื่อสแกนหา pattern
                    df_str = df.astype(str)

                    # 1. นับเคสเดือน 9 (Sep/September/09/ก.ย./กันยายน)
                    m9_mask = df_str.apply(lambda col: col.str.contains('09-202|/09/|-09-|sep|september|กันยายน|ก.ย.', case=False, na=False)).any(axis=1)
                    count_m9 = m9_mask.sum()
                    summary_text += f"- เคสในเดือน 9 (กันยายน / Sep / 09): **{count_m9:,} เคส**\n"

                    # 2. ค้นหาคีย์เวิร์ดเฉพาะคำในคำถาม
                    q_words = [w.strip() for w in query.split() if len(w.strip()) > 1]
                    if q_words:
                        kw_mask = df_str.apply(lambda col: col.str.contains('|'.join(q_words), case=False, na=False)).any(axis=1)
                        count_kw = kw_mask.sum()
                        summary_text += f"- เคสที่ตรงกับคีย์เวิร์ดในคำถาม '{query}': **{count_kw:,} เคส**\n"

                    # 3. แจกแจงประเภท Complaint หรือ Product (ถ้ามีคอลัมน์สถิติ)
                    for col in df.columns:
                        col_lower = str(col).lower()
                        if any(k in col_lower for k in ["type", "product", "category", "status", "ประเภท", "สินค้า"]):
                            top_counts = df[col].value_counts().head(5).to_dict()
                            summary_text += f"  - สรุปยอดตาม `{col}`: {top_counts}\n"

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
                with st.spinner("กำลังคำนวณและประมวลผลยอดสถิติจากทุกไฟล์..."):
                    analytics_summary = analyze_and_summarize(user_query)

                    prompt = f"""คุณคือผู้ช่วย AI ประจำแผนก Customer Experience Management (CXM) ของบริษัท Coway Thailand
โปรดใช้สรุปผลสถิติที่คำนวณจากไฟล์เอกสารด้านล่างนี้ ตอบคำถามของผู้ใช้อย่างเรียบร้อย สุภาพ และชัดเจน
รายงานตัวเลขตามผลสรุปสถิติที่คำนวณมาได้อย่างแม่นยำ 100% ห้ามตอบว่าไม่มีข้อมูลหากมีตัวเลขปรากฏอยู่

สรุปผลสถิติตัวเลขจากระบบ:
{analytics_summary}

คำถามจากผู้ใช้:
{user_query}
"""
                    answer = None
                    last_err = None

                    # ใช้โมเดล llama-3.1-8b-instant ที่รวดเร็วและใช้ Token น้อยที่สุด
                    candidate_models = [
                        "llama-3.1-8b-instant",
                        "llama-3.3-70b-versatile"
                    ]

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