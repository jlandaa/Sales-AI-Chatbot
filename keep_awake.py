from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

# URL de chatbot de ventas
URL = "https://jml-ventas-ai.streamlit.app/"

def ping_streamlit():
    options = Options()
    options.add_argument("--headless") # Ejecuta el navegador en segundo plano
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        print(f"Iniciando navegador para visitar: {URL}")
        # Selenium Manager se encarga de descargar el ChromeDriver automáticamente
        driver = webdriver.Chrome(options=options)
        
        driver.get(URL)
        print("Página cargada. Esperando 15 segundos para establecer la conexión WebSocket...")
        
        # Este tiempo asegura que la carga de Streamlit finalice y registre la "actividad"
        time.sleep(15) 
        
        print("Visita completada con éxito. Cerrando navegador.")
        driver.quit()
    except Exception as e:
        print(f"Ocurrió un error al intentar despertar la app: {e}")

if __name__ == "__main__":
    ping_streamlit()
