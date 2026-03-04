# 🤖 Chatbot de Ventas BI - Motor Text-to-SQL

Este proyecto es un asistente de Business Intelligence impulsado por Inteligencia Artificial que permite a los usuarios consultar un reporte de ventas utilizando lenguaje natural. El sistema actúa como un "traductor" que convierte preguntas coloquiales en consultas SQL precisas, ejecutándolas contra una base de datos en memoria para devolver resultados matemáticamente exactos.

## 🚀 ¿Qué resuelve este proyecto?
En entornos corporativos, los equipos de negocio necesitan respuestas rápidas sobre sus datos sin depender constantemente del equipo de analistas para escribir consultas SQL. Este chatbot democratiza el acceso a la información de ventas garantizando **cero alucinaciones**, ya que el LLM no genera la respuesta final de forma generativa, sino que escribe el código SQL exacto que extrae el dato real de la base de datos.

## ⚙️ ¿Cómo funciona?

El flujo de trabajo (Pipeline) se compone de los siguientes pasos:

1. **Ingesta de Datos:** Se lee un archivo `ventas.csv` utilizando Pandas y se carga dinámicamente en una base de datos SQLite en memoria (`sqlite3`).
2. **Procesamiento del Lenguaje:** Se utiliza **LangChain** para gestionar el flujo y conectar con un modelo local (**Llama 3.2 3B** vía **Ollama**).
3. **Prompt Engineering & Guardarraíles:** El LLM recibe un *system prompt* estricto que define la estructura de la tabla, reglas de negocio (taxonomías como "Ropa" o "Calzado") y directivas de seguridad (Out-of-Domain) para evitar respuestas fuera del contexto comercial.
4. **Ejecución y Respuesta:** El modelo devuelve únicamente código SQL válido. El script ejecuta esta query en la base de datos SQLite y retorna el dato exacto al usuario final.

## 🛠️ Tecnologías Utilizadas
* **Python 3**
* **LangChain** (Orquestación del LLM)
* **Ollama / Llama 3.2** (Modelo de lenguaje local)
* **Pandas & SQLite3** (Manipulación y almacenamiento de datos en memoria)

---

## 📁 Estructura del Proyecto

Asegúrate de tener los siguientes archivos en tu directorio:
* `chatbot.py`: El script principal con la lógica de LangChain y SQLite.
* `ventas.csv`: El dataset de origen con las columnas `Producto` y `Unidades_Vendidas`.
* `requirements.txt`: El listado de dependencias de Python necesarias.

---

## 💻 Guía de Instalación y Uso paso a paso

### Paso 1: Requisitos Previos
1. Tener **Python 3.8+** instalado en tu sistema.
2. Descargar e instalar [Ollama](https://ollama.com/).
3. Descargar el modelo Llama 3.2. Abre tu terminal y ejecuta:
   ```bash
   ollama run llama3.2
   ```

###   Paso 2: Preparar el Entorno
1. Clona este repositorio o crea una carpeta con los archivos del proyecto.

2. Es una buena práctica crear un entorno virtual. En tu terminal, dentro de la carpeta del proyecto, ejecuta:
  ```bash
python -m venv venv
   ```
3. Activa el entorno virtual:

Windows: venv\Scripts\activate

Mac/Linux: source venv/bin/activate


### Paso 3: Instalar Dependencias
Con el entorno virtual activado, instala las librerías necesarias ejecutando:
  ```bash
pip install -r requirements.txt
   ```

###    Paso 4: Ejecutar el Chatbot
Asegúrate de que Ollama esté corriendo en segundo plano y ejecuta el script principal:
  ```bash
python chatbot.py
   ```

¡Listo! El chatbot iniciará en la terminal y podrás empezar a interactuar con los datos.


**🧪Casos de Prueba (Testing)**
El modelo ha sido sometido a rigurosas pruebas de calidad para garantizar su viabilidad en un entorno analítico corporativo:

**1. Pruebas de Comparación y Lógica SQL**
Evalúa la capacidad de generar agregaciones, ordenamientos y límites correctos.

**Q:** "¿Cuál es el segundo producto más vendido después de las Medias?" * Resultado esperado: Retorna los Zapatos (120 unidades).

**Q:** "¿Qué productos vendieron menos de 40 unidades?"

**Resultado esperado:** Sombreros (30) y Camperas (15).

**2. Pruebas de Variación Lingüística y Taxonomía**
Verifica que el modelo aplique reglas de negocio y entienda sinónimos.

**Q:** "¿Cuál es el stock de calzado?"

**Resultado esperado:** Traduce "calzado" a "Zapatos" y "Medias" mediante la regla del prompt.

**Q:** "¿Qué es lo que menos salió?"

**Resultado esperado:** Identifica "salió" como "vendió" y ordena ascendentemente.

**3. Integridad y Seguridad (Out-of-Domain / Cero Alucinaciones)**
Garantiza que el bot no invente datos ni se desvíe de su propósito comercial.

**Q:** "¿Cuántos cinturones se vendieron?"

**Resultado esperado:** El sistema indica que no hay resultados o dato no encontrado.

**Q:** "¿Cuál es el clima de hoy?"

**Resultado esperado:** Se activa el guardarraíl devolviendo: "Lo siento, como Analista de BI solo puedo responder preguntas sobre el reporte de ventas."

**4. Prueba de Actualización Dinámica**
Al basarse en consultas SQL directas y no en conocimiento pre-entrenado, el sistema responde a cambios en tiempo real.

**Acción:** Cierra el bot, agrega la línea Gorras,450 al archivo ventas.csv, y vuelve a ejecutar.

**Q:** "¿Cuál es el producto más vendido?"

**Resultado esperado:** El bot identifica inmediatamente a las Gorras como el nuevo producto principal con 450 unidades.
