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

# --- 2. ฟังก์ชันโหลดและค้นหาข้อมูลอัจฉริยะ ---
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

def build_smart_context(query, max_chars=12000):
    query_lower = query.lower()
    # สร้างคีย์เวิร์ดค้นหาและเทียบคำ เช่น เดือน 9 = sep = september
    keywords = set([w for w in query_lower.split() if len(w) > 1])
    if "9" in query_lower or "เดือน 9" in query_lower or "กันยายน" in query_lower or "sep" in query_lower:
        keywords.update(["sep", "september", "09", "/9/", "-09-", "กันยายน", "ก.ย."])

    matched_lines = []
    general_lines = []

    # 1. อ่านไฟล์ Excel / CSV ในระบบทุกไฟล์และทุก Sheet
    all_paths = get_all_file_paths()
    for path in all_paths:
        file_name = os.path.basename(path)
        file_ext = os.path.splitext(file_name)[1].lower()

        try:
            if file_ext in [".xlsx", ".csv"]:
                xls = pd.ExcelFile(path) if file_ext == ".xlsx" else None
                sheet_names = xls.sheet_names if xls else ["Sheet1"]

                for sheet in sheet_names:
                    df = pd.read_excel(path, sheet_name=sheet) if xls else pd.read_csv(path)
                    for idx, row in df.iterrows():
                        row_values = [str(val) for val in row.values if pd.notna(val)]
                        if not row_values:
                            continue
                        row_str = f"[{file_name} | {sheet} | แถวที่ {idx+1}]: " + " | ".join(row_values)
                        row_str_lower = row_str.lower()

                        # ตรวจจับว่าตรงกับคีย์เวิร์ดหรือไม่
                        if any(kw in row_str_lower for kw in keywords):
                            matched_lines.append(row_str)
                        elif len(general_lines) < 100:
                            general_lines.append(row_str)

            elif file_ext in [".pdf", ".docx"]:
                loader = PyPDFLoader(path) if file_ext == ".pdf" else Docx2txtLoader(path)
                docs = loader.load()
                for doc in docs:
                    for line in doc.page_content.split("\n"):
                        if line.strip():
                            line_str = f"[{file_name}]: {line.strip()}"
                            if any(kw in line_str.lower() for kw in keywords):
                                matched_lines.append(line_str)
                            elif len(general_lines) < 50:
                                general_lines.append(line_str)
        except Exception:
            pass

    # 2. อ่านไฟล์อัปโหลดเพิ่มชั่วคราว (ถ้ามี)
    if uploaded_files:
        import tempfile
        for u_file in uploaded_files:
            f_ext = os.path.splitext(u_file.name)[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=f_ext) as tmp:
                tmp.write(u_file.getvalue())
                tmp_p = tmp.name

            try:
                if f_ext in [".xlsx", ".csv"]:
                    xls = pd.ExcelFile(tmp_p) if f_ext == ".xlsx" else None
                    sheet_names = xls.sheet_names if xls else ["Sheet1"]
                    for sheet in sheet_names:
                        df = pd.read_excel(tmp_p, sheet_name=sheet) if xls else pd.read_csv(tmp_p)
                        for idx, row in df.iterrows():
                            row_values = [str(val) for val in row.values if pd.notna(val)]
                            if row_values:
                                row_str = f"[อัปโหลด: {u_file.name} | {sheet} | แถวที่ {idx+1}]: " + " | ".join(row_values)
                                if any(kw in row_str.lower() for kw in keywords):
                                    matched_lines.append(row_str)
                                else:
                                    general_lines.append(row_str)
            except Exception:
                pass
            finally:
                if os.path.exists(tmp_p):
                    os.remove(tmp_p)

    # รวมตรงประเด็นก่อน ถ้ายังมีพื้นที่เหลือค่อยเอาข้อมูลทั่วไปใส่
    final_lines = matched_lines + general_lines
    final_text = "\n".join(final_lines)
    return final_text[:max_chars]

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
                with st.spinner("กำลังสแกนและค้นหาข้อมูลในเอกสารทั้งหมด..."):
                    context_data = build_smart_context(user_query, max_chars=12000)

                    prompt = f"""คุณคือผู้ช่วย AI ประจำแผนก Customer Experience Management (CXM) ของบริษัท Coway Thailand
โปรดใช้ข้อมูลบริบทด้านล่างนี้ตอบคำถามของผู้ใช้อย่างสุภาพ สรุปตัวเลขหรือใจความสำคัญเป็นข้อๆ และแม่นยำ
หากมีข้อมูลการนับ ให้ทำการสรุปยอดรวมจำนวนเคส/สายบริการให้ชัดเจน
หากไม่มีข้อมูลตอบในบริบท ให้แจ้งตรงๆ ว่า 'ไม่พบข้อมูลดังกล่าวในเอกสาร' ห้ามคาดเดาข้อมูลเอง

บริบทข้อมูลที่สแกนพบจากเอกสาร:
{context_data}

คำถามจากผู้ใช้:
{user_query}
"""
                    answer = None
                    last_err = None

                    # ลิสต์โมเดลมาตรฐานที่พร้อมทำงาน
                    candidate_models = [
                        "llama-3.1-8b-instant",
                        "llama-3.3-70b-versatile",
                        "groq/compound"
                    ]

                    for model_name in candidate_models:
                        try:
                            chat_completion = client.chat.completions.create(
                                messages=[
                                    {"role": "system", "content": "คุณคือผู้ช่วย AI ของ Coway Thailand ตอบเป็นภาษาไทยอย่างแม่นยำและสรุปตัวเลขได้ถูกต้อง"},
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