# Sales Chatbot: Híbrido RAG & Lógica Local 🤖

Este proyecto es un chatbot de ventas inteligente desarrollado en Python. Su principal ventaja es su **enfoque híbrido**: combina una capa de **lógica determinista local** para cálculos de alto rendimiento con una capa de **Generación Aumentada por Recuperación (RAG)** para consultas semánticas complejas.



---

## 🚀 Características

* **Procesamiento Inteligente:**
    * **Capa Local:** Identifica instantáneamente consultas sobre "máximos" o "mínimos" de ventas, respondiendo sin latencia ni consumo de tokens.
    * **Capa AI (RAG):** Utiliza LangChain para interpretar el catálogo y responder sobre productos específicos de forma conversacional.
* **Stack Tecnológico:**
    * **Embeddings:** `all-MiniLM-L6-v2` (SentenceTransformers) para procesamiento vectorial local.
    * **Base de Datos Vectorial:** FAISS para búsquedas de similitud ultra rápidas.
    * **LLM:** OpenAI (`gpt-3.5-turbo`) configurado para máxima precisión.
* **Gestión de Errores:** Manejo nativo de `RateLimitError` para prevenir caídas por límites de cuota en la API de OpenAI.

---

## 🛠️ Requisitos e Instalación

### 1. Preparar el entorno
Se recomienda el uso de un entorno virtual para gestionar las dependencias:

```bash
python -m venv venv
# Activar en Windows:
.\venv\Scripts\activate
# Activar en macOS/Linux:
source venv/bin/activate
```
### 2. Instalar dependencias
Instalar las librerías necesarias especificadas en el archivo de requerimientos:
```bash
pip install -r requirements.txt
```
Las dependencias principales incluyen langchain, sentence-transformers, faiss-cpu, y openai==0.28.0.

### 3. Configuración
El sistema requiere una clave de API de OpenAI para funcionar.
Crea un archivo .env en el directorio raíz.
Añade tu clave siguiendo este formato:
```
OPENAI_API_KEY=tu_api_key_aqui
```


### 4. Instrucciones de Uso
Para iniciar el chatbot, ejecuta el archivo principal:
```bash
python chatbot.py
```

Ejemplos de Interacción:
* Pregunta local: "¿Qué producto tuvo menos ventas?" (El script detecta la palabra clave y responde sin consultar la IA) .
* Pregunta RAG: "¿Cuántos zapatos se vendieron?" (El sistema busca en el índice FAISS y el LLM genera la respuesta) .
* Salir: Escribe salir, exit o quit para cerrar la sesión.

### 5. Estructura del Proyecto
* chatbot.py: Script principal con la lógica del chatbot y la cadena RAG.
* requirements.txt: Lista de librerías y versiones compatibles.
* .env: Archivo de configuración para variables de entorno (no incluido por seguridad).
