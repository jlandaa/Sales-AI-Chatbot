#!/usr/bin/env python3
from dotenv import load_dotenv
import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama

# Nuevas importaciones "Modernas" (LCEL) que evitan el módulo 'chains'
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# Función para formatear los documentos recuperados por FAISS
def format_docs(docs):
    return "\n".join(doc.page_content for doc in docs)

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
    
    docs = [f"El producto {p} tiene un total de {v} unidades vendidas." for p, v in ventas.items()]

    # 2. Embeddings y Vector Store
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vector_db = FAISS.from_texts(docs, embeddings)

    # 3. LLM Local con Ollama
    llm = ChatOllama(
        model="llama3.2:1b",
        temperature=0
    )

    # 4. Construcción de RAG Moderno (LCEL)
    retriever = vector_db.as_retriever(search_kwargs={"k": 4})

    # Le damos instrucciones claras al modelo
    template = """Usa el siguiente contexto sobre las ventas para responder la pregunta del usuario. 
    Si no sabes la respuesta, di simplemente que no lo sabes, no intentes adivinar.
    
    Contexto: {context}
    
    Pregunta: {pregunta}
    
    Respuesta:"""
    prompt = PromptTemplate.from_template(template)

    # Esta es la nueva tubería (Pipeline) de datos
    qa_chain = (
        {"context": retriever | format_docs, "pregunta": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    print("🤖 Chatbot de Ventas Local (Ollama - LCEL)")
    while True:
        pregunta = input("> ¿Qué quieres saber de las ventas? ").strip()
        if pregunta.lower() in ("salir", "exit", "quit"):
            print("👋 ¡Hasta luego!")
            break

        try:
            # En LCEL, .invoke() solo requiere el string de la pregunta
            res = qa_chain.invoke(pregunta)
            print("💡", res)
        except Exception as e:
            print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    main()
