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

# --- 2. ฟังก์ชันดึงเนื้อหาและกรองข้อมูลให้ขนาดพอดี ---
@st.cache_data(show_spinner=False)
def get_all_file_paths():
    supported_extensions = ["*.xlsx", "*.csv", "*.pdf", "*.docx"]
    file_paths = []
    for ext in supported_extensions:
        file_paths.extend(glob.glob(ext))
    return file_paths

file_paths = get_all_file_paths()
system_files = [os.path.basename(p) for p in file_paths]

# แสดงรายชื่อเอกสารบน Sidebar
with st.sidebar:
    st.subheader("📚 เอกสารหลักในระบบ")
    if system_files:
        for f in system_files:
            st.markdown(f"- 📄 `{f}`")
    else:
        st.warning("ไม่พบไฟล์เอกสารในระบบ")

def extract_relevant_context(query, max_chars=8000):
    """ ค้นหาเฉพาะบรรทัดหรือข้อมูลที่เกี่ยวน้องกับคำถามของผู้ใช้ เพื่อลดขนาดข้อมูลไม่ให้ติด Error 413 """
    query_words = [w.lower() for w in query.split() if len(w) > 1]
    retrieved_text = ""

    # 1. อ่านไฟล์ในระบบ
    all_paths = get_all_file_paths()
    for path in all_paths:
        file_name = os.path.basename(path)
        file_ext = os.path.splitext(file_name)[1].lower()
        retrieved_text += f"\n--- เอกสาร: {file_name} ---\n"

        try:
            if file_ext in [".xlsx", ".csv"]:
                df = pd.read_excel(path) if file_ext == ".xlsx" else pd.read_csv(path)
                match_count = 0
                for index, row in df.iterrows():
                    row_str = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                    
                    # ถ้าเจอคำค้นหา หรือถ้าคำค้นหาสั้นมาก ให้ดึงแถวแรกๆ มาประกอบ
                    if not query_words or any(w in row_str.lower() for w in query_words) or match_count < 30:
                        retrieved_text += f"แถวที่ {index + 1}: {row_str}\n"
                        match_count += 1
                    
                    if len(retrieved_text) >= max_chars:
                        break

            elif file_ext in [".pdf", ".docx"]:
                loader = None
                if file_ext == ".pdf":
                    from langchain_community.document_loaders import PyPDFLoader
                    loader = PyPDFLoader(path)
                else:
                    from langchain_community.document_loaders import Docx2txtLoader
                    loader = Docx2txtLoader(path)
                
                docs = loader.load()
                for doc in docs:
                    lines = doc.page_content.split("\n")
                    for line in lines:
                        if not query_words or any(w in line.lower() for w in query_words):
                            retrieved_text += line + "\n"
                        if len(retrieved_text) >= max_chars:
                            break
        except Exception as e:
            retrieved_text += f"ไม่สามารถอ่านไฟล์ {file_name} ได้: {e}\n"

        if len(retrieved_text) >= max_chars:
            break

    # 2. อ่านไฟล์อัปโหลดเพิ่มชั่วคราว
    if uploaded_files:
        import tempfile
        for u_file in uploaded_files:
            f_ext = os.path.splitext(u_file.name)[1].lower()
            retrieved_text += f"\n--- เอกสารเพิ่มเติม: {u_file.name} ---\n"
            with tempfile.NamedTemporaryFile(delete=False, suffix=f_ext) as tmp:
                tmp.write(u_file.getvalue())
                tmp_p = tmp.name
            
            try:
                if f_ext in [".xlsx", ".csv"]:
                    df = pd.read_excel(tmp_p) if f_ext == ".xlsx" else pd.read_csv(tmp_p)
                    for index, row in df.iterrows():
                        row_str = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                        retrieved_text += f"แถวที่ {index + 1}: {row_str}\n"
                        if len(retrieved_text) >= max_chars:
                            break
            except Exception:
                pass
            finally:
                if os.path.exists(tmp_p):
                    os.remove(tmp_p)

    return retrieved_text[:max_chars]

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
                with st.spinner("กำลังค้นหาข้อมูลและวิเคราะห์คำตอบ..."):
                    
                    # คัดเลือกเฉพาะเนื้อหาที่เกี่ยวข้องและขนาดไม่เกิน API Limit
                    context_data = extract_relevant_context(user_query, max_chars=8000)

                    prompt = f"""คุณคือผู้ช่วย AI ประจำแผนก Customer Experience Management (CXM) ของบริษัท Coway Thailand
โปรดใช้ข้อมูลบริบทด้านล่างนี้ตอบคำถามของผู้ใช้อย่างสุภาพ สรุปใจความสำคัญเป็นข้อๆ และแม่นยำ
หากไม่มีข้อมูลตอบในบริบท ให้แจ้งตรงๆ ว่า 'ไม่พบข้อมูลดังกล่าวในเอกสาร' ห้ามคาดเดาข้อมูลเอง

บริบทข้อมูลที่เกี่ยวข้องจากเอกสาร:
{context_data}

คำถามจากผู้ใช้:
{user_query}
"""
                    answer = None
                    last_err = None

                    # โมเดลของ Groq ที่รองรับข้อความยาวแบบไม่ติด Rate Limit/413
                    candidate_models = [
                        "llama-3.1-8b-instant",
                        "llama-3.3-70b-versatile",
                        "openai/gpt-oss-20b"
                    ]

                    for model_name in candidate_models:
                        try:
                            chat_completion = client.chat.completions.create(
                                messages=[
                                    {"role": "system", "content": "คุณคือผู้ช่วย AI ของ Coway Thailand ตอบเป็นภาษาไทยอย่างแม่นยำ"},
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