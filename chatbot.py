#!/usr/bin/env python3
from dotenv import load_dotenv
import pandas as pd
import sqlite3
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

def main():
    load_dotenv()
    
    # 1. Cargar datos y crear Base de Datos en Memoria
    try:
        df = pd.read_csv("ventas.csv")
        conn = sqlite3.connect(':memory:')
        df.to_sql('ventas', conn, index=False, if_exists='replace')
    except Exception as e:
        print(f"❌ Error al cargar los datos: {e}")
        return

    # 2. Configurar el "Traductor" Text-to-SQL (Llama 3.2 3B)
    llm = ChatOllama(model="llama3.2", temperature=0)

    # 3. Prompt de Text-to-SQL con Guardarraíles y Manejo Out-of-Domain
    template = """Eres un Data Analyst experto en SQLite. 
    Tienes una tabla 'ventas' con dos columnas: 'Producto' (TEXT) y 'Unidades_Vendidas' (INTEGER).
    
    REGLA DE NEGOCIO (Taxonomía):
    - Calzado = 'Zapatos', 'Medias'
    - Ropa = 'Pantalones', 'Camisetas', 'Camperas'
    - Accesorios = 'Sombreros', 'Guantes'
    (Usa estas categorías en un WHERE Producto IN (...) SOLO si preguntan por "ropa", "calzado" o "accesorios").

    REGLAS DE SEGURIDAD (FUERA DE DOMINIO):
    Si el usuario hace una pregunta que NO tiene NADA que ver con ventas, productos, stock o la tabla proporcionada (ej. clima, deportes, saludos, chistes), debes devolver EXACTAMENTE esta consulta:
    SELECT 'Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas.' AS Mensaje;

    REGLAS ESTRICTAS DE SINTAXIS SQL:
    1. El orden OBLIGATORIO es: SELECT -> FROM -> WHERE -> ORDER BY -> LIMIT -> OFFSET.
    2. NUNCA pongas un WHERE después de un ORDER BY, LIMIT u OFFSET.

    EJEMPLOS DE CÓDIGO (Aprende de estos patrones):
    Usuario: ¿Cuál es el producto más vendido?
    SQL: SELECT Producto, Unidades_Vendidas FROM ventas ORDER BY Unidades_Vendidas DESC LIMIT 1;
    
    Usuario: ¿Cuál es el segundo producto más vendido después de las Medias?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas < (SELECT MAX(Unidades_Vendidas) FROM ventas) ORDER BY Unidades_Vendidas DESC LIMIT 1;
    
    Usuario: ¿Cuál es el segundo producto más vendido?
    SQL: SELECT Producto FROM ventas WHERE Unidades_Vendidas < (SELECT MAX(Unidades_Vendidas) FROM ventas) ORDER BY Unidades_Vendidas DESC LIMIT 1;
    
    Usuario: ¿Cuántos guantes se vendieron?
    SQL: SELECT Unidades_Vendidas FROM ventas WHERE Producto = 'Guantes';
    
    Usuario: ¿Qué es lo que menos salió?
    SQL: SELECT Producto, Unidades_Vendidas FROM ventas ORDER BY Unidades_Vendidas ASC LIMIT 1;
    
    Usuario: ¿Cómo está el clima?
    SQL: SELECT 'Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas.' AS Mensaje;
    
    PREGUNTA DEL USUARIO: {pregunta}
    
    Escribe la consulta SQL exacta para responder. 
    IMPORTANTE: Devuelve ÚNICAMENTE el código SQL. No uses bloques de código (```sql), no des explicaciones.
    """
    
    prompt = PromptTemplate.from_template(template)

    # 4. Pipeline
    sql_chain = prompt | llm | StrOutputParser()

    print("🤖 Chatbot de Ventas BI - Motor SQL (v8.0 - Out-Of-Domain Safety)")
    print("Traduciendo lenguaje natural a SQL para precisión matemática.")
    print("Escribe 'salir' para terminar.\n")
    
    while True:
        pregunta = input("> ¿Qué quieres saber de las ventas? ").strip()
        if pregunta.lower() in ("salir", "exit", "quit"):
            print("👋 ¡Hasta luego!")
            break
        if not pregunta:
            continue

        try:
            # 1. El LLM genera la Query
            query_generada = sql_chain.invoke({"pregunta": pregunta}).strip()
            query_generada = query_generada.replace("```sql", "").replace("```", "").strip()
            
            print(f"\n⚙️  [Query Generada]: {query_generada}")
            
            # 2. Ejecutamos la Query
            cursor = conn.cursor()
            cursor.execute(query_generada)
            resultados = cursor.fetchall()
            
            # 3. Mostramos el dato
            print(f"💡 Resultado exacto:")
            if not resultados or resultados[0][0] is None:
                print("   - (Sin resultados / Dato no encontrado)")
            else:
                for fila in resultados:
                    if len(fila) == 1:
                        print(f"   - {fila[0]}")
                    else:
                        print(f"   - {fila[0]}: {fila[1]}")
            print("\n")
                
        except Exception as e:
            print(f"⚠️ Hubo un error procesando la consulta SQL: {e}\n")

if __name__ == "__main__":
    main()
