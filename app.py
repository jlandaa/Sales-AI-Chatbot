import os
import sqlite3
import time

import pandas as pd
import plotly.express as px
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

from sql_engine import (
    cargar_historial_db,
    formatear_respuesta_texto,
    formatear_valor_kpi,
    guardar_mensaje_db,
    init_history_db,
    limitar_resultados,
    limpiar_historial_db,
    parsear_respuesta_llm,
    validar_sql_seguro,
)

MAX_BYTES_BILLED = 100 * 1024 * 1024  # Tope FinOps de 100 MB por consulta en BigQuery

# 1. Configuración de la página (siempre primer comando de Streamlit)
st.set_page_config(page_title="BI Sales Chatbot", page_icon="Logo_jml.png", layout="centered")

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 0rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# 2. Historial persistente en SQLite
@st.cache_resource
def get_history_conn() -> sqlite3.Connection:
    return init_history_db("chat_history.db")


conn_history = get_history_conn()


def save_message(role: str, content_obj: object) -> None:
    """Guarda el mensaje en RAM y lo serializa a SQLite."""
    st.session_state.messages.append({"role": role, "content": content_obj})
    guardar_mensaje_db(conn_history, role, content_obj)


# Logo y controles en barra lateral
with st.sidebar:
    st.image("Logo_jml.png", width="stretch")
    st.markdown("---")
    st.markdown("**Desarrollado por JML Analytics**")

    if st.button("🗑️ Limpiar Historial"):
        limpiar_historial_db(conn_history)
        st.session_state.messages = []
        st.rerun()

st.title("🤖 Chatbot de Ventas BI")
st.markdown(
    "Consulta tu reporte de ventas en lenguaje natural. "
    "El modelo generará la consulta SQL y extraerá el dato exacto."
)

if "messages" not in st.session_state:
    st.session_state.messages = cargar_historial_db(conn_history)


# 3. Inicialización híbrida (Cloud: Groq + BigQuery | Local: Ollama + SQLite)
@st.cache_resource
def init_entorno_hibrido():
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import PromptTemplate

    template = """Eres un Data Analyst experto en bases de datos. Hoy es el año 2026.
    Tienes una tabla 'ventas' con cuatro columnas: 'Producto' (TEXT), 'Unidades_Vendidas' (INTEGER),
    'Fecha_Venta' (DATE) y 'Precio_Unitario' (FLOAT).

    REGLA DE NEGOCIO (Taxonomía):
    - Calzado = 'Zapatos', 'Medias'
    - Ropa = 'Pantalones', 'Camisetas', 'Camperas'
    - Accesorios = 'Sombreros', 'Guantes'
    (Usa estas categorías en un WHERE Producto IN (...) SOLO si preguntan por
    "ropa", "calzado" o "accesorios").

    REGLAS DE SEGURIDAD (INTEGRIDAD DE DATOS Y ERRORES):
    1. FUERA DE DOMINIO O LÓGICA ABSURDA: Si el usuario hace una pregunta que NO tiene NADA
       que ver con ventas, pide cruzar o sumar atributos incompatibles (ej. multiplicar texto
       por fecha), o menciona atributos inexistentes, devuelve EXACTAMENTE esta consulta:
       SELECT 'Lo siento, como Analista de BI solo puedo realizar cruces lógicos sobre el reporte de ventas.' AS Mensaje;
    2. CORTAFUEGOS SEMÁNTICO: Si mencionan una categoría, atributo o temporada (ej. 'invierno')
       que NO existe en la tabla, devuelve EXACTAMENTE esta consulta:
       SELECT 'Lo siento, solo puedo responder sobre las categorías oficiales (Ropa, Calzado, Accesorios).' AS Mensaje;

    REGLA DE SINTAXIS OBLIGATORIA:
    - TODA consulta que busque datos numéricos o evalúe columnas DEBE incluir obligatoriamente
      la cláusula "FROM ventas". Nunca omitas el origen de los datos.

    REGLAS ESTRICTAS DE SINTAXIS SQL:
    1. El orden OBLIGATORIO es: SELECT -> FROM -> WHERE -> ORDER BY -> LIMIT -> OFFSET.
    2. NUNCA pongas un WHERE después de un ORDER BY, LIMIT u OFFSET.

    EJEMPLOS DE CÓDIGO (Aprende de estos patrones):
    Usuario: ¿Cuál es el producto más vendido?
    SQL: SELECT Producto, Unidades_Vendidas FROM ventas ORDER BY Unidades_Vendidas DESC LIMIT 1;

    Usuario: ¿Cuál es el producto más vendido después de las Medias?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas < (
        SELECT Unidades_Vendidas FROM ventas WHERE Producto = 'Medias'
    ) ORDER BY Unidades_Vendidas DESC LIMIT 1;

    Usuario: ¿Cuál es el segundo producto más vendido?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas < (
        SELECT MAX(Unidades_Vendidas) FROM ventas
    ) ORDER BY Unidades_Vendidas DESC LIMIT 1;

    Usuario: ¿Cuántos guantes se vendieron?
    SQL: SELECT Unidades_Vendidas FROM ventas WHERE Producto = 'Guantes';

    Usuario: ¿Qué es lo que menos salió?
    SQL: SELECT Producto, Unidades_Vendidas FROM ventas ORDER BY Unidades_Vendidas ASC LIMIT 1;

    Usuario: ¿Qué productos vendieron más de 60 unidades?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas > 60;

    Usuario: ¿Cómo está el clima?
    SQL: SELECT 'Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas.' AS Mensaje;

    Usuario: Dame el total de ventas de indumentaria de invierno.
    SQL: SELECT 'Lo siento, solo puedo responder sobre las categorías oficiales (Ropa, Calzado, Accesorios).' AS Mensaje;

    Usuario: ¿Cuál es el total de ventas de remeras y guantes?
    SQL: SELECT SUM(Unidades_Vendidas) FROM ventas WHERE Producto IN ('Camisetas', 'Guantes');

    PREGUNTA DEL USUARIO: {pregunta}

    IMPORTANTE: Compórtate como una API. Devuelve ÚNICAMENTE un objeto JSON válido con la
    siguiente estructura exacta, sin texto adicional ni bloques markdown:
    {{
        "sql": "AQUÍ_VA_TU_QUERY",
        "grafico": "AQUÍ_EL_TIPO"
    }}

    Reglas para elegir el campo "grafico":
    - Usa "metrica" o "tabla" si la consulta devuelve un solo número o busca una fecha puntual.
    - Usa "barras" si la consulta devuelve una categoría y un valor numérico.
    - Usa "lineas" EXCLUSIVAMENTE si pide evolución temporal o tendencias a lo largo de fechas.
    - Usa "dispersion" si piden comparar precios vs unidades.
    - Usa "tabla" si es un mensaje de texto de seguridad o no aplica ninguna de las anteriores.
    - Usa "torta" o "anillo" EXCLUSIVAMENTE si devuelve DOS columnas simples (Categoría y Valor).
      Nunca uses funciones de ventana (OVER) complejas para estos gráficos.
    """
    prompt_template = PromptTemplate.from_template(template)

    try:
        from langchain_groq import ChatGroq

        api_key = st.secrets["GROQ_API_KEY"]
        llm = ChatGroq(api_key=api_key, model_name="openai/gpt-oss-20b", temperature=0)

        gcp_credentials = dict(st.secrets["GCP_CREDENTIALS"])
        credentials = service_account.Credentials.from_service_account_info(gcp_credentials)
        db_conn = bigquery.Client(credentials=credentials, project=credentials.project_id)
        entorno_actual = "CLOUD"
    except Exception:
        from langchain_ollama import ChatOllama

        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        llm = ChatOllama(model="llama3.2", temperature=0, base_url=ollama_url)
        db_conn = sqlite3.connect(":memory:", check_same_thread=False)
        entorno_actual = "LOCAL"

    chain = prompt_template | llm | StrOutputParser()
    return chain, db_conn, entorno_actual


@st.cache_data(ttl=3600)
def cargar_preview_bigquery(_bq_client: bigquery.Client) -> pd.DataFrame:
    """Cachea la vista previa de BigQuery por 1 hora para evitar consultas en cada rerun."""
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    query_job = _bq_client.query(
        f"SELECT * FROM `{_bq_client.project}.ventas_data.ventas`",
        job_config=job_config,
    )
    return query_job.to_dataframe()


sql_chain, db_conn, entorno = init_entorno_hibrido()


# 4. Renderizador visual reutilizable (chat en vivo e historial)
def mostrar_resultado_visual(
    query_generada: str,
    respuesta_texto: str,
    tipo_grafico: str,
    resultados: list,
    latencia: float,
    entorno_actual: str,
) -> None:
    """Renderiza el SQL, el gráfico o KPI correspondiente y la telemetría."""
    st.code(query_generada, language="sql")

    if "Lo siento" in respuesta_texto:
        st.warning(resultados[0][0] if resultados else respuesta_texto)
    elif respuesta_texto == "No se encontraron resultados para esa consulta." or not resultados:
        st.warning(respuesta_texto)
    else:
        st.markdown("**Resultado Analítico:**")
        tiene_varias_cols = len(resultados[0]) > 1

        if tipo_grafico == "metrica":
            valor_mostrar = formatear_valor_kpi(resultados[0][0])
            st.metric(label="Valor Calculado", value=valor_mostrar)

        elif tipo_grafico == "barras" and tiene_varias_cols:
            if len(resultados) == 1:
                categoria = str(resultados[0][0])
                valor_mostrar = formatear_valor_kpi(resultados[0][1], es_moneda=True)
                st.metric(label=f"Top 1: {categoria}", value=valor_mostrar)
            else:
                df_grafico = pd.DataFrame(resultados).set_index(0)
                st.bar_chart(df_grafico)

        elif tipo_grafico == "lineas" and tiene_varias_cols:
            if len(resultados) == 1:
                st.metric(label=str(resultados[0][0]), value=formatear_valor_kpi(resultados[0][1]))
            else:
                df_grafico = pd.DataFrame(resultados).set_index(0)
                st.line_chart(df_grafico)

        elif tipo_grafico == "dispersion" and tiene_varias_cols:
            if len(resultados) == 1:
                st.metric(label=str(resultados[0][0]), value=formatear_valor_kpi(resultados[0][1]))
            else:
                df_grafico = pd.DataFrame(resultados).set_index(0)
                st.scatter_chart(df_grafico)

        elif tipo_grafico in ("torta", "anillo") and tiene_varias_cols:
            if len(resultados) == 1:
                st.metric(label=str(resultados[0][0]), value=formatear_valor_kpi(resultados[0][1]))
            else:
                filas_dos_cols = [fila[:2] for fila in resultados]
                df_grafico = pd.DataFrame(filas_dos_cols, columns=["Categoría", "Valor"])
                hole = 0.5 if tipo_grafico == "anillo" else 0.0
                titulo = "Distribución (Anillo)" if hole > 0 else "Distribución de Ventas"
                fig = px.pie(df_grafico, values="Valor", names="Categoría", hole=hole, title=titulo)
                st.plotly_chart(fig, width="stretch")

        else:
            st.markdown(respuesta_texto)

        st.caption(f"⚡ Consulta procesada en {latencia} segundos mediante {entorno_actual}")


# 5. Interfaz dinámica según entorno
if entorno == "CLOUD":
    st.success("🟢 Sistema Conectado a Data Warehouse Corporativo (Google BigQuery)")
    datos_cargados = True
    try:
        df_bq = cargar_preview_bigquery(db_conn)
        with st.expander("👁️ Ver tabla de datos alojada en Google Cloud", expanded=False):
            st.dataframe(df_bq, width="stretch", hide_index=True)
    except Exception as exc:
        st.warning(f"No se pudo cargar la vista previa de la tabla: {exc}")
else:
    st.info("🟡 Entorno Local Aislado. Sube tu reporte para procesarlo en memoria.")
    uploaded_file = st.file_uploader("Sube tu archivo de ventas (.csv)", type=["csv"])

    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        df.to_sql("ventas", db_conn, index=False, if_exists="replace")
        datos_cargados = True
        with st.expander("Ver vista previa de los datos locales"):
            st.dataframe(df)
    else:
        datos_cargados = False


# 6. Ejecución conversacional con Guardrail SQL
if datos_cargados:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if isinstance(message["content"], dict):
                d = message["content"]
                mostrar_resultado_visual(
                    d["query"],
                    d["texto"],
                    d["grafico"],
                    d["resultados"],
                    d["latencia"],
                    d["entorno"],
                )
            else:
                st.markdown(message["content"])

    if prompt := st.chat_input("Ej: ¿Cuál es el segundo producto más vendido?"):
        save_message("user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analizando en la base de datos..."):
                try:
                    start_time = time.time()
                    respuesta_llm = sql_chain.invoke({"pregunta": prompt})
                    query_cruda, tipo_grafico = parsear_respuesta_llm(respuesta_llm)
                    query_generada = validar_sql_seguro(query_cruda)

                    if entorno == "CLOUD":
                        job_config = bigquery.QueryJobConfig(
                            default_dataset=f"{db_conn.project}.ventas_data",
                            maximum_bytes_billed=MAX_BYTES_BILLED,
                        )
                        query_job = db_conn.query(query_generada, job_config=job_config)
                        resultados = [list(row.values()) for row in query_job]
                    else:
                        cursor = db_conn.cursor()
                        cursor.execute(query_generada)
                        resultados = [list(row) for row in cursor.fetchall()]

                    resultados, fue_truncado = limitar_resultados(resultados, max_filas=100)
                    if fue_truncado:
                        st.warning(
                            "⚠️ El volumen de datos es muy alto. Mostrando los primeros "
                            "100 registros para proteger el rendimiento."
                        )

                    respuesta_texto = formatear_respuesta_texto(resultados)
                    latencia = round(time.time() - start_time, 2)

                    mostrar_resultado_visual(
                        query_generada,
                        respuesta_texto,
                        tipo_grafico,
                        resultados,
                        latencia,
                        entorno,
                    )

                    datos_assistant = {
                        "query": query_generada,
                        "texto": respuesta_texto,
                        "grafico": tipo_grafico,
                        "resultados": resultados,
                        "latencia": latencia,
                        "entorno": entorno,
                    }
                    save_message("assistant", datos_assistant)

                except Exception as exc:
                    error_msg = f"⚠️ Hubo un error de ejecución SQL: {exc}"
                    st.error(error_msg)
                    save_message("assistant", error_msg)
else:
    st.info("👆 Por favor, sube un archivo CSV para habilitar el chat.")
