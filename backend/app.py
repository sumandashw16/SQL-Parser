"""
Flask backend for mysql-lite.

Two endpoints:
  POST /query/sql  -> typed SQL text goes through lexer+parser
  POST /query/nl   -> English goes through Gemini (llm.py)

Both converge on the same validated AST -> ast_to_sql -> MySQL execution.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS

from lexer import LexerError
from parser import parse_sql, ParseError
from ast_nodes import validate_ast, ASTValidationError
from ast_to_sql import ast_to_sql
from llm import english_to_ast
import db

app = Flask(__name__)
CORS(app)  # allow the frontend (served separately) to call this API


def execute_ast(ast):
    """Shared final step: validate -> convert to SQL -> run on MySQL -> format result."""
    validate_ast(ast)
    sql, params = ast_to_sql(ast)
    columns, result = db.run_query(sql, params)

    if columns is not None:
        # SELECT: result is a list of tuples
        rows = [dict(zip(columns, row)) for row in result]
        return {
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }
    else:
        # INSERT/UPDATE/DELETE: result is affected row count
        return {
            "sql": sql,
            "columns": None,
            "rows": None,
            "affected_rows": result,
        }


@app.route("/query/sql", methods=["POST"])
def query_sql():
    data = request.get_json(force=True)
    sql_text = data.get("query", "").strip()

    if not sql_text:
        return jsonify({"error": "Empty query"}), 400

    try:
        ast = parse_sql(sql_text)
        result = execute_ast(ast)
        return jsonify(result)
    except LexerError as e:
        return jsonify({"error": f"Syntax error (lexer): {e}"}), 400
    except ParseError as e:
        return jsonify({"error": f"Syntax error (parser): {e}"}), 400
    except ASTValidationError as e:
        return jsonify({"error": f"Invalid query: {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@app.route("/query/nl", methods=["POST"])
def query_nl():
    data = request.get_json(force=True)
    english_text = data.get("query", "").strip()

    if not english_text:
        return jsonify({"error": "Empty query"}), 400

    try:
        ast = english_to_ast(english_text)
        result = execute_ast(ast)
        result["ast"] = ast  # include so frontend can show "here's what I understood"
        return jsonify(result)
    except ASTValidationError as e:
        return jsonify({"error": f"Model produced an invalid query: {e}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@app.route("/health", methods=["GET"])
def health():
    ok, msg = db.test_connection()
    return jsonify({"db_connected": ok, "message": msg})


if __name__ == "__main__":
    app.run(debug=True, port=5000)