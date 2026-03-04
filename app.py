import streamlit as st
import pandas as pd
import sqlite3
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 1. Configuración de la página
st.set_page_config(page_title="BI Sales Chatbot", page_icon="📊", layout="centered")

st.title("🤖 Chatbot de Ventas BI")
st.markdown("Sube tu reporte de ventas y consúltalo en lenguaje natural. El modelo generará la consulta SQL y extraerá el dato exacto.")

# 2. Inicializar el historial de chat en la sesión
if "messages" not in st.session_state:
    st.session_state.messages = []

# 3. Inicializar el modelo y el prompt (Cacheado para no recargar en cada interacción)
@st.cache_resource
def init_chain():
    llm = ChatOllama(model="llama3.2", temperature=0)
    template = """Eres un Data Analyst experto en SQLite. 
    Tienes una tabla 'ventas' con dos columnas: 'Producto' (TEXT) y 'Unidades_Vendidas' (INTEGER).
    
    REGLA DE NEGOCIO (Taxonomía):
    - Calzado = 'Zapatos', 'Medias'
    - Ropa = 'Pantalones', 'Camisetas', 'Camperas'
    - Accesorios = 'Sombreros', 'Guantes'
    (Usa estas categorías en un WHERE Producto IN (...) SOLO si preguntan por "ropa", "calzado" o "accesorios").

    REGLAS DE SEGURIDAD (FUERA DE DOMINIO):
    Si el usuario hace una pregunta que NO tiene NADA que ver con ventas, productos, stock o la tabla proporcionada, debes devolver EXACTAMENTE esta consulta:
    SELECT 'Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas.' AS Mensaje;

    REGLAS ESTRICTAS DE SINTAXIS SQL:
    1. El orden OBLIGATORIO es: SELECT -> FROM -> WHERE -> ORDER BY -> LIMIT -> OFFSET.
    2. NUNCA pongas un WHERE después de un ORDER BY, LIMIT u OFFSET.
    
    PREGUNTA DEL USUARIO: {pregunta}
    
    Escribe la consulta SQL exacta para responder. 
    IMPORTANTE: Devuelve ÚNICAMENTE el código SQL. No uses bloques de código (```sql), no des explicaciones.
    """
    prompt = PromptTemplate.from_template(template)
    return prompt | llm | StrOutputParser()

sql_chain = init_chain()

# 4. Widget para subir el archivo CSV
uploaded_file = st.file_uploader("Sube tu archivo de ventas (.csv)", type=["csv"])

if uploaded_file is not None:
    # Cargar datos a la sesión y crear la base de datos en memoria
    df = pd.read_csv(uploaded_file)
    conn = sqlite3.connect(':memory:')
    df.to_sql('ventas', conn, index=False, if_exists='replace')
    
    # Mostrar una vista previa opcional de los datos
    with st.expander("Ver vista previa de los datos"):
        st.dataframe(df)

    # 5. Mostrar historial de chat
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 6. Input del usuario
    if prompt := st.chat_input("Ej: ¿Cuál es el segundo producto más vendido?"):
        # Agregar y mostrar mensaje del usuario
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generar respuesta del asistente
        with st.chat_message("assistant"):
            with st.spinner("Traduciendo a SQL y analizando datos..."):
                try:
                    # Generar Query
                    query_generada = sql_chain.invoke({"pregunta": prompt}).strip()
                    query_generada = query_generada.replace("```sql", "").replace("```", "").strip()
                    
                    # Mostrar la query generada (Excelente para demostrar cómo funciona por detrás)
                    st.code(query_generada, language="sql")
                    
                    # Ejecutar Query
                    cursor = conn.cursor()
                    cursor.execute(query_generada)
                    resultados = cursor.fetchall()
                    
                    # Formatear el resultado
                    if not resultados or resultados[0][0] is None:
                        respuesta = "No se encontraron resultados para esa consulta."
                    else:
                        respuesta = "\n".join([f"- {fila[0]}: {fila[1]}" if len(fila) > 1 else f"- {fila[0]}" for fila in resultados])
                    
                    st.markdown(f"**Resultado:**\n{respuesta}")
                    
                    # Guardar en el historial
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"**Query ejecutada:**\n```sql\n{query_generada}\n```\n**Resultado:**\n{respuesta}"
                    })

                except Exception as e:
                    error_msg = f"⚠️ Hubo un error de ejecución SQL: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
else:
    st.info("👆 Por favor, sube un archivo CSV para habilitar el chat.")
