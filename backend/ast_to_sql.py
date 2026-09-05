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

    # NOT wrapper
    if "not" in where:
        frag, params = _build_where(where["not"])
        return f"NOT ({frag})", params

    # AND / OR combinators
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

    # Leaf condition
    field = where["field"]
    op    = where["op"]

    if op == "IS_NULL":
        return f"{field} IS NULL", []

    if op == "IS_NOT_NULL":
        return f"{field} IS NOT NULL", []

    if op == "LIKE":
        return f"{field} LIKE %s", [where["value"]]

    if op == "IN":
        placeholders = ", ".join(["%s"] * len(where["values"]))
        return f"{field} IN ({placeholders})", list(where["values"])

    if op == "BETWEEN":
        return f"{field} BETWEEN %s AND %s", [where["low"], where["high"]]

    # Standard comparison (=, !=, >, <, >=, <=)
    return f"{field} {op} %s", [where["value"]]



def ast_to_sql(ast):
    """
    Returns (sql_string, params_tuple) ready for cursor.execute(sql, params).
    """
    stmt_type = ast["type"]

    # SHOW_TABLES has no "table" field -- handle it before we ever access ast["table"]
    if stmt_type == "SHOW_TABLES":
        return "SHOW TABLES", ()

    table = ast["table"]

    if stmt_type == "DROP_TABLE":
        return f"DROP TABLE {table}", ()
    
    DTYPE_TO_SQL = {"int": "INT", "float": "FLOAT", "string": "VARCHAR(255)", "bool": "BOOLEAN"}

    if stmt_type == "CREATE_TABLE":
        cols = ast["columns"]
        col_defs = ", ".join(f"{c['name']} {DTYPE_TO_SQL[c['dtype']]}" for c in cols)
        sql = f"CREATE TABLE {table} ({col_defs})"
        return sql, ()

    elif stmt_type == "ALTER_TABLE":
        action = ast["action"]

        if action == "ADD_COLUMN":
            col = ast["column"]
            sql = f"ALTER TABLE {table} ADD COLUMN {col['name']} {DTYPE_TO_SQL[col['dtype']]}"
            return sql, ()

        elif action == "DROP_COLUMN":
            sql = f"ALTER TABLE {table} DROP COLUMN {ast['column_name']}"
            return sql, ()

        elif action == "RENAME_COLUMN":
            # MySQL 8.0+ supports RENAME COLUMN directly
            sql = f"ALTER TABLE {table} RENAME COLUMN {ast['old_name']} TO {ast['new_name']}"
            return sql, ()

        elif action == "MODIFY_COLUMN":
            col = ast["column"]
            sql = f"ALTER TABLE {table} MODIFY COLUMN {col['name']} {DTYPE_TO_SQL[col['dtype']]}"
            return sql, ()

    elif stmt_type == "SELECT":
        cols = ast["columns"]
        aggregates = ast.get("aggregates") or []

        # Build the SELECT list
        select_parts = []

        # Non-aggregate columns (omit if the only column is "*" and there are aggregates)
        if not (cols == ["*"] and aggregates):
            select_parts += cols if cols != ["*"] else ["*"]

        # Aggregate expressions: AVG(score) AS avg_score
        for agg in aggregates:
            field_expr = agg["field"]  # could be "*" for COUNT(*)
            expr = f"{agg['func']}({field_expr}) AS {agg['alias']}"
            select_parts.append(expr)

        col_str = ", ".join(select_parts) if select_parts else "*"
        sql = f"SELECT {col_str} FROM {table}"
        params = []

        # WHERE (filters before grouping)
        where = ast.get("where")
        if where is not None:
            frag, where_params = _build_where(where)
            sql += f" WHERE {frag}"
            params.extend(where_params)

        # GROUP BY
        # Safety net: if aggregates are present and columns has real field names (not "*"),
        # those columns MUST be in GROUP BY (MySQL only_full_group_by will reject otherwise).
        # Auto-infer group_by from columns when the LLM forgets to include it.
        group_by = ast.get("group_by")
        if aggregates and not group_by and cols != ["*"]:
            group_by = cols  # infer from the non-aggregate column list
        if group_by:
            sql += f" GROUP BY {', '.join(group_by)}"

        # HAVING (filters after grouping — same condition system as WHERE)
        having = ast.get("having")
        if having is not None:
            frag, having_params = _build_where(having)
            sql += f" HAVING {frag}"
            params.extend(having_params)

        # ORDER BY
        order_by = ast.get("order_by")
        if order_by is not None:
            sql += f" ORDER BY {order_by['field']} {order_by.get('order', 'asc').upper()}"

        # LIMIT
        limit = ast.get("limit")
        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        return sql, tuple(params)


    elif stmt_type == "INSERT":
        rows = ast["values"]
        cols = list(rows[0].keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_str = ", ".join(cols)
        # One row per execute call -- executemany-style, but keeping it simple
        # and consistent with our single (sql, params) return shape.
        sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"
        params_list = [tuple(row[c] for c in cols) for row in rows]
        return sql, params_list  # note: now a LIST of param tuples, not one tuple

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