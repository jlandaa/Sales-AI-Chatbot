#!/usr/bin/env python3
from dotenv import load_dotenv
import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# 1. Nueva importación para leer CSV
from langchain_community.document_loaders.csv_loader import CSVLoader

def format_docs(docs):
    return "\n".join(doc.page_content for doc in docs)

def main():
    load_dotenv()
    
    # 2. Cargar datos directamente desde el CSV (¡Adiós diccionario!)
    try:
        loader = CSVLoader(file_path="ventas.csv", encoding="utf-8")
        docs = loader.load()
    except FileNotFoundError:
        print("❌ Error: No se encontró el archivo 'ventas.csv' en la carpeta.")
        return

    # 3. Embeddings y Vector Store
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vector_db = FAISS.from_texts([doc.page_content for doc in docs], embeddings)

    # 4. LLM Local con Ollama
    llm = ChatOllama(
        model="llama3.2:1b",
        temperature=0
    )

    # 5. Construcción de RAG Moderno (LCEL)
    # k=10 asegura que el motor lea hasta 10 filas del CSV para tener todo el contexto
    retriever = vector_db.as_retriever(search_kwargs={"k": 10})

    template = """Eres un analista de datos. Usa el siguiente contexto sobre las ventas para responder la pregunta. 
    Si la respuesta no está en el contexto, responde exactamente: 'No tengo esa información en la base de datos'.
    
    Contexto: {context}
    
    Pregunta: {pregunta}
    
    Respuesta:"""
    prompt = PromptTemplate.from_template(template)

    # Pipeline de datos
    qa_chain = (
        {"context": retriever | format_docs, "pregunta": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    print("🤖 Chatbot de Ventas Local (Leyendo desde ventas.csv)")
    while True:
        pregunta = input("> ¿Qué quieres saber de las ventas? ").strip()
        if pregunta.lower() in ("salir", "exit", "quit"):
            print("👋 ¡Hasta luego!")
            break

        try:
            res = qa_chain.invoke(pregunta)
            print("💡", res)
        except Exception as e:
            print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    main()
