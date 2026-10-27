import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import plotly.express as px
import time # Nuevo import
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
st.set_page_config(page_title="BI Sales Chatbot", page_icon="Logo_jml.png", layout="centered")


# --- BLOQUE 1: BASE DE DATOS DE HISTORIAL AVANZADO (Soporta JSON) ---
def init_history_db():
    conn = sqlite3.connect("chat_history.db", check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

conn_history = init_history_db()

def save_message(role, content_obj):
    """Guarda el mensaje en RAM y lo serializa a JSON para Disco (SQLite)"""
    st.session_state.messages.append({"role": role, "content": content_obj})
    
    # Si el contenido es un diccionario (gráficos/metadata), lo pasamos a String JSON
    if isinstance(content_obj, dict):
        content_str = json.dumps(content_obj, default=str) # default=str protege contra errores de formato de fecha
    else:
        content_str = str(content_obj)
        
    conn_history.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content_str))
    conn_history.commit()
# ------------------------------------------------

# Logo en la barra lateral
with st.sidebar:
    st.image("Logo_jml.png", width="stretch")
    st.markdown("---")
    st.markdown("**Desarrollado por JML Analytics**")
    
    if st.button("🗑️ Limpiar Historial"):
        conn_history.execute("DELETE FROM chat_history")
        conn_history.commit()
        st.session_state.messages = []
        st.rerun()
    
st.title("🤖 Chatbot de Ventas BI")
st.markdown("Consulta tu reporte de ventas en lenguaje natural. El modelo generará la consulta SQL y extraerá el dato exacto.")

# Cargar historial desde la base de datos al entrar y DESERIALIZAR el JSON
if "messages" not in st.session_state:
    cursor = conn_history.execute("SELECT role, content FROM chat_history ORDER BY id ASC")
    st.session_state.messages = []
    for role, content_str in cursor.fetchall():
        try:
            # Intentamos reconstruir el diccionario JSON si el mensaje empieza con '{'
            if role == "assistant" and content_str.strip().startswith("{"):
                content_obj = json.loads(content_str)
            else:
                content_obj = content_str
        except Exception:
            content_obj = content_str
        st.session_state.messages.append({"role": role, "content": content_obj})

# 2. NUEVA FUNCIÓN HÍBRIDA (LLM + Base de Datos)
@st.cache_resource
def init_entorno_hibrido():
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    
    template = """Eres un Data Analyst experto en bases de datos. Hoy es el año 2026.
    Tienes una tabla 'ventas' con cuatro columnas: 'Producto' (TEXT), 'Unidades_Vendidas' (INTEGER), 'Fecha_Venta' (DATE) y 'Precio_Unitario' (FLOAT).
    
    REGLA DE NEGOCIO (Taxonomía):
    - Calzado = 'Zapatos', 'Medias'
    - Ropa = 'Pantalones', 'Camisetas', 'Camperas'
    - Accesorios = 'Sombreros', 'Guantes'
    (Usa estas categorías en un WHERE Producto IN (...) SOLO si preguntan por "ropa", "calzado" o "accesorios").

   REGLAS DE SEGURIDAD (INTEGRIDAD DE DATOS Y ERRORES):
    1. FUERA DE DOMINIO O LÓGICA ABSURDA: Si el usuario hace una pregunta que NO tiene NADA que ver con ventas, pide cruzar o sumar atributos incompatibles (ej. multiplicar texto por fecha), o menciona atributos inexistentes, debes abortar y devolver EXACTAMENTE esta consulta:
       SELECT 'Lo siento, como Analista de BI solo puedo realizar cruces lógicos sobre el reporte de ventas.' AS Mensaje;
    2. CORTAFUEGOS SEMÁNTICO: Si mencionan una categoría, atributo o temporada (ej. 'invierno') que NO existe en la tabla, debes devolver EXACTAMENTE esta consulta:
       SELECT 'Lo siento, solo puedo responder sobre las categorías oficiales (Ropa, Calzado, Accesorios).' AS Mensaje;

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
    - Usa "metrica" o "tabla" si la consulta devuelve un solo número o busca una fecha puntual/día específico (ej. "¿En qué fecha se vendieron más medias?").
    - Usa "barras" si la consulta devuelve una categoría y un valor numérico (ej. ventas por producto).
    - Usa "lineas" EXCLUSIVAMENTE si la consulta pide evolución temporal, tendencias o comportamiento a lo largo de un período de fechas.
    - Usa "dispersion" si piden comparar precios vs unidades.
    - Usa "tabla" si es un mensaje de texto de seguridad o no aplica ninguna de las anteriores.
    - Usa "torta" o "anillo" EXCLUSIVAMENTE si la consulta devuelve un formato tabular simple de DOS columnas (Columna 1: Categoría o Nombre, Columna 2: Valor numérico total). Nunca uses funciones de ventana (OVER) complejas para estos gráficos.
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

# --- 3. NUEVA FUNCIÓN REUTILIZABLE: DIBUJADOR DE GRÁFICOS ---
def mostrar_resultado_visual(query_generada, respuesta_texto, tipo_grafico, resultados, latencia, entorno):
    """Función centralizada para renderizar UI que puede ser usada por el chat en vivo y por el historial"""
    st.code(query_generada, language="sql")

    if "Lo siento" in respuesta_texto:
        st.warning(resultados[0][0] if resultados else respuesta_texto)
    elif respuesta_texto == "No se encontraron resultados para esa consulta.":
        st.warning(respuesta_texto)
    else:
        st.markdown("**Resultado Analítico:**")
        
        # NUEVO: Gráfico de Métrica (KPI) con control de tipos de datos
        if tipo_grafico == "metrica" and resultados:
            valor = resultados[0][0]
            # Validamos si es un número (int o float) para formatearlo
            if isinstance(valor, (int, float)):
                valor_mostrar = f"{valor:,}".replace(",", ".")
            else:
                # Si es un texto o fecha, lo dejamos intacto
                valor_mostrar = str(valor)
            st.metric(label="Valor Calculado", value=valor_mostrar)
            
        # Gráfico de Barras (con inteligencia de UX y Finanzas)
        elif tipo_grafico == "barras" and len(resultados[0]) > 1:
            # Interceptor: Si hay un solo registro (ej. LIMIT 1), forzamos una Métrica
            if len(resultados) == 1:
                categoria = str(resultados[0][0])
                valor = resultados[0][1]
                # Si el valor es FLOAT (Precio o Ingresos), aplicamos formato moneda
                if isinstance(valor, float):
                    valor_mostrar = f"${valor:,.0f}".replace(",", ".")
                # Si es INTEGER (Unidades vendidas), aplicamos formato numérico normal
                elif isinstance(valor, int):
                    valor_mostrar = f"{valor:,}".replace(",", ".")
                else:
                    valor_mostrar = str(valor)
                st.metric(label=f"Top 1: {categoria}", value=valor_mostrar)
            else:
                # Si hay múltiples registros, dibujamos el gráfico de barras normal
                df_grafico = pd.DataFrame(resultados)
                df_grafico = df_grafico.set_index(0) 
                st.bar_chart(df_grafico)

        # Gráfico de Líneas
        elif tipo_grafico == "lineas" and len(resultados[0]) > 1:
            if len(resultados) == 1:
                # Interceptor UX: Un solo punto en el tiempo es un KPI
                categoria = str(resultados[0][0])
                valor = resultados[0][1]
                valor_mostrar = f"{valor:,}".replace(",", ".") if isinstance(valor, (int, float)) else str(valor)
                st.metric(label=categoria, value=valor_mostrar)
            else:
                df_grafico = pd.DataFrame(resultados)
                df_grafico = df_grafico.set_index(0) 
                st.line_chart(df_grafico)
                
        # Gráfico de Dispersión
        elif tipo_grafico == "dispersion" and len(resultados[0]) > 1:
            if len(resultados) == 1:
                # Interceptor UX: Un solo punto de dispersión es un KPI
                categoria = str(resultados[0][0])
                valor = resultados[0][1]
                valor_mostrar = f"{valor:,}".replace(",", ".") if isinstance(valor, (int, float)) else str(valor)
                st.metric(label=categoria, value=valor_mostrar)
            else:
                df_grafico = pd.DataFrame(resultados)
                df_grafico = df_grafico.set_index(0)
                st.scatter_chart(df_grafico)

        # Gráfico de Torta (Plotly)
        elif tipo_grafico == "torta" and len(resultados[0]) > 1:
            if len(resultados) == 1:
                # Interceptor UX: Un solo ítem se convierte en KPI
                categoria = str(resultados[0][0])
                valor = resultados[0][1]
                valor_mostrar = f"{valor:,}".replace(",", ".") if isinstance(valor, (int, float)) else str(valor)
                st.metric(label=categoria, value=valor_mostrar)
            else:
                df_grafico = pd.DataFrame(resultados, columns=['Categoría', 'Valor'])
                fig = px.pie(df_grafico, values='Valor', names='Categoría', title="Distribución de Ventas")
                st.plotly_chart(fig, width="stretch")

        # Gráfico de Anillo (Plotly)
        elif tipo_grafico == "anillo" and len(resultados[0]) > 1:
            if len(resultados) == 1:
                # Interceptor UX: Un solo ítem se convierte en KPI
                categoria = str(resultados[0][0])
                valor = resultados[0][1]
                valor_mostrar = f"{valor:,}".replace(",", ".") if isinstance(valor, (int, float)) else str(valor)
                st.metric(label=categoria, value=valor_mostrar)
            else:
                df_grafico = pd.DataFrame(resultados, columns=['Categoría', 'Valor'])
                fig = px.pie(df_grafico, values='Valor', names='Categoría', hole=0.5, title="Distribución (Anillo)")
                st.plotly_chart(fig, width="stretch")
            
        # Fallback (Tabla/Texto)
        else:
            st.markdown(respuesta_texto)

        # Impacto visual en la UI (Telemetría para el usuario/auditor)
        st.caption(f"⚡ Consulta procesada en {latencia} segundos mediante {entorno}")
# --------------------------------------------------------------
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
                width="stretch",
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
    
    # --- DIBUJADO DEL HISTORIAL DE CHAT ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if isinstance(message["content"], dict):
                # Es un objeto estructurado del asistente, usamos la función de dibujo
                d = message["content"]
                mostrar_resultado_visual(d["query"], d["texto"], d["grafico"], d["resultados"], d["latencia"], d["entorno"])
            else:
                # Es texto del usuario o un error viejo
                st.markdown(message["content"])

    if prompt := st.chat_input("Ej: ¿Cuál es el segundo producto más vendido?"):
        save_message("user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analizando en la base de datos..."):
                try:
                    start_time = time.time() # ⏱️ INICIA EL CRONÓMETRO
                    
                    # 1. Obtenemos la respuesta cruda del LLM
                    respuesta_llm = sql_chain.invoke({"pregunta": prompt}).strip()
                    
                    # Parseador robusto (Soporta JSON y Texto plano)
                    # Buscamos dónde empieza y termina el JSON real
                    inicio_json = respuesta_llm.find('{')
                    fin_json = respuesta_llm.rfind('}')
                    
                    if inicio_json != -1 and fin_json != -1:
                        texto_limpio = respuesta_llm[inicio_json:fin_json+1] # Extraemos solo el JSON
                        try:
                            dict_respuesta = json.loads(texto_limpio)
                            query_generada = dict_respuesta.get("sql", "")
                            tipo_grafico = dict_respuesta.get("grafico", "texto")
                        except Exception:
                            query_generada = respuesta_llm
                            tipo_grafico = "texto"
                    else:
                        # Fallback: Si no hay llaves, asumimos que devolvió SQL crudo sin JSON
                        query_generada = respuesta_llm.replace("```sql", "").replace("```", "").strip()
                        tipo_grafico = "texto"
                    
                    # --- INTERCEPTOR DE SEGURIDAD 1: FALSO SQL ---
                    if not query_generada.strip().upper().startswith("SELECT"):
                         raise ValueError("El asistente generó texto en lugar de una consulta válida.")

                    # --- MAGIA HÍBRIDA AQUÍ ---
                    if entorno == "CLOUD":
                        job_config = bigquery.QueryJobConfig(default_dataset=f"{db_conn.project}.ventas_data")
                        query_job = db_conn.query(query_generada, job_config=job_config)
                        resultados = [list(row.values()) for row in query_job]
                    else:
                        cursor = db_conn.cursor()
                        cursor.execute(query_generada)
                        resultados = cursor.fetchall()
                        
                    # --- INTERCEPTOR DE SEGURIDAD 2: SOBRECARGA DE RAM ---
                    if len(resultados) > 100:
                         st.warning("⚠️ El volumen de datos es muy alto. Mostrando una muestra gráfica de los primeros 100 registros para proteger el rendimiento.")
                         resultados = resultados[:100]
                        
                    # --- 3. PREPARAMOS EL TEXTO DE RESPALDO  ---
                    if not resultados or (len(resultados) > 0 and resultados[0][0] is None):
                        respuesta_texto = "No se encontraron resultados para esa consulta."
                    else:
                        respuesta_texto = "\n".join([f"- {fila[0]}: {fila[1]}" if len(fila) > 1 else f"- {fila[0]}" for fila in resultados])

                    end_time = time.time() # ⏱️ FRENA EL CRONÓMETRO
                    latencia = round(end_time - start_time, 2)

                    # --- RENDERIZADO VISUAL EN TIEMPO REAL ---
                    mostrar_resultado_visual(query_generada, respuesta_texto, tipo_grafico, resultados, latencia, entorno)

                    # --- GUARDADO ESTRUCTURADO (JSON) PARA SOPORTAR F5 ---
                    # 5. Guardamos en el historial para que no desaparezca al preguntar de nuevo
                    datos_assistant = {
                        "query": query_generada,
                        "texto": respuesta_texto,
                        "grafico": tipo_grafico,
                        "resultados": resultados,
                        "latencia": latencia,
                        "entorno": entorno
                    }
                    save_message("assistant", datos_assistant)

                except Exception as e:
                    error_msg = f"⚠️ Hubo un error de ejecución SQL: {e}"
                    st.error(error_msg)
                    save_message("assistant", error_msg)
else:
    st.info("👆 Por favor, sube un archivo CSV para habilitar el chat.")
