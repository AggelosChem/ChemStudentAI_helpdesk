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

# --- 1. Ρυθμίσεις Εφαρμογής ---
st.set_page_config(page_title="Uni Helpdesk Pro", page_icon="🏛️", layout="wide")

# Φόρτωση AI Μοντέλου (Cached για ταχύτητα)
@st.cache_resource
def load_model():
    return SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

try:
    with st.spinner('Εκκίνηση Συστήματος...'):
        model = load_model()
except: st.stop()

# Διαδρομές Αρχείων
FILES_PATH = {'db': 'helpdesk.db', 'knowledge': 'knowledge.xlsx'}

# --- 2. Ρύθμιση Email (ΜΟΝΟ μέσω Secrets για ασφάλεια) ---
if 'email' in st.secrets:
    SMTP_SERVER = st.secrets["email"]["smtp_server"]
    SMTP_PORT = st.secrets["email"]["smtp_port"]
    SMTP_EMAIL = st.secrets["email"]["address"]
    SMTP_PASSWORD = st.secrets["email"]["password"]
else:
    # Fallback μόνο για safe mode (δεν στέλνει πραγματικά emails αν δεν υπάρχουν secrets)
    SMTP_SERVER = "smtp.upatras.gr"
    SMTP_EMAIL = "test@upatras.gr"
    SMTP_PASSWORD = "test"

# --- 3. Λειτουργίες Βάσης Δεδομένων (SQLite) ---
def init_db():
    """Δημιουργεί τη βάση αν δεν υπάρχει"""
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
    """Φέρνει όλα τα tickets για τον Admin"""
    conn = sqlite3.connect(FILES_PATH['db'])
    df = pd.read_sql_query("SELECT * FROM tickets", conn)
    conn.close()
    return df

def add_ticket(category, role, name, email, issue):
    """Αποθηκεύει νέο ticket"""
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
    """Ενημερώνει μαζικά τα tickets από τον πίνακα του Admin"""
    conn = sqlite3.connect(FILES_PATH['db'])
    c = conn.cursor()
    
    data_to_update = []
    for index, row in edited_df.iterrows():
        # Προσοχή: Η σειρά πρέπει να ταιριάζει με το SQL query παρακάτω
        data_to_update.append((row['status'], row['category'], row['id']))
    
    c.executemany('UPDATE tickets SET status = ?, category = ? WHERE id = ?', data_to_update)
    conn.commit()
    conn.close()

# --- 4. Logic & AI Helpers ---
def load_knowledge():
    # Δημιουργία dummy αρχείου αν δεν υπάρχει
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

# Αρχικοποίηση κατά την εκκίνηση
init_db()
df_kb, kb_embeddings = load_knowledge()

def find_answer_ai(user_question):
    if df_kb is None or kb_embeddings is None: return None
    user_embedding = model.encode(user_question, convert_to_tensor=True)
    scores = util.cos_sim(user_embedding, kb_embeddings)[0]
    if float(scores.max()) > 0.60: # Όριο εμπιστοσύνης AI
        return df_kb.iloc[int(scores.argmax())]['Answer']
    return None

def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        # Προσοχή: Αν δεν υπάρχουν σωστά secrets, αυτό θα αποτύχει σιωπηλά ή θα βγάλει error logs
        if SMTP_PASSWORD == "test": return False 
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# --- 5. User Interface (UI) ---
st.title("🏛️ Ηλεκτρονική Γραμματεία")

tab1, tab2, tab3 = st.tabs(["💬 Εξυπηρέτηση Φοιτητών", "🔍 Παρακολούθηση Αιτήματος", "🔐 Γραφείο Γραμματείας"])

# --- TAB 1: ΝΕΑ ΑΙΤΗΣΗ & AI ---
with tab1:
    col1, col2 = st.columns(2)
    role = col1.selectbox("Ιδιότητα:", ["Φοιτητής", "Άλλο"])
    cat = col2.selectbox("Θέμα:", ["Βεβαιώσεις", "Εγγραφές", "Γενικά"])
    q = st.text_input("Ερώτηση:", placeholder="Π.χ. πότε ορκιζόμαστε;")
    
    # AI Απάντηση
    if q:
        ans = find_answer_ai(q)
        if ans: 
            st.success(f"🤖 Αυτόματη Απάντηση: {ans}")
        else: 
            st.info("Δεν βρέθηκε απάντηση στη βάση γνώσης. Παρακαλώ προχωρήστε σε αίτηση.")

    # Φόρμα Αίτησης
    with st.expander("📝 Υποβολή Νέας Αίτησης", expanded=(q != "")):
        with st.form("req"):
            name = st.text_input("Ονοματεπώνυμο")
            email = st.text_input("Email (Πανεπιστημίου)")
            desc = st.text_area("Λεπτομέρειες Αιτήματος", value=q)
            
            if st.form_submit_button("Υποβολή Αίτησης") and name and email:
                # 1. Αποθήκευση στη Βάση
                tid = add_ticket(cat, role, name, email, desc)
                
                # 2. Αποστολή Email
                subject = f"Επιβεβαίωση Αιτήματος: {tid}"
                body = f"Γεια σας {name},\n\nΤο αίτημά σας καταχωρήθηκε επιτυχώς.\nΚωδικός Παρακολούθησης: {tid}\n\nΘα ενημερωθείτε μόλις ολοκληρωθεί.\n\nΓραμματεία Τμήματος"
                email_sent = send_email(email, subject, body)
                
                # 3. Ενημέρωση Χρήστη
                st.success(f"Η αίτηση εστάλη! Ο κωδικός σας είναι: {tid}")
                if not email_sent:
                    st.warning("⚠️ Η αίτηση καταγράφηκε, αλλά δεν εστάλη email επιβεβαίωσης (ελέγξτε τα Secrets).")

# --- TAB 2: TRACKER (Αναζήτηση) ---
with tab2:
    st.write("Εισάγετε τον κωδικό που λάβατε στο email σας.")
    tid = st.text_input("Κωδικός Αίτησης (π.χ. A1B2):")
    
    if st.button("Αναζήτηση Πορείας"):
        conn = sqlite3.connect(FILES_PATH['db'])
        # Ασφαλές Query με παραμέτρους (?)
        res = pd.read_sql_query("SELECT date, category, status FROM tickets WHERE id = ?", conn, params=(tid.strip().upper(),))
        conn.close()
        
        if not res.empty:
            status = res.iloc[0]['status']
            st.info(f"📅 Ημ/νία: {res.iloc[0]['date']} | 📂 Κατηγορία: {res.iloc[0]['category']}")
            
            if status == "Έτοιμο":
                st.balloons()
                st.success(f"✅ Η αίτησή σας είναι ΕΤΟΙΜΗ!")
            elif status == "Απορρίφθηκε":
                st.error(f"❌ Η αίτησή σας απορρίφθηκε. Επικοινωνήστε με τη γραμματεία.")
            else:
                st.warning(f"⏳ Κατάσταση: {status}")
        else:
            st.error("❌ Ο κωδικός δεν βρέθηκε. Ελέγξτε αν τον γράψατε σωστά.")

# --- TAB 3: ADMIN PANEL (Ασφαλές) ---
with tab3:
    pwd = st.text_input("Κωδικός Προσωπικού", type="password")
    
    # --- SECURITY CHECK ---
    # Εδώ γίνεται ο αυστηρός έλεγχος. Αν δεν υπάρχει secret, ο κωδικός είναι αδύνατον να βρεθεί.
    if 'admin_password' in st.secrets:
        admin_pass = st.secrets["admin_password"]
    else:
        # Κωδικός που δεν μπορεί να μαντέψει κανείς, για να κλειδώσει το σύστημα αν λείπουν τα secrets
        admin_pass = "LOCKED_SYSTEM_NO_SECRETS_FOUND_!@#" 
    
    if pwd == admin_pass:
        df_tickets = get_all_tickets()
        
        st.markdown("---")
        # KPIs
        pending_count = len(df_tickets[df_tickets['status'] == 'Υπό Επεξεργασία'])
        
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("🔴 Εκκρεμείς Υποθέσεις", pending_count)
        kpi2.metric("✅ Συνολικά Αιτήματα", len(df_tickets))
        
        st.write("### 🗂️ Πίνακας Διαχείρισης")
        
        # Φίλτρα
        show_all = st.checkbox("Προβολή Ολοκληρωμένων", value=False)
        if show_all:
            edit_df = df_tickets
        else:
            edit_df = df_tickets[df_tickets['status'] == 'Υπό Επεξεργασία']
            
        # Data Editor (Επεξεργάσιμος Πίνακας)
        edited_data = st.data_editor(
            edit_df,
            key="ticket_editor",
            column_config={
                "status": st.column_config.SelectboxColumn(
                    "Κατάσταση",
                    options=["Υπό Επεξεργασία", "Έτοιμο", "Απορρίφθηκε"],
                    required=True,
                    width="medium"
                ),
                "category": st.column_config.SelectboxColumn(
                    "Κατηγορία",
                    options=["Βεβαιώσεις", "Εγγραφές", "Γενικά"],
                    width="medium"
                ),
                "id": st.column_config.TextColumn(disabled=True),
                "date": st.column_config.TextColumn(disabled=True),
            },
            hide_index=True,
            use_container_width=True
        )

        # Κουμπί Αποθήκευσης
        if st.button("💾 Ενημέρωση Βάσης Δεδομένων"):
            try:
                update_tickets_batch(edited_data)
                st.success("✅ Οι αλλαγές αποθηκεύτηκαν επιτυχώς!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Σφάλμα κατά την αποθήκευση: {e}")
    
    elif pwd:
        st.error("Λάθος Κωδικός.")