# Usar una imagen oficial de Python ligera y estable
FROM python:3.10-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de dependencias primero (mejora el caché de construcción)
COPY requirements.txt .

# Instalar las librerías necesarias
RUN pip install --no-cache-dir -r requirements.txt

# Archivos de código Python (Front-end y Lógica)
COPY app.py .
COPY chatbot.py .

# Base de datos local
COPY ventas.csv .

# Carpeta de configuración del servidor de Streamlit
COPY .streamlit/ .streamlit/

# Exponer el puerto por defecto que utiliza Streamlit
EXPOSE 8501

# Comando para iniciar la aplicación web (Entry point: app.py)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
