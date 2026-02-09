#!/usr/bin/env python3
from dotenv import load_dotenv
import os
import openai
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA

def respuesta_local(q, ventas):
    q = q.lower()
    if "menos ventas" in q:
        p, v = min(ventas.items(), key=lambda x: x[1])
        return f"El producto con menos ventas fue {p}, con {v} unidades vendidas."
    if "más ventas" in q or "mayor venta" in q:
        p, v = max(ventas.items(), key=lambda x: x[1])
        return f"El producto con más ventas fue {p}, con {v} unidades vendidas."
    return None

def main():
    load_dotenv()
    API_KEY = os.getenv("OPENAI_API_KEY")
    if not API_KEY:
        print("❗️ Define OPENAI_API_KEY en .env")
        return

    # Datos de ventas
    ventas = {"Zapatos": 120, "Camisetas": 75, "Pantalones": 50, "Sombreros": 30}
    docs = [f"Producto: {p}, Ventas: {v}" for p, v in ventas.items()]

    # 1. Embeddings locales actualizados
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    index = FAISS.from_texts(docs, embeddings)

    # 2. LLM actualizado (ChatOpenAI es mejor para gpt-3.5-turbo)
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0,
        api_key=API_KEY,
        max_retries=0
    )

    # 3. Cadena de recuperación
    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=index.as_retriever(search_kwargs={"k": 1})
    )

    print("🤖 Chatbot de Ventas (escribe 'salir' para terminar)")
    while True:
        pregunta = input("> ¿Qué quieres saber de las ventas? ").strip()
        if pregunta.lower() in ("salir", "exit", "quit"):
            print("👋 ¡Hasta luego!")
            break

        # Lógica Local
        resp = respuesta_local(pregunta, ventas)
        if resp:
            print("💡", resp)
            continue

        # Lógica LLM con manejo de errores moderno
        try:
            res = qa.invoke({"query": pregunta})
            print("💡", res["result"])
        except openai.RateLimitError:
            print("⚠️ No se puede consultar a OpenAI, se acabó la cuota.")
        except Exception as e:
            print(f"⚠️ Ocurrió un error inesperado: {e}")

if __name__ == "__main__":
    main()

