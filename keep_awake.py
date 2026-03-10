from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

# Lista de las aplicaciones del portfolio
URLS = [
    "https://jml-ventas-ai.streamlit.app/", # Chatbot de ventas híbrido
    "https://jml-dashboard-adr.streamlit.app/", # URL del dashboard de ADRs argentinos
    "https://jml-smartcredit-ml.streamlit.app/"  # URL de la app SmartCredit-ML
]

def ping_streamlit_apps():
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        # Iniciamos el navegador una sola vez
        driver = webdriver.Chrome(options=options)
        
        for url in URLS:
            print(f"Iniciando visita a: {url}")
            driver.get(url)
            
            # Aumentamos a 30 segundos para asegurar la conexión en apps más pesadas
            print("Página cargada. Esperando 30 segundos para establecer la conexión WebSocket...")
            time.sleep(30) 
            
            print(f"Visita completada con éxito para: {url}\n")
            
        print("Todas las aplicaciones del portfolio fueron visitadas. Cerrando navegador.")
        driver.quit()
        
    except Exception as e:
        print(f"Ocurrió un error al intentar despertar las apps: {e}")

if __name__ == "__main__":
    ping_streamlit_apps()
