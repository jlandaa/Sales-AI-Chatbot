from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
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
            
            try:
                print("Buscando el botón para despertar la app...")
                boton_despertar = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Yes, get this app back up!')]"))
                )
                boton_despertar.click()
                print("¡Botón presionado! Esperando 30 segundos para que la app arranque...")
                time.sleep(30)
                
            except TimeoutException:
                print("El botón no apareció. La app ya estaba activa.")
                time.sleep(5)
            
            print(f"Visita completada con éxito para: {url}\n")
            
        print("Todas las aplicaciones del portfolio fueron visitadas. Cerrando navegador.")
        driver.quit()
        
    except Exception as e:
        print(f"Ocurrió un error al intentar despertar las apps: {e}")

if __name__ == "__main__":
    ping_streamlit_apps()
