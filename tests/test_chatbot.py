import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from sql_engine import (
    SQLSecurityError,
    cargar_historial_db,
    extraer_texto_respuesta_llm,
    formatear_respuesta_texto,
    formatear_valor_kpi,
    guardar_mensaje_db,
    init_history_db,
    limitar_resultados,
    limpiar_historial_db,
    limpiar_sql_crudo,
    parsear_respuesta_llm,
    validar_sql_seguro,
)


def test_parsear_respuesta_llm_json_limpio_y_markdown() -> None:
    respuesta_sucia = (
        "Aquí tienes el resultado:\n"
        "```json\n"
        '{"sql": "SELECT Producto, Unidades_Vendidas FROM ventas;", "grafico": "BARRAS"}\n'
        "```"
    )
    sql, grafico = parsear_respuesta_llm(respuesta_sucia)
    assert sql == "SELECT Producto, Unidades_Vendidas FROM ventas;"
    assert grafico == "barras"

    # Si devuelve un tipo de gráfico desconocido, debe caer a "texto"
    _, grafico_desconocido = parsear_respuesta_llm('{"sql": "SELECT 1", "grafico": "3d_radar"}')
    assert grafico_desconocido == "texto"

    # Fallback a SQL plano sin JSON
    sql_plano, grafico_plano = parsear_respuesta_llm("```sql\nSELECT COUNT(*) FROM ventas\n```")
    assert sql_plano == "SELECT COUNT(*) FROM ventas"
    assert grafico_plano == "texto"


def test_limpiar_sql_crudo_remueve_prefijo_y_markdown() -> None:
    crudo = "```sql\nSQL: SELECT * FROM ventas;\n```"
    assert limpiar_sql_crudo(crudo) == "SELECT * FROM ventas;"


def test_validar_sql_seguro_acepta_select_cte_y_literales() -> None:
    assert validar_sql_seguro("SELECT Producto FROM ventas;") == "SELECT Producto FROM ventas"

    cte = "WITH top_ventas AS (SELECT Producto FROM ventas) SELECT * FROM top_ventas;"
    assert validar_sql_seguro(cte).startswith("WITH top_ventas")

    # Palabras restringidas dentro de un literal de texto no deben disparar falso positivo
    msg = "SELECT 'No se permite DROP ni DELETE en este reporte.' AS Mensaje;"
    assert validar_sql_seguro(msg) == msg[:-1]


@pytest.mark.parametrize(
    "query_maliciosa",
    [
        "",
        "Hola, las ventas fueron muy buenas",
        "DROP TABLE ventas",
        "DELETE FROM ventas WHERE Producto = 'Zapatos'",
        "UPDATE ventas SET Unidades_Vendidas = 0",
        "INSERT INTO ventas VALUES ('Botas', 10)",
        "ALTER TABLE ventas ADD COLUMN x INT",
        "PRAGMA table_info(ventas)",
        "SELECT * FROM ventas; DROP TABLE ventas;",
        "SELECT * FROM ventas -- comentario sospechoso",
        "SELECT * FROM ventas /* bloque sospechoso */",
    ],
)
def test_validar_sql_seguro_bloquea_inyeccion_y_ddl_dml(query_maliciosa: str) -> None:
    with pytest.raises(SQLSecurityError):
        validar_sql_seguro(query_maliciosa)


def test_limitar_resultados_y_formatear_texto() -> None:
    filas = [[f"Prod-{i}", i] for i in range(150)]
    recortadas, fue_truncado = limitar_resultados(filas, max_filas=100)
    assert len(recortadas) == 100
    assert fue_truncado is True

    sin_corte, fue_truncado_2 = limitar_resultados([["Zapatos", 50]], max_filas=100)
    assert sin_corte == [["Zapatos", 50]]
    assert fue_truncado_2 is False

    assert formatear_respuesta_texto([]) == "No se encontraron resultados para esa consulta."
    assert formatear_respuesta_texto([[None]]) == "No se encontraron resultados para esa consulta."
    assert formatear_respuesta_texto([["Guantes", 42]]) == "- Guantes: 42"
    assert formatear_respuesta_texto([["Guantes", 42, 15.5]]) == "- Guantes | 42 | 15.5"


def test_formatear_valor_kpi() -> None:
    assert formatear_valor_kpi(12500) == "12.500"
    assert formatear_valor_kpi(12500.75, es_moneda=True) == "$12.501"
    assert formatear_valor_kpi("2026-11-24") == "2026-11-24"
    assert formatear_valor_kpi(True) == "True"


def test_historial_sqlite_persistencia_y_limpieza(tmp_path: Path) -> None:
    db_file = str(tmp_path / "test_history.db")
    conn = init_history_db(db_file)
    try:
        guardar_mensaje_db(conn, "user", "¿Producto más vendido?")
        payload_asistente = {
            "query": "SELECT Producto, Unidades_Vendidas FROM ventas LIMIT 1",
            "texto": "- Medias: 120",
            "grafico": "barras",
            "resultados": [["Medias", 120]],
            "latencia": 0.42,
            "entorno": "LOCAL",
        }
        guardar_mensaje_db(conn, "assistant", payload_asistente)

        historial = cargar_historial_db(conn)
        assert len(historial) == 2
        assert historial[0] == {"role": "user", "content": "¿Producto más vendido?"}
        assert historial[1]["content"]["grafico"] == "barras"
        assert historial[1]["content"]["resultados"] == [["Medias", 120]]

        limpiar_historial_db(conn)
        assert cargar_historial_db(conn) == []
    finally:
        conn.close()


def test_pipeline_sql_en_memoria_end_to_end() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE ventas (Producto TEXT, Unidades_Vendidas INTEGER)")
        conn.executemany(
            "INSERT INTO ventas VALUES (?, ?)",
            [("Zapatos", 40), ("Medias", 120), ("Guantes", 65)],
        )

        respuesta_mock = (
            '{"sql": "SELECT Producto, Unidades_Vendidas FROM ventas '
            'ORDER BY Unidades_Vendidas DESC LIMIT 1;", "grafico": "barras"}'
        )
        query_cruda, grafico = parsear_respuesta_llm(respuesta_mock)
        query_segura = validar_sql_seguro(query_cruda)

        resultados = conn.execute(query_segura).fetchall()
        assert grafico == "barras"
        assert resultados == [("Medias", 120)]
        assert formatear_respuesta_texto(resultados) == "- Medias: 120"
    finally:
        conn.close()


def test_parsear_respuesta_llm_claves_mayusculas_y_multilinea() -> None:
    respuesta = '{"SQL": "SELECT Producto\nFROM ventas\nLIMIT 1;", "GRAFICO": "METRICA"}'
    sql, grafico = parsear_respuesta_llm(respuesta)
    assert sql.startswith("SELECT Producto")
    assert grafico == "metrica"


def test_extraer_texto_respuesta_llm_aimessage_y_reasoning() -> None:
    assert extraer_texto_respuesta_llm("  SELECT 1  ") == "SELECT 1"

    msg_bloques = SimpleNamespace(content=[{"type": "text", "text": '{"sql": "SELECT 1"}'}])
    assert extraer_texto_respuesta_llm(msg_bloques) == '{"sql": "SELECT 1"}'

    esperado = '{"sql": "SELECT 2", "grafico": "metrica"}'
    msg_reasoning = SimpleNamespace(
        content="",
        additional_kwargs={"reasoning_content": esperado},
    )
    assert extraer_texto_respuesta_llm(msg_reasoning) == esperado
