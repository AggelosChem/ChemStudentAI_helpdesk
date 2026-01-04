import webview
import sys
import os
import subprocess # <--- Η αλλαγή: Χρήση υπο-διεργασίας
import time

def on_closed():
    """Όταν κλείσει το παράθυρο, να κλείσει και το Streamlit"""
    print("Τερματισμός εφαρμογής...")
    # Εδώ δεν χρειάζεται να κάνουμε κάτι έξτρα, το process.terminate() στο τέλος αρκεί

if __name__ == '__main__':
    # 1. Βρίσκουμε πού είναι το app.py
    # (Αυτό δουλεύει και αν το τρέχεις ως .py και αν γίνει .exe)
    if getattr(sys, 'frozen', False):
        application_path = sys._MEIPASS
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    app_path = os.path.join(application_path, "app_v15_sqlite.py")

    print(f"Εκκίνηση Streamlit από: {app_path}")

    # 2. Ξεκινάμε το Streamlit ως ΞΕΧΩΡΙΣΤΗ διεργασία (Subprocess)
    # Αυτό λύνει το πρόβλημα με τα Signals γιατί έχει δικό του Main Thread
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", app_path, "--global.developmentMode=false", "--server.headless=true", "--server.port=8501"],
        cwd=application_path # Ορίζουμε τον φάκελο εκτέλεσης
    )

    # 3. Περιμένουμε λίγο να "πάρει μπρος" ο server
    time.sleep(3)

    # 4. Ανοίγουμε το παράθυρο (GUI)
    window = webview.create_window(
        title="🎓 Uni Helpdesk Pro", 
        url="http://localhost:8501",
        width=1200,
        height=800,
        resizable=True,
        confirm_close=True
    )
    
    webview.start()

    # 5. Καθαρισμός: Μόλις κλείσει το παράθυρο, σκοτώνουμε το Streamlit
    process.terminate()
    sys.exit()