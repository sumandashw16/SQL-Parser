"""
Canonical AST schema for mysql-lite.

Both the hand-written SQL parser (parser.py) and the LLM-based
NL parser (llm.py) must produce dicts matching these shapes.
The executor only ever consumes this schema.

---------------------------------------------------------------------
SELECT
{
  "type": "SELECT",
  "table": "students",
  "columns": ["name", "score"],   # or ["*"]
  "where": <condition> | None,
  "order_by": {"field": "score", "order": "asc"|"desc"} | None,
  "limit": int | None
}

INSERT
{
  "type": "INSERT",
  "table": "students",
  "values": {"name": "Asha", "score": 88.5, "subject": "Math"}
}

UPDATE
{
  "type": "UPDATE",
  "table": "students",
  "set": {"score": 90},
  "where": <condition> | None
}

DELETE
{
  "type": "DELETE",
  "table": "students",
  "where": <condition> | None
}

<condition> is one of:
  {"field": "score", "op": "=" | "!=" | ">" | "<" | ">=" | "<=", "value": <literal>}
  {"and": [<condition>, <condition>, ...]}
  {"or":  [<condition>, <condition>, ...]}
---------------------------------------------------------------------
"""

VALID_DTYPES = {"int", "float", "string", "bool"}
VALID_OPS = {"=", "!=", ">", "<", ">=", "<="}
VALID_STMT_TYPES = {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE_TABLE"}

class ASTValidationError(Exception):
    pass


def _fail(msg):
    raise ASTValidationError(msg)


def validate_condition(cond, path="where"):
    if not isinstance(cond, dict):
        _fail(f"{path}: condition must be an object, got {type(cond).__name__}")

    if "and" in cond or "or" in cond:
        key = "and" if "and" in cond else "or"
        if len(cond) != 1:
            _fail(f"{path}.{key}: combinator object must only contain '{key}'")
        items = cond[key]
        if not isinstance(items, list) or len(items) < 1:
            _fail(f"{path}.{key}: must be a non-empty list of conditions")
        for i, sub in enumerate(items):
            validate_condition(sub, path=f"{path}.{key}[{i}]")
        return

    for required in ("field", "op", "value"):
        if required not in cond:
            _fail(f"{path}: leaf condition missing '{required}'")
    if cond["op"] not in VALID_OPS:
        _fail(f"{path}: invalid op '{cond['op']}', must be one of {VALID_OPS}")
    if not isinstance(cond["field"], str):
        _fail(f"{path}: 'field' must be a string")


def validate_ast(ast):
    if not isinstance(ast, dict):
        _fail(f"AST must be an object, got {type(ast).__name__}")

    stmt_type = ast.get("type")
    if stmt_type not in VALID_STMT_TYPES:
        _fail(f"Unknown/missing statement type: {stmt_type!r}. Must be one of {VALID_STMT_TYPES}")

    if "table" not in ast or not isinstance(ast["table"], str) or not ast["table"]:
        _fail(f"{stmt_type}: 'table' must be a non-empty string")

        if stmt_type == "CREATE_TABLE":
            cols = ast.get("columns")
            if not isinstance(cols, list) or len(cols) == 0:
                _fail("CREATE_TABLE: 'columns' must be a non-empty list")
            seen = set()
            for i, col in enumerate(cols):
                if not isinstance(col, dict) or "name" not in col or "dtype" not in col:
                    _fail(f"CREATE_TABLE.columns[{i}]: must have 'name' and 'dtype'")
                if col["dtype"] not in VALID_DTYPES:
                    _fail(f"CREATE_TABLE.columns[{i}]: invalid dtype '{col['dtype']}', must be one of {VALID_DTYPES}")
                if col["name"] in seen:
                    _fail(f"CREATE_TABLE.columns[{i}]: duplicate column name '{col['name']}'")
                seen.add(col["name"])
    
        elif stmt_type == "INSERT":
            rows = ast.get("values")
            if not isinstance(rows, list) or len(rows) == 0:
                _fail("INSERT: 'values' must be a non-empty list of row objects")
            first_keys = None
            for i, row in enumerate(rows):
                if not isinstance(row, dict) or len(row) == 0:
                    _fail(f"INSERT.values[{i}]: each row must be a non-empty object")
                if first_keys is None:
                    first_keys = set(row.keys())
                elif set(row.keys()) != first_keys:
                    _fail(f"INSERT.values[{i}]: all rows must have the same columns as row 0")

    elif stmt_type == "SELECT":
        cols = ast.get("columns")
        if not isinstance(cols, list) or len(cols) == 0:
            _fail("SELECT: 'columns' must be a non-empty list (use ['*'] for all)")
        where = ast.get("where")
        if where is not None:
            validate_condition(where)
        order_by = ast.get("order_by")
        if order_by is not None:
            if not isinstance(order_by, dict) or "field" not in order_by:
                _fail("SELECT.order_by: must have 'field'")
            order = order_by.get("order", "asc")
            if order not in ("asc", "desc"):
                _fail("SELECT.order_by.order: must be 'asc' or 'desc'")
        limit = ast.get("limit")
        if limit is not None and (not isinstance(limit, int) or limit < 0):
            _fail("SELECT.limit: must be a non-negative integer")

    elif stmt_type == "UPDATE":
        set_clause = ast.get("set")
        if not isinstance(set_clause, dict) or len(set_clause) == 0:
            _fail("UPDATE: 'set' must be a non-empty object")
        where = ast.get("where")
        if where is not None:
            validate_condition(where)

    elif stmt_type == "DELETE":
        where = ast.get("where")
        if where is not None:
            validate_condition(where)

    return True