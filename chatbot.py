#!/usr/bin/env python3
from dotenv import load_dotenv
import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama  # Importación para modelo local
from langchain.chains import RetrievalQA

def main():
    load_dotenv()
    
    # 1. Datos dinámicos 
    ventas = {
        "Zapatos": 120, 
        "Camisetas": 75, 
        "Pantalones": 50, 
        "Sombreros": 30,
        "Medias": 200  
    }
    
    # Convertimos los datos en "Documentos" para el motor de búsqueda
    docs = [f"El producto {p} tiene un total de {v} unidades vendidas." for p, v in ventas.items()]

    # 2. Embeddings y Vector Store (Locales)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vector_db = FAISS.from_texts(docs, embeddings)

    # 3. LLM Local con Ollama (Adiós a la cuota de OpenAI)
    # Asegúrate de haber hecho: ollama pull llama3.2:1b
    llm = ChatOllama(
        model="llama3.2:1b",
        temperature=0 # Queremos precisión, no creatividad
    )

    # 4. Cadena de RAG
    # k=4 permite que el modelo vea todos los productos para comparar máximos/mínimos
    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vector_db.as_retriever(search_kwargs={"k": 4}) 
    )

    print("🤖 Chatbot de Ventas Local (Ollama)")
    while True:
        pregunta = input("> ¿Qué quieres saber de las ventas? ").strip()
        if pregunta.lower() in ("salir", "exit", "quit"):
            print("👋 ¡Hasta luego!")
            break

        try:
            # El LLM ahora recibe la pregunta + los datos de FAISS y deduce la respuesta
            res = qa.invoke({"query": pregunta})
            print("💡", res["result"])
        except Exception as e:
            print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    main()

