import os
import tempfile
import pandas as pd
import streamlit as st
from groq import Groq

# --- 1. หน้าตาอินเทอร์เฟซ (Streamlit UI) ---
st.set_page_config(page_title="CXM Internal AI Search", page_icon="🔍", layout="wide")
st.title("🔍 CXM Knowledge AI Search - Coway Thailand")
st.caption("ระบบค้นหาข้อมูลและตอบคำถามภายในแผนก Customer Experience Management")

# ดึง API Key จาก Secrets ถ้ามี หรือรับจาก Sidebar
api_key_secret = st.secrets.get("GROQ_API_KEY", "")

with st.sidebar:
    st.header("⚙️ การตั้งค่าระบบ")
    if api_key_secret:
        groq_api_key = api_key_secret
        st.success("🔑 เชื่อมต่อ Groq API Key กลางเรียบร้อยแล้ว")
    else:
        groq_api_key = st.text_input("กรอก Groq API Key (ขึ้นต้นด้วย gsk_...):", type="password")
        
    uploaded_files = st.file_uploader(
        "อัปโหลดไฟล์คู่มือ / เอกสาร (PDF, Word, Excel):",
        type=["pdf", "docx", "xlsx", "csv"],
        accept_multiple_files=True
    )

# --- 2. ฟังก์ชันแปลงไฟล์เป็นเนื้อหาข้อความ ---
def extract_text_from_files(files):
    combined_text = ""
    for uploaded_file in files:
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        combined_text += f"\n--- เริ่มต้นเอกสาร: {uploaded_file.name} ---\n"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        try:
            if file_ext in [".xlsx", ".csv"]:
                df = pd.read_excel(tmp_path) if file_ext == ".xlsx" else pd.read_csv(tmp_path)
                for index, row in df.iterrows():
                    row_str = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                    combined_text += f"แถวที่ {index + 1}: {row_str}\n"

            elif file_ext == ".pdf":
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(tmp_path)
                docs = loader.load()
                for doc in docs:
                    combined_text += doc.page_content + "\n"

            elif file_ext == ".docx":
                from langchain_community.document_loaders import Docx2txtLoader
                loader = Docx2txtLoader(tmp_path)
                docs = loader.load()
                for doc in docs:
                    combined_text += doc.page_content + "\n"
        except Exception as e:
            combined_text += f"ไม่สามารถอ่านไฟล์นี้ได้: {e}\n"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
        combined_text += f"--- จบเอกสาร: {uploaded_file.name} ---\n\n"
    return combined_text

# --- 3. ประมวลผลและตอบคำถามด้วย Groq ---
if uploaded_files and groq_api_key:
    clean_key = groq_api_key.strip()

    try:
        client = Groq(api_key=clean_key)
        
        if "context_data" not in st.session_state or st.sidebar.button("🔄 อัปเดต/โหลดไฟล์ใหม่"):
            with st.spinner("กำลังอ่านและประมวลผลเอกสารทั้งหมด..."):
                st.session_state.context_data = extract_text_from_files(uploaded_files)
            st.sidebar.success("อ่านเอกสารสำเร็จพร้อมใช้งาน!")

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
                with st.spinner("กำลังวิเคราะห์ข้อมูลและหาคำตอบ..."):
                    prompt = f"""คุณคือผู้ช่วย AI ประจำแผนก Customer Experience Management (CXM) ของบริษัท Coway Thailand
โปรดใช้ข้อมูลบริบทด้านล่างนี้ตอบคำถามของผู้ใช้อย่างสุภาพ สรุปใจความสำคัญเป็นข้อๆ และแม่นยำ
หากไม่มีข้อมูลตอบในบริบท ให้แจ้งตรงๆ ว่า 'ไม่พบข้อมูลดังกล่าวในเอกสารที่อัปโหลด' ห้ามคาดเดาข้อมูลเอง

บริบทข้อมูลจากเอกสารทั้งหมด:
{st.session_state.context_data}

คำถามจากผู้ใช้:
{user_query}
"""
                    answer = None
                    last_err = None

                    try:
                        models_data = client.models.list()
                        active_models = [m.id for m in models_data.data if m.id and "whisper" not in m.id and "guard" not in m.id]
                    except Exception:
                        active_models = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]

                    for model_name in active_models:
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
    st.info("👈 โปรดอัปโหลดไฟล์เอกสารที่เมนูด้านซ้ายเพื่อเริ่มต้นใช้งาน")