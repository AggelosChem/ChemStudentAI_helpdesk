import streamlit as st
import pandas as pd
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from sentence_transformers import SentenceTransformer, util
import torch

# --- 1. Ρυθμίσεις & Cache ---
st.set_page_config(page_title="Smart Helpdesk", page_icon="🧠", layout="centered")

# Φορτώνουμε το AI Μοντέλο ΜΙΑ φορά
@st.cache_resource
def load_model():
    return SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

try:
    with st.spinner('Φόρτωση AI Εγκεφάλου...'):
        model = load_model()
except Exception as e:
    st.error(f"Σφάλμα φόρτωσης μοντέλου: {e}")
    st.stop()

# --- 2. Διαδρομές & Emails ---
FILES_PATH = {'tickets': 'tickets.csv', 'knowledge': 'knowledge.xlsx'}

# Ρυθμίσεις Email
if 'email' in st.secrets:
    SMTP_SERVER = st.secrets["email"]["smtp_server"]
    SMTP_PORT = st.secrets["email"]["smtp_port"]
    SMTP_EMAIL = st.secrets["email"]["address"]
    SMTP_PASSWORD = st.secrets["email"]["password"]
else:
    SMTP_SERVER = "smtp.upatras.gr"
    SMTP_EMAIL = "test@upatras.gr"
    SMTP_PASSWORD = "test"

# --- 3. Λειτουργίες ---

def load_knowledge_base():
    """Φορτώνει το Excel και μετατρέπει τις ερωτήσεις σε Vectors"""
    if not os.path.exists(FILES_PATH['knowledge']):
        data = {
            "Question": ["Πότε γίνονται οι εγγραφές πρωτοετών;", "Πώς παίρνω βεβαίωση σπουδών;", "Ξέχασα τον κωδικό eclass"],
            "Answer": ["1-15 Σεπτεμβρίου στο ministry.gr.", "Από το students.upatras.gr.", "Επικοινωνήστε με το NOC."]
        }
        pd.DataFrame(data).to_excel(FILES_PATH['knowledge'], index=False)
    
    try:
        df = pd.read_excel(FILES_PATH['knowledge'])
        df = df.dropna(subset=['Question', 'Answer'])
        
        if df.empty: return df, None
        
        # Encode questions
        embeddings = model.encode(df['Question'].tolist(), convert_to_tensor=True)
        return df, embeddings
    except Exception as e:
        st.error(f"Error loading Excel: {e}")
        return pd.DataFrame(), None

# Φόρτωση Γνώσης
df_kb, kb_embeddings = load_knowledge_base()

def find_answer_ai(user_question):
    """Semantic Search με έλεγχο Score"""
    if df_kb.empty or kb_embeddings is None: return None
    
    user_embedding = model.encode(user_question, convert_to_tensor=True)
    scores = util.cos_sim(user_embedding, kb_embeddings)[0]
    
    best_score = float(scores.max())
    best_index = int(scores.argmax())
    
    # --- DEBUG PRINT (Δες το στο τερματικό) ---
    matched_q = df_kb.iloc[best_index]['Question']
    print(f"User: {user_question} | Match: {matched_q} | Score: {best_score:.4f}")
    
    # --- THRESHOLD: 0.60 (Αυστηρότητα) ---
    if best_score > 0.60:
        return df_kb.iloc[best_index]['Answer']
    
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

def save_ticket(category, role, name, email, issue):
    new_data = {
        'Date': [datetime.now().strftime("%Y-%m-%d %H:%M")],
        'Category': [category], 'Role': [role], 'Name': [name],
        'Email': [email], 'Issue': [issue], 'Status': ['Open']
    }
    df = pd.DataFrame(new_data)
    if not os.path.exists(FILES_PATH['tickets']): df.to_csv(FILES_PATH['tickets'], index=False)
    else: df.to_csv(FILES_PATH['tickets'], mode='a', header=False, index=False)
    
    subject = f"Αίτημα: {category}"
    body = f"Γεια σας {name},\n\nΤο αίτημά σας καταχωρήθηκε.\n\nΓραμματεία"
    return send_email(email, subject, body)

# --- 4. User Interface ---
try:
    if os.path.exists("logo.png"): st.image("logo.png", width=150)
except: pass

st.title("🧠 Ηλεκτρονική Γραμματεία (AI)")

tab1, tab2 = st.tabs(["💬 Εξυπηρέτηση", "⚙️ Διαχείριση"])

with tab1:
    st.info("ℹ️ Οι φοιτητές ταυτοποιούνται μόνο με @upatras.gr email.")
    
    col1, col2 = st.columns(2)
    with col1:
        role = st.selectbox("1. Ιδιότητα:", ["Φοιτητής/τρια", "Εξωτερικός", "Άλλο"])
    with col2:
        cat = st.selectbox("2. Θέμα:", ["Γενικά", "Βεβαιώσεις", "Εγγραφές", "Βαθμολογίες"])
        
    user_q = st.text_input("3. Πώς μπορώ να βοηθήσω;", placeholder="Περιγράψτε το πρόβλημα...")
    
    # --- ΔΙΟΡΘΩΣΗ CRASH: Αρχικοποίηση μεταβλητής ---
    ans = None 

    if user_q:
        ans = find_answer_ai(user_q)
        
        if ans:
            st.success(f"🤖 **Αυτόματη Απάντηση:** {ans}")
            st.caption("Η απάντηση δόθηκε βάσει νοήματος.")
        else:
            st.warning("Δεν βρήκα απάντηση στη βάση γνώσης.")
            
    # Φόρμα Υποβολής
    with st.expander("📝 Αποστολή Αιτήματος", expanded=(user_q != "")):
        with st.form("ticket_form"):
            st.write(f"**Κατηγορία:** {cat}")
            name = st.text_input("Ονοματεπώνυμο")
            email = st.text_input("Email")
            desc = st.text_area("Λεπτομέρειες", value=user_q)
            
            if st.form_submit_button("Υποβολή"):
                if not (name and email and desc):
                    st.error("Συμπληρώστε όλα τα πεδία.")
                elif role == "Φοιτητής/τρια" and not email.endswith("upatras.gr"):
                    st.error("⛔ Απαιτείται email @upatras.gr")
                else:
                    ok = save_ticket(cat, role, name, email, desc)
                    if ok: st.success("✅ Το αίτημα εστάλη!")
                    else: st.warning("⚠️ Το αίτημα εστάλη (πρόβλημα με email).")

with tab2:
    pwd = st.text_input("Password", type="password")
    if pwd == "admin123":
        if st.button("🔄 Reload Model & Excel"):
            st.cache_resource.clear()
            st.rerun()
            
        st.write("### 🧠 Τι γνωρίζει το AI:")
        if not df_kb.empty:
            st.dataframe(df_kb, use_container_width=True)
            
        if os.path.exists(FILES_PATH['tickets']):
            st.write("### 📩 Αιτήματα:")
            st.dataframe(pd.read_csv(FILES_PATH['tickets']))