import json
import re
import sqlite3

VALID_CHART_TYPES = {
    "metrica",
    "barras",
    "lineas",
    "dispersion",
    "tabla",
    "torta",
    "anillo",
    "texto",
}

FORBIDDEN_SQL_KEYWORDS = (
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    r"REPLACE\s+INTO",
    "MERGE",
    "GRANT",
    "REVOKE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "EXEC",
    "EXECUTE",
    "CALL",
)

FORBIDDEN_SQL_PATTERN = re.compile(
    rf"\b({'|'.join(FORBIDDEN_SQL_KEYWORDS)})\b",
    re.IGNORECASE,
)

STRING_LITERAL_PATTERN = re.compile(r"'(?:\\.|''|[^'\\])*'|\"(?:\\.|\"\"|[^\"\\])*\"")


class SQLSecurityError(ValueError):
    """Excepción lanzada cuando una consulta SQL incumple las reglas de seguridad."""


def limpiar_sql_crudo(texto: str) -> str:
    """Elimina bloques Markdown, prefijos 'SQL:' y espacios sobrantes."""
    limpio = re.sub(r"```(?:sql)?", "", texto, flags=re.IGNORECASE).replace("```", "").strip()
    limpio = re.sub(r"^SQL\s*:\s*", "", limpio, flags=re.IGNORECASE).strip()
    return limpio


def extraer_texto_respuesta_llm(respuesta: object) -> str:
    """Extrae texto desde str o AIMessage (incluyendo bloques o reasoning_content)."""
    if isinstance(respuesta, str):
        return respuesta.strip()

    content = getattr(respuesta, "content", "")
    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        partes = [
            bloque.get("text", "") if isinstance(bloque, dict) else str(bloque)
            for bloque in content
        ]
        texto_bloques = "\n".join(p for p in partes if p).strip()
        if texto_bloques:
            return texto_bloques

    additional_kwargs = getattr(respuesta, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        for clave in ("reasoning_content", "reasoning"):
            valor = additional_kwargs.get(clave)
            if isinstance(valor, str) and valor.strip():
                return valor.strip()

    return ""


def _extraer_objetos_json(texto: str) -> list[dict]:
    """Extrae todos los objetos JSON válidos embebidos en el texto."""
    decoder = json.JSONDecoder(strict=False)
    objetos: list[dict] = []
    idx = 0
    longitud = len(texto)

    while idx < longitud:
        pos = texto.find("{", idx)
        if pos == -1:
            break
        try:
            obj, end_idx = decoder.raw_decode(texto, pos)
            if isinstance(obj, dict):
                objetos.append(obj)
            idx = end_idx
        except json.JSONDecodeError:
            idx = pos + 1

    return objetos


def parsear_respuesta_llm(respuesta_llm: str) -> tuple[str, str]:
    """Extrae (sql, tipo_grafico) desde JSON estructurado o SQL plano como fallback."""
    texto = respuesta_llm.strip()

    for data in reversed(_extraer_objetos_json(texto)):
        data_norm = {str(k).strip().lower(): v for k, v in data.items()}
        raw_sql = data_norm.get("sql") or data_norm.get("query") or ""
        query = limpiar_sql_crudo(str(raw_sql)) if raw_sql else ""
        if query:
            raw_grafico = data_norm.get("grafico") or data_norm.get("chart") or "texto"
            grafico = str(raw_grafico).strip().lower()
            if grafico not in VALID_CHART_TYPES:
                grafico = "texto"
            return query, grafico

    return limpiar_sql_crudo(texto), "texto"


def _remover_literales_texto(query: str) -> str:
    """Enmascara literales entre comillas simples y dobles para evitar falsos positivos."""
    return STRING_LITERAL_PATTERN.sub("''", query)


def validar_sql_seguro(query: str) -> str:
    """Valida que la consulta sea estrictamente de lectura (SELECT/WITH) y sin inyección."""
    limpia = limpiar_sql_crudo(query)
    if not limpia:
        raise SQLSecurityError("La consulta SQL generada está vacía.")

    if limpia.endswith(";"):
        limpia = limpia[:-1].strip()

    sin_literales = _remover_literales_texto(limpia)

    if "--" in sin_literales or "/*" in sin_literales or "*/" in sin_literales:
        raise SQLSecurityError("No se permiten comentarios SQL en las consultas generadas.")

    if ";" in sin_literales:
        raise SQLSecurityError("No se permiten múltiples sentencias SQL en una misma consulta.")

    if not re.match(r"^(SELECT|WITH)\b", sin_literales, re.IGNORECASE):
        raise SQLSecurityError(
            "Solo se permiten consultas de lectura que comiencen con SELECT o WITH."
        )

    match_prohibido = FORBIDDEN_SQL_PATTERN.search(sin_literales)
    if match_prohibido:
        palabra = re.sub(r"\s+", " ", match_prohibido.group(1)).upper()
        raise SQLSecurityError(f"Operación SQL no permitida detectada: {palabra}.")

    return limpia


def limitar_resultados(resultados: list, max_filas: int = 100) -> tuple[list, bool]:
    """Acota el volumen de filas en memoria para proteger la UI."""
    if len(resultados) > max_filas:
        return resultados[:max_filas], True
    return resultados, False


def formatear_respuesta_texto(resultados: list) -> str:
    """Genera el texto de respaldo en Markdown a partir de las filas retornadas."""
    if not resultados or resultados[0][0] is None:
        return "No se encontraron resultados para esa consulta."

    lineas: list[str] = []
    for fila in resultados:
        if len(fila) == 1:
            lineas.append(f"- {fila[0]}")
        elif len(fila) == 2:
            lineas.append(f"- {fila[0]}: {fila[1]}")
        else:
            lineas.append("- " + " | ".join(str(col) for col in fila))
    return "\n".join(lineas)


def formatear_valor_kpi(valor: object, es_moneda: bool = False) -> str:
    """Formatea valores numéricos con separador de miles estilo argentino."""
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, float):
        if es_moneda:
            return f"${valor:,.0f}".replace(",", ".")
        return f"{valor:,}".replace(",", ".")
    if isinstance(valor, int):
        return f"{valor:,}".replace(",", ".")
    return str(valor)


def init_history_db(db_path: str = "chat_history.db") -> sqlite3.Connection:
    """Inicializa la base SQLite de historial conversacional."""
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def guardar_mensaje_db(conn: sqlite3.Connection, role: str, content_obj: object) -> None:
    """Serializa el mensaje (texto o diccionario JSON) y lo persiste en SQLite."""
    if isinstance(content_obj, dict):
        content_str = json.dumps(content_obj, default=str)
    else:
        content_str = str(content_obj)

    conn.execute(
        "INSERT INTO chat_history (role, content) VALUES (?, ?)",
        (role, content_str),
    )
    conn.commit()


def cargar_historial_db(conn: sqlite3.Connection) -> list[dict]:
    """Recupera el historial y deserializa respuestas estructuradas del asistente."""
    cursor = conn.execute("SELECT role, content FROM chat_history ORDER BY id ASC")
    mensajes: list[dict] = []
    for role, content_str in cursor.fetchall():
        content_obj: object = content_str
        if role == "assistant" and content_str.strip().startswith("{"):
            try:
                content_obj = json.loads(content_str)
            except json.JSONDecodeError:
                content_obj = content_str
        mensajes.append({"role": role, "content": content_obj})
    return mensajes


def limpiar_historial_db(conn: sqlite3.Connection) -> None:
    """Elimina todos los registros del historial de chat."""
    conn.execute("DELETE FROM chat_history")
    conn.commit()
