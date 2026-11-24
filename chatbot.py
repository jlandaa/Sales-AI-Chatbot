#!/usr/bin/env python3
import os
import sqlite3

import pandas as pd
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama

from sql_engine import (
    SQLSecurityError,
    formatear_respuesta_texto,
    limpiar_sql_crudo,
    validar_sql_seguro,
)


def main() -> None:
    load_dotenv()

    try:
        df = pd.read_csv("ventas.csv")
        conn = sqlite3.connect(":memory:")
        df.to_sql("ventas", conn, index=False, if_exists="replace")
    except Exception as exc:
        print(f"❌ Error al cargar los datos: {exc}")
        return

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(model="llama3.2", temperature=0, base_url=ollama_url)

    template = """Eres un Data Analyst experto en SQLite.
    Tienes una tabla 'ventas' con dos columnas: 'Producto' (TEXT) y 'Unidades_Vendidas' (INTEGER).

    REGLA DE NEGOCIO (Taxonomía):
    - Calzado = 'Zapatos', 'Medias'
    - Ropa = 'Pantalones', 'Camisetas', 'Camperas'
    - Accesorios = 'Sombreros', 'Guantes'
    (Usa estas categorías en un WHERE Producto IN (...) SOLO si preguntan por
    "ropa", "calzado" o "accesorios").

    REGLAS DE SEGURIDAD (INTEGRIDAD DE DATOS):
    1. FUERA DE DOMINIO: Si el usuario hace una pregunta que NO tiene NADA que ver con las
       ventas o los productos de la tabla (ej. clima, deportes, saludos, chistes), devuelve:
       SELECT 'Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas.' AS Mensaje;
    2. CORTAFUEGOS SEMÁNTICO: Si menciona una categoría, atributo o temporada que NO existe
       explícitamente en la tabla o en la regla de Taxonomía, devuelve:
       SELECT 'Lo siento, como Analista de BI solo puedo responder sobre las categorías oficiales (Ropa, Calzado, Accesorios).' AS Mensaje;

    REGLA DE SINTAXIS OBLIGATORIA:
    - TODA consulta que busque datos numéricos o evalúe columnas DEBE incluir "FROM ventas".
    - El orden OBLIGATORIO es: SELECT -> FROM -> WHERE -> ORDER BY -> LIMIT -> OFFSET.

    PREGUNTA DEL USUARIO: {pregunta}

    Escribe la consulta SQL exacta para responder.
    IMPORTANTE: Devuelve ÚNICAMENTE el código SQL sin bloques markdown ni explicaciones.
    """

    prompt = PromptTemplate.from_template(template)
    sql_chain = prompt | llm | StrOutputParser()

    print("🤖 Chatbot de Ventas BI - Motor SQL (v8.0 - Out-Of-Domain Safety)")
    print("Traduciendo lenguaje natural a SQL para precisión matemática.")
    print("Escribe 'salir' para terminar.\n")

    try:
        while True:
            pregunta = input("> ¿Qué quieres saber de las ventas? ").strip()
            if pregunta.lower() in ("salir", "exit", "quit"):
                print("👋 ¡Hasta luego!")
                break
            if not pregunta:
                continue

            try:
                query_cruda = limpiar_sql_crudo(sql_chain.invoke({"pregunta": pregunta}))
                query_generada = validar_sql_seguro(query_cruda)
                print(f"\n⚙️  [Query Generada]: {query_generada}")

                cursor = conn.cursor()
                cursor.execute(query_generada)
                resultados = cursor.fetchall()

                print("💡 Resultado exacto:")
                print(formatear_respuesta_texto(resultados))
                print("\n")
            except SQLSecurityError as exc:
                print(f"🛡️ Consulta bloqueada por seguridad: {exc}\n")
            except Exception as exc:
                print(f"⚠️ Hubo un error procesando la consulta SQL: {exc}\n")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
