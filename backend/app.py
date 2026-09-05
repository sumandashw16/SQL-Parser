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


def is_destructive(ast):
    """
    Checks whether an AST represents an operation that could cause irreversible
    data loss. Returns (dangerous: bool, warning: str | None).

    Flagged as destructive:
      - DROP_TABLE          : deletes the entire table permanently
      - DELETE with no WHERE: removes every row in the table
      - UPDATE with no WHERE: overwrites every row in the table
    """
    stmt_type = ast.get("type")
    if stmt_type == "DROP_TABLE":
        table = ast.get("table", "unknown")
        return True, (
            f"This will permanently DELETE the entire table '{table}' "
            f"and all its data. This cannot be undone."
        )
    if stmt_type == "DELETE" and ast.get("where") is None:
        table = ast.get("table", "unknown")
        return True, (
            f"No WHERE clause — this will DELETE every row in '{table}'."
        )
    if stmt_type == "UPDATE" and ast.get("where") is None:
        table = ast.get("table", "unknown")
        return True, (
            f"No WHERE clause — this will UPDATE every row in '{table}'."
        )
    return False, None

@app.route("/query/sql", methods=["POST"])
def query_sql():
    data = request.get_json(force=True)
    sql_text  = data.get("query", "").strip()
    confirmed = data.get("confirmed", False)

    if not sql_text:
        return jsonify({"error": "Empty query"}), 400

    try:
        ast = parse_sql(sql_text)

        # Before executing, check if this operation is destructive.
        # If so, and the user hasn't explicitly confirmed, return a
        # needs_confirm response — MySQL is NOT touched at this point.
        dangerous, warning = is_destructive(ast)
        if dangerous and not confirmed:
            validate_ast(ast)          # catch schema errors before asking
            sql, _ = ast_to_sql(ast)   # generate SQL just for display
            return jsonify({"needs_confirm": True, "sql": sql, "warning": warning})

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
    confirmed    = data.get("confirmed", False)

    if not english_text:
        return jsonify({"error": "Empty query"}), 400

    try:
        ast = english_to_ast(english_text)

        # Same destructive-op gate as the SQL endpoint.
        # Note: the LLM call already happened, so we know the intent.
        # We show the generated SQL so the user can see exactly what will run.
        dangerous, warning = is_destructive(ast)
        if dangerous and not confirmed:
            sql, _ = ast_to_sql(ast)
            return jsonify({"needs_confirm": True, "sql": sql, "warning": warning, "ast": ast})

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