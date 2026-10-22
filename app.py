import streamlit as st
import pandas as pd
import sqlite3
import os
# 1. NUEVOS IMPORTS PARA GOOGLE CLOUD
from google.cloud import bigquery
from google.oauth2 import service_account

st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 0rem;
        }
    </style>
""", unsafe_allow_html=True)

# Configuración de la página
st.set_page_config(page_title="BI Sales Chatbot", page_icon="📊", layout="centered")

st.title("🤖 Chatbot de Ventas BI")
st.markdown("Consulta tu reporte de ventas en lenguaje natural. El modelo generará la consulta SQL y extraerá el dato exacto.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# 2. NUEVA FUNCIÓN HÍBRIDA (LLM + Base de Datos)
@st.cache_resource
def init_entorno_hibrido():
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    
    template = """Eres un Data Analyst experto en bases de datos. 
    Tienes una tabla 'ventas' con dos columnas: 'Producto' (STRING) y 'Unidades_Vendidas' (INTEGER).
    
    REGLA DE NEGOCIO (Taxonomía):
    - Calzado = 'Zapatos', 'Medias'
    - Ropa = 'Pantalones', 'Camisetas', 'Camperas'
    - Accesorios = 'Sombreros', 'Guantes'
    (Usa estas categorías en un WHERE Producto IN (...) SOLO si preguntan por "ropa", "calzado" o "accesorios").

    REGLAS DE SEGURIDAD (INTEGRIDAD DE DATOS):
    1. FUERA DE DOMINIO: Si el usuario hace una pregunta que NO tiene NADA que ver con las ventas o los productos de la tabla proporcionada (ej. clima, deportes, saludos, chistes), debes devolver EXACTAMENTE esta consulta:
       SELECT 'Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas.' AS Mensaje;
    2. CORTAFUEGOS SEMÁNTICO: Si el usuario menciona una categoría, atributo, temporada (ej. 'invierno', 'verano') o adjetivo que NO existe explícitamente en la tabla o en la regla de Taxonomía, DEBES devolver la consulta de seguridad:
       SELECT 'Lo siento, como Analista de BI solo puedo responder sobre las categorías oficiales (Ropa, Calzado, Accesorios).' AS Mensaje;

    REGLA DE SINTAXIS OBLIGATORIA:
    - TODA consulta que busque datos numéricos o evalúe columnas DEBE incluir obligatoriamente la cláusula "FROM ventas". Nunca omitas el origen de los datos.

    REGLAS ESTRICTAS DE SINTAXIS SQL:
    1. El orden OBLIGATORIO es: SELECT -> FROM -> WHERE -> ORDER BY -> LIMIT -> OFFSET.
    2. NUNCA pongas un WHERE después de un ORDER BY, LIMIT u OFFSET.

    EJEMPLOS DE CÓDIGO (Aprende de estos patrones):
    Usuario: ¿Cuál es el producto más vendido?
    SQL: SELECT Producto, Unidades_Vendidas FROM ventas ORDER BY Unidades_Vendidas DESC LIMIT 1;
    
    Usuario: ¿Cuál es el producto más vendido después de las Medias?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas < (SELECT Unidades_Vendidas FROM ventas WHERE Producto = 'Medias') ORDER BY Unidades_Vendidas DESC LIMIT 1;
    
    Usuario: ¿Cuál es el segundo producto más vendido?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas < (SELECT MAX(Unidades_Vendidas) FROM ventas) ORDER BY Unidades_Vendidas DESC LIMIT 1;
    
    Usuario: ¿Cuántos guantes se vendieron?
    SQL: SELECT Unidades_Vendidas FROM ventas WHERE Producto = 'Guantes';
    
    Usuario: ¿Qué es lo que menos salió?
    SQL: SELECT Producto, Unidades_Vendidas FROM ventas ORDER BY Unidades_Vendidas ASC LIMIT 1;

    Usuario: ¿Qué productos vendieron más de 60 unidades?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas > 60;
    
    Usuario: ¿Cómo está el clima?
    SQL: SELECT 'Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas.' AS Mensaje;

    Usuario: Dame el total de ventas de indumentaria de invierno.
    SQL: SELECT 'Lo siento, como Analista de BI solo puedo responder sobre las categorías oficiales (Ropa, Calzado, Accesorios).' AS Mensaje;

    Usuario: ¿Cuál es el total de ventas de remeras y guantes?
    SQL: SELECT SUM(Unidades_Vendidas) FROM ventas WHERE Producto IN ('Camisetas', 'Guantes');

    PREGUNTA DEL USUARIO: {pregunta}
    
    IMPORTANTE: Compórtate como una API. Devuelve ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta, sin texto adicional ni bloques markdown:
    {{
        "sql": "AQUÍ_VA_TU_QUERY",
        "grafico": "AQUÍ_EL_TIPO"
    }}
    
    Reglas para elegir el campo "grafico":
    - Usa "metrica" si la consulta devuelve un solo número (ej. SUM, COUNT, MAX).
    - Usa "barras" si la consulta devuelve una categoría y un valor numérico (ej. ventas por producto).
    - Usa "tabla" si es un mensaje de texto de seguridad o no aplica ninguna de las anteriores.
    """
    prompt_template = PromptTemplate.from_template(template)

    try:
        # ==========================================
        # MODO CLOUD: Streamlit Cloud + Groq + BigQuery
        # ==========================================
        from langchain_groq import ChatGroq
        
        api_key = st.secrets["GROQ_API_KEY"]
        llm = ChatGroq(api_key=api_key, model_name="openai/gpt-oss-20b", temperature=0)
        
        gcp_credentials = dict(st.secrets["GCP_CREDENTIALS"])
        credentials = service_account.Credentials.from_service_account_info(gcp_credentials)
        db_conn = bigquery.Client(credentials=credentials, project=credentials.project_id)
        
        entorno = "CLOUD"
        
    except Exception:
        # ==========================================
        # MODO LOCAL: Docker + Ollama + SQLite
        # ==========================================
        from langchain_ollama import ChatOllama
        
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        llm = ChatOllama(model="llama3.2", temperature=0, base_url=ollama_url)
        
        db_conn = sqlite3.connect(':memory:', check_same_thread=False)
        entorno = "LOCAL"

    sql_chain = prompt_template | llm | StrOutputParser()
    return sql_chain, db_conn, entorno

sql_chain, db_conn, entorno = init_entorno_hibrido()

# 3. INTERFAZ DINÁMICA (Ocultar CSV en la nube)
if entorno == "CLOUD":
    st.success("🟢 Sistema Conectado a Data Warehouse Corporativo (Google BigQuery)")
    datos_cargados = True 
    # NUEVO BLOQUE: Visualización gráfica de la tabla en GCP
    try:
        # Hacemos un query a BigQuery para traer toda la tabla
        query_job = db_conn.query(f"SELECT * FROM `{db_conn.project}.ventas_data.ventas`")
        df_bq = query_job.to_dataframe()
        
        # Mostramos la tabla dentro de un bloque desplegable para no saturar la UI
        with st.expander("👁️ Ver tabla de datos alojada en Google Cloud", expanded=False):
            st.dataframe(
                df_bq,
                use_container_width=True,
                hide_index=True # Ocultamos el índice numérico por defecto de Pandas para que se vea más limpio
            )
    except Exception as e:
        st.warning(f"No se pudo cargar la vista previa de la tabla: {e}")
else:
    st.info("🟡 Entorno Local Aislado. Sube tu reporte para procesarlo en memoria.")
    uploaded_file = st.file_uploader("Sube tu archivo de ventas (.csv)", type=["csv"])
    
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        df.to_sql('ventas', db_conn, index=False, if_exists='replace')
        datos_cargados = True
        with st.expander("Ver vista previa de los datos locales"):
            st.dataframe(df)
    else:
        datos_cargados = False

# 4. EJECUCIÓN DINÁMICA DE LA QUERY
if datos_cargados:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ej: ¿Cuál es el segundo producto más vendido?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analizando en la base de datos..."):
                try:
                    query_generada = sql_chain.invoke({"pregunta": prompt}).strip()
                    query_generada = query_generada.replace("```sql", "").replace("```", "").strip()
                    st.code(query_generada, language="sql")
                    
                    # --- MAGIA HÍBRIDA AQUÍ ---
                    if entorno == "CLOUD":
                        job_config = bigquery.QueryJobConfig(default_dataset=f"{db_conn.project}.ventas_data")
                        query_job = db_conn.query(query_generada, job_config=job_config)
                        resultados = [list(row.values()) for row in query_job]
                    else:
                        cursor = db_conn.cursor()
                        cursor.execute(query_generada)
                        resultados = cursor.fetchall()
                    # --------------------------
                    
                    if not resultados or (len(resultados) > 0 and resultados[0][0] is None):
                        respuesta = "No se encontraron resultados para esa consulta."
                    else:
                        respuesta = "\n".join([f"- {fila[0]}: {fila[1]}" if len(fila) > 1 else f"- {fila[0]}" for fila in resultados])
                    
                    st.markdown(f"**Resultado:**\n{respuesta}")
                    
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"**Query ejecutada:**\n```sql\n{query_generada}\n```\n**Resultado:**\n{respuesta}"
                    })

                except Exception as e:
                    error_msg = f"⚠️ Hubo un error de ejecución SQL: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
