import streamlit as st
import pandas as pd
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from sentence_transformers import SentenceTransformer, util
import uuid
import time
import sqlite3

# --- 1. Ρυθμίσεις ---
st.set_page_config(page_title="Uni Helpdesk Pro", page_icon="🏛️", layout="wide")

@st.cache_resource
def load_model():
    return SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

try:
    with st.spinner('Εκκίνηση Συστήματος...'):
        model = load_model()
except: st.stop()

# Αρχεία
FILES_PATH = {'db': 'helpdesk.db', 'knowledge': 'knowledge.xlsx'}

# --- 2. Ρύθμιση Email (Secrets ή Test) ---
if 'email' in st.secrets:
    SMTP_SERVER = st.secrets["email"]["smtp_server"]
    SMTP_PORT = st.secrets["email"]["smtp_port"]
    SMTP_EMAIL = st.secrets["email"]["address"]
    SMTP_PASSWORD = st.secrets["email"]["password"]
else:
    # Ρυθμίσεις για τοπική δοκιμή (αν δεν υπάρχουν secrets)
    SMTP_SERVER = "smtp.upatras.gr"
    SMTP_EMAIL = "test@upatras.gr"
    SMTP_PASSWORD = "test"

# --- 3. Database Functions (SQLite) ---
def init_db():
    conn = sqlite3.connect(FILES_PATH['db'])
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            date TEXT,
            category TEXT,
            role TEXT,
            name TEXT,
            email TEXT,
            issue TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_all_tickets():
    conn = sqlite3.connect(FILES_PATH['db'])
    df = pd.read_sql_query("SELECT * FROM tickets", conn)
    conn.close()
    return df

def add_ticket(category, role, name, email, issue):
    ticket_id = str(uuid.uuid4())[:4].upper()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    conn = sqlite3.connect(FILES_PATH['db'])
    c = conn.cursor()
    c.execute('''
        INSERT INTO tickets (id, date, category, role, name, email, issue, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ticket_id, current_time, category, role, name, email, issue, 'Υπό Επεξεργασία'))
    conn.commit()
    conn.close()
    return ticket_id

def update_tickets_batch(edited_df):
    conn = sqlite3.connect(FILES_PATH['db'])
    c = conn.cursor()
    data_to_update = []
    for index, row in edited_df.iterrows():
        data_to_update.append((row['status'], row['category'], row['id']))
    
    c.executemany('UPDATE tickets SET status = ?, category = ? WHERE id = ?', data_to_update)
    conn.commit()
    conn.close()

# --- 4. Logic & AI ---
def load_knowledge():
    if not os.path.exists(FILES_PATH['knowledge']):
        pd.DataFrame({"Question": ["Παράδειγμα"], "Answer": ["Απάντηση"]}).to_excel(FILES_PATH['knowledge'], index=False)
    
    try:
        df_kb = pd.read_excel(FILES_PATH['knowledge'])
        clean_kb = df_kb.dropna()
        if not clean_kb.empty:
            embeddings = model.encode(clean_kb['Question'].tolist(), convert_to_tensor=True)
        else:
            embeddings = None
        return df_kb, embeddings
    except:
        return None, None

# Αρχικοποίηση
init_db()
df_kb, kb_embeddings = load_knowledge()

def find_answer_ai(user_question):
    if df_kb is None or kb_embeddings is None: return None
    user_embedding = model.encode(user_question, convert_to_tensor=True)
    scores = util.cos_sim(user_embedding, kb_embeddings)[0]
    if float(scores.max()) > 0.60:
        return df_kb.iloc[int(scores.argmax())]['Answer']
    return None

def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP(SMTP_SERVER, 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except:
        return False

# --- 5. UI ---
st.title("🏛️ Ηλεκτρονική Γραμματεία")

tab1, tab2, tab3 = st.tabs(["💬 Εξυπηρέτηση", "🔍 Παρακολούθηση", "🔐 Γραφείο"])

# --- TAB 1: ΝΕΑ ΑΙΤΗΣΗ ---
with tab1:
    col1, col2 = st.columns(2)
    role = col1.selectbox("Ιδιότητα:", ["Φοιτητής", "Άλλο"])
    cat = col2.selectbox("Θέμα:", ["Βεβαιώσεις", "Εγγραφές", "Γενικά"])
    q = st.text_input("Ερώτηση:", placeholder="Π.χ. πότε ορκιζόμαστε;")
    
    if q:
        ans = find_answer_ai(q)
        if ans: st.success(f"🤖 {ans}")
        else: st.info("Δεν βρέθηκε απάντηση. Παρακαλώ κάντε αίτηση.")

    with st.expander("📝 Νέα Αίτηση", expanded=(q != "")):
        with st.form("req"):
            name = st.text_input("Ονοματεπώνυμο")
            email = st.text_input("Email")
            desc = st.text_area("Λεπτομέρειες", value=q)
            if st.form_submit_button("Υποβολή") and name and email:
                tid = add_ticket(cat, role, name, email, desc)
                
                # Αποστολή Email
                subject = f"Αίτημα: {tid}"
                body = f"Γεια σας {name},\nΟ κωδικός αιτήματός σας είναι: {tid}"
                ok = send_email(email, subject, body)
                
                st.success(f"Εστάλη! Κωδικός: {tid}")
                if not ok: st.warning("Το email επιβεβαίωσης ίσως δεν εστάλη (ελέγξτε ρυθμίσεις).")

# --- TAB 2: TRACKER ---
with tab2:
    tid = st.text_input("Κωδικός Αίτησης:")
    if st.button("Αναζήτηση"):
        conn = sqlite3.connect(FILES_PATH['db'])
        res = pd.read_sql_query("SELECT date, category, status FROM tickets WHERE id = ?", conn, params=(tid.strip().upper(),))
        conn.close()
        
        if not res.empty:
            status = res.iloc[0]['status']
            st.info(f"📅 {res.iloc[0]['date']} | 📂 {res.iloc[0]['category']}")
            if status == "Έτοιμο":
                st.balloons()
                st.success(f"✅ Κατάσταση: {status}")
            else:
                st.warning(f"⏳ Κατάσταση: {status}")
        else:
            st.error("Δεν βρέθηκε.")

# --- TAB 3: ADMIN (ΑΥΣΤΗΡΟ) ---
with tab3:
    pwd = st.text_input("Κωδικός Προσωπικού", type="password")
    
    # 1. Παίρνουμε τον κωδικό ΜΟΝΟ από τα Secrets
    if 'admin_password' in st.secrets:
        admin_pass = st.secrets["admin_password"]
    else:
        # Αν δεν βρεθούν secrets (π.χ. τοπικά χωρίς αρχείο), 
        # βάζουμε έναν κωδικό που δεν μπορεί να μαντέψει κανείς.
        # Έτσι το "admin123" σταματάει να δουλεύει.
        admin_pass = "X@_NO_ACCESS_WITHOUT_SECRETS_@X"
    # ---------------------------------

    if pwd == admin_pass:
        df_tickets = get_all_tickets()
        
        st.markdown("---")
        pending = len(df_tickets[df_tickets['status'] == 'Υπό Επεξεργασία'])
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("🔴 Εκκρεμείς", pending)
        kpi2.metric("✅ Σύνολο", len(df_tickets))
        
        st.write("### 🗂️ Διαχείριση")
        show_all = st.checkbox("Προβολή Ολοκληρωμένων", value=False)
        
        if show_all: edit_df = df_tickets
        else: edit_df = df_tickets[df_tickets['status'] == 'Υπό Επεξεργασία']
            
        edited_data = st.data_editor(
            edit_df,
            key="editor",
            column_config={
                "status": st.column_config.SelectboxColumn("Κατάσταση", options=["Υπό Επεξεργασία", "Έτοιμο", "Απορρίφθηκε"], required=True),
                "id": st.column_config.TextColumn(disabled=True)
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("💾 Αποθήκευση"):
            try:
                update_tickets_batch(edited_data)
                st.success("✅ Ενημερώθηκε!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
