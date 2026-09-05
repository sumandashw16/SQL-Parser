"""
Converts a validated AST dict into a real SQL string + parameter values,
ready to run on MySQL via mysql-connector-python.

We use %s placeholders and a separate params list/tuple instead of
string-formatting values directly into the SQL text. This is standard
practice (prevents SQL injection) and mysql-connector handles it natively.
"""


def _build_where(where):
    """Returns (sql_fragment, params_list). sql_fragment has no leading 'WHERE'."""
    if where is None:
        return "", []

    if "and" in where or "or" in where:
        key = "and" if "and" in where else "or"
        parts = []
        params = []
        for sub in where[key]:
            frag, sub_params = _build_where(sub)
            parts.append(f"({frag})")
            params.extend(sub_params)
        joiner = " AND " if key == "and" else " OR "
        return joiner.join(parts), params

    # leaf condition
    field = where["field"]
    op = where["op"]
    value = where["value"]
    return f"{field} {op} %s", [value]


def ast_to_sql(ast):
    """
    Returns (sql_string, params_tuple) ready for cursor.execute(sql, params).
    """
    stmt_type = ast["type"]
    table = ast["table"]

    if stmt_type == "SELECT":
        cols = ast["columns"]
        col_str = "*" if cols == ["*"] else ", ".join(cols)
        sql = f"SELECT {col_str} FROM {table}"
        params = []

        where = ast.get("where")
        if where is not None:
            frag, where_params = _build_where(where)
            sql += f" WHERE {frag}"
            params.extend(where_params)

        order_by = ast.get("order_by")
        if order_by is not None:
            sql += f" ORDER BY {order_by['field']} {order_by.get('order', 'asc').upper()}"

        limit = ast.get("limit")
        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        return sql, tuple(params)

    elif stmt_type == "INSERT":
        values = ast["values"]
        cols = list(values.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_str = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"
        params = tuple(values[c] for c in cols)
        return sql, params

    elif stmt_type == "UPDATE":
        set_clause = ast["set"]
        set_cols = list(set_clause.keys())
        set_str = ", ".join(f"{c} = %s" for c in set_cols)
        params = [set_clause[c] for c in set_cols]

        sql = f"UPDATE {table} SET {set_str}"

        where = ast.get("where")
        if where is not None:
            frag, where_params = _build_where(where)
            sql += f" WHERE {frag}"
            params.extend(where_params)

        return sql, tuple(params)

    elif stmt_type == "DELETE":
        sql = f"DELETE FROM {table}"
        params = []

        where = ast.get("where")
        if where is not None:
            frag, where_params = _build_where(where)
            sql += f" WHERE {frag}"
            params.extend(where_params)

        return sql, tuple(params)

    else:
        raise ValueError(f"Unsupported statement type: {stmt_type}")