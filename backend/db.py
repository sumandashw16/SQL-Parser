"""
MySQL connection handling. Opens a connection using config.py credentials
and provides a simple function to run a (sql, params) pair and get results back.
"""

import mysql.connector
from mysql.connector import Error
import config


def get_connection():
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
    )


def run_query(sql, params):
    """
    Runs a SQL statement with parameters.
    For SELECT: returns (columns, rows) where rows is a list of tuples.
    For INSERT/UPDATE/DELETE: returns (None, affected_row_count).
    For multi-row INSERT, params is a list of tuples -> uses executemany.
    Raises Error on failure (caught by the caller in app.py).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        is_multi_row = isinstance(params, list)
        if is_multi_row:
            cursor.executemany(sql, params)
        else:
            cursor.execute(sql, params)

        if sql.strip().upper().startswith(("SELECT", "SHOW")):
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            cursor.close()
            return columns, rows
        else:
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
            return None, affected
    finally:
        conn.close()


def test_connection():
    """Quick sanity check you can call to confirm config.py is correct."""
    try:
        conn = get_connection()
        conn.close()
        return True, "Connected successfully"
    except Error as e:
        return False, str(e)

def get_live_schema():
    """
    Queries MySQL itself for all tables and their columns in the current database.
    Returns a human-readable string describing the schema, used to keep the
    LLM's knowledge in sync with tables that were created after the app started
    (including ones created via CREATE_TABLE through this same app).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]

        schema_lines = []
        for table in tables:
            cursor.execute(f"DESCRIBE {table}")
            columns = cursor.fetchall()  # each row: (Field, Type, Null, Key, Default, Extra)
            schema_lines.append(f"Table: {table}")
            for col in columns:
                field_name, sql_type = col[0], col[1]
                schema_lines.append(f"  - {field_name} ({sql_type})")
            schema_lines.append("")  # blank line between tables

        cursor.close()
        return "\n".join(schema_lines)
    finally:
        conn.close()