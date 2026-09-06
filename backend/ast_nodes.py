"""
Canonical AST schema for mysql-lite.

Both the hand-written SQL parser (parser.py) and the LLM-based
NL parser (llm.py) must produce dicts matching these shapes.
The executor only ever consumes this schema.

---------------------------------------------------------------------
SELECT (plain)
{
  "type": "SELECT",
  "table": "students",
  "columns": ["name", "score"],   # or ["*"]
  "where": <condition> | None,
  "order_by": {"field": "score", "order": "asc"|"desc"} | None,
  "limit": int | None
}

SELECT with aggregates
{
  "type": "SELECT",
  "table": "students",
  "columns": ["subject"],          # non-aggregate columns (GROUP BY columns)
  "aggregates": [                   # optional; omit or [] for plain SELECT
    {"func": "AVG", "field": "score",  "alias": "avg_score"},
    {"func": "COUNT", "field": "*",   "alias": "total"}
  ],
  "where": <condition> | None,     # filter BEFORE grouping
  "group_by": ["subject"],          # optional list of fields
  "having": <condition> | None,    # filter AFTER grouping (same shape as where)
  "order_by": {"field": "avg_score", "order": "desc"} | None,
  "limit": int | None
}

Valid aggregate functions: COUNT, SUM, AVG, MIN, MAX
Use field="*" only with COUNT.

INSERT
{
  "type": "INSERT",
  "table": "students",
  "values": [{"name": "Asha", "score": 88.5, "subject": "Math"}, ...]
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

CREATE_TABLE
{
  "type": "CREATE_TABLE",
  "table": "teachers",
  "columns": [{"name": "name", "dtype": "string"}, ...]
}

ALTER_TABLE (four possible actions)
{
  "type": "ALTER_TABLE", "table": "teachers", "action": "ADD_COLUMN",
  "column": {"name": "email", "dtype": "string"}
}
{
  "type": "ALTER_TABLE", "table": "teachers", "action": "DROP_COLUMN",
  "column_name": "email"
}
{
  "type": "ALTER_TABLE", "table": "teachers", "action": "RENAME_COLUMN",
  "old_name": "dept", "new_name": "department"
}
{
  "type": "ALTER_TABLE", "table": "teachers", "action": "MODIFY_COLUMN",
  "column": {"name": "age", "dtype": "float"}
}

<condition> is one of:
  {"field": "score", "op": "=" | "!=" | ">" | "<" | ">=" | "<=", "value": <literal>}
  {"field": "name",  "op": "LIKE",    "value": "%ali%"}
  {"field": "id",    "op": "IN",      "values": [1, 2, 3]}
  {"field": "score", "op": "BETWEEN", "low": 50, "high": 90}
  {"field": "email", "op": "IS_NULL"}
  {"field": "email", "op": "IS_NOT_NULL"}
  {"not": <condition>}
  {"and": [<condition>, <condition>, ...]}
  {"or":  [<condition>, <condition>, ...]}
---------------------------------------------------------------------
"""

VALID_DTYPES = {"int", "float", "string", "text", "bool", "date", "datetime", "timestamp"}
VALID_OPS = {"=", "!=", ">", "<", ">=", "<="}
VALID_AGG_FUNCS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
VALID_STMT_TYPES = {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE_TABLE", "ALTER_TABLE", "SHOW_TABLES", "DROP_TABLE", "DESCRIBE"}
VALID_ALTER_ACTIONS = {"ADD_COLUMN", "DROP_COLUMN", "RENAME_COLUMN", "MODIFY_COLUMN"}


class ASTValidationError(Exception):
    pass


def _fail(msg):
    raise ASTValidationError(msg)


def validate_condition(cond, path="where"):
    if not isinstance(cond, dict):
        _fail(f"{path}: condition must be an object, got {type(cond).__name__}")

    # NOT wrapper
    if "not" in cond:
        if len(cond) != 1:
            _fail(f"{path}.not: object must only contain 'not'")
        validate_condition(cond["not"], path=f"{path}.not")
        return

    # AND / OR combinators
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

    # All leaf conditions require "field" and "op"
    if "field" not in cond or not isinstance(cond["field"], str):
        _fail(f"{path}: leaf condition must have a string 'field'")
    if "op" not in cond:
        _fail(f"{path}: leaf condition missing 'op'")

    op = cond["op"]

    if op in VALID_OPS:
        # standard comparison: requires "value" or "right_field"
        if "value" not in cond and "right_field" not in cond:
            _fail(f"{path}: op '{op}' requires a 'value' or 'right_field'")
        if "right_field" in cond and not isinstance(cond["right_field"], str):
            _fail(f"{path}: 'right_field' must be a string")

    elif op == "LIKE":
        if "value" not in cond or not isinstance(cond["value"], str):
            _fail(f"{path}: LIKE requires a string 'value' (the pattern)")

    elif op == "IN":
        vals = cond.get("values")
        if not isinstance(vals, list) or len(vals) == 0:
            _fail(f"{path}: IN requires a non-empty 'values' list")

    elif op == "BETWEEN":
        if "low" not in cond or "high" not in cond:
            _fail(f"{path}: BETWEEN requires 'low' and 'high'")

    elif op in ("IS_NULL", "IS_NOT_NULL"):
        pass  # only needs "field"

    else:
        _fail(f"{path}: invalid op '{op}', must be one of {VALID_OPS | {'LIKE','IN','BETWEEN','IS_NULL','IS_NOT_NULL'}}")


def validate_ast(ast):
    if not isinstance(ast, dict):
        _fail(f"AST must be an object, got {type(ast).__name__}")

    stmt_type = ast.get("type")
    if stmt_type not in VALID_STMT_TYPES:
        _fail(f"Unknown/missing statement type: {stmt_type!r}. Must be one of {VALID_STMT_TYPES}")
    if stmt_type != "SHOW_TABLES":
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



        elif stmt_type == "ALTER_TABLE":
            action = ast.get("action")
            if action not in VALID_ALTER_ACTIONS:
                _fail(f"ALTER_TABLE: invalid action '{action}', must be one of {VALID_ALTER_ACTIONS}")

            if action == "ADD_COLUMN":
                cols = ast.get("columns")
                if not isinstance(cols, list) or len(cols) == 0:
                    _fail("ALTER_TABLE ADD_COLUMN: 'columns' must be a non-empty list")
                for i, col in enumerate(cols):
                    if not isinstance(col, dict) or "name" not in col or "dtype" not in col:
                        _fail(f"ALTER_TABLE ADD_COLUMN columns[{i}]: must be an object with 'name' and 'dtype'")
                    if col["dtype"] not in VALID_DTYPES:
                        _fail(f"ALTER_TABLE ADD_COLUMN columns[{i}]: invalid dtype '{col['dtype']}'")

            elif action == "DROP_COLUMN":
                cols = ast.get("column_names")
                if not isinstance(cols, list) or len(cols) == 0:
                    _fail("ALTER_TABLE DROP_COLUMN: 'column_names' must be a non-empty list of strings")
                for i, col in enumerate(cols):
                    if not isinstance(col, str) or not col:
                        _fail(f"ALTER_TABLE DROP_COLUMN column_names[{i}]: must be a non-empty string")

            elif action == "RENAME_COLUMN":
                cols = ast.get("columns")
                if not isinstance(cols, list) or len(cols) == 0:
                    _fail("ALTER_TABLE RENAME_COLUMN: 'columns' must be a non-empty list")
                for i, col in enumerate(cols):
                    if not isinstance(col, dict) or "old_name" not in col or "new_name" not in col:
                        _fail(f"ALTER_TABLE RENAME_COLUMN columns[{i}]: must be an object with 'old_name' and 'new_name'")
                    if not isinstance(col["old_name"], str) or not col["old_name"]:
                        _fail(f"ALTER_TABLE RENAME_COLUMN columns[{i}]: 'old_name' must be a non-empty string")
                    if not isinstance(col["new_name"], str) or not col["new_name"]:
                        _fail(f"ALTER_TABLE RENAME_COLUMN columns[{i}]: 'new_name' must be a non-empty string")

            elif action == "MODIFY_COLUMN":
                cols = ast.get("columns")
                if not isinstance(cols, list) or len(cols) == 0:
                    _fail("ALTER_TABLE MODIFY_COLUMN: 'columns' must be a non-empty list")
                for i, col in enumerate(cols):
                    if not isinstance(col, dict) or "name" not in col or "dtype" not in col:
                        _fail(f"ALTER_TABLE MODIFY_COLUMN columns[{i}]: must be an object with 'name' and 'dtype'")
                    if col["dtype"] not in VALID_DTYPES:
                        _fail(f"ALTER_TABLE MODIFY_COLUMN columns[{i}]: invalid dtype '{col['dtype']}', must be one of {VALID_DTYPES}")

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

            joins = ast.get("joins")
            if joins is not None:
                if not isinstance(joins, list):
                    _fail("SELECT.joins: must be a list")
                for i, j in enumerate(joins):
                    if not isinstance(j, dict):
                        _fail(f"SELECT.joins[{i}]: must be an object")
                    if j.get("type") not in ("INNER", "LEFT", "RIGHT", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN"):
                        _fail(f"SELECT.joins[{i}]: 'type' must be INNER, LEFT, or RIGHT (or include JOIN)")
                    if "table" not in j or not isinstance(j["table"], str) or not j["table"]:
                        _fail(f"SELECT.joins[{i}]: 'table' must be a non-empty string")
                    if "on" not in j:
                        _fail(f"SELECT.joins[{i}]: must have 'on' condition")
                    validate_condition(j["on"], path=f"SELECT.joins[{i}].on")

            # Aggregates (optional)
            aggregates = ast.get("aggregates")
            if aggregates is not None:
                if not isinstance(aggregates, list):
                    _fail("SELECT.aggregates: must be a list")
                for i, agg in enumerate(aggregates):
                    if not isinstance(agg, dict):
                        _fail(f"SELECT.aggregates[{i}]: must be an object")
                    if agg.get("func") not in VALID_AGG_FUNCS:
                        _fail(f"SELECT.aggregates[{i}]: 'func' must be one of {VALID_AGG_FUNCS}")
                    if "field" not in agg or not isinstance(agg["field"], str):
                        _fail(f"SELECT.aggregates[{i}]: 'field' must be a string (use '*' for COUNT(*))")
                    if "alias" not in agg or not isinstance(agg["alias"], str):
                        _fail(f"SELECT.aggregates[{i}]: 'alias' must be a non-empty string")

            # GROUP BY (optional, but required if aggregates are present)
            group_by = ast.get("group_by")
            if group_by is not None:
                if not isinstance(group_by, list) or len(group_by) == 0:
                    _fail("SELECT.group_by: must be a non-empty list of field names")
                for i, f in enumerate(group_by):
                    if not isinstance(f, str) or not f:
                        _fail(f"SELECT.group_by[{i}]: must be a non-empty string")

            # HAVING (optional condition applied after GROUP BY)
            having = ast.get("having")
            if having is not None:
                validate_condition(having, path="having")

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