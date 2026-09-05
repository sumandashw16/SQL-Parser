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
    Raises Error on failure (caught by the caller in app.py).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)

        if sql.strip().upper().startswith("SELECT"):
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