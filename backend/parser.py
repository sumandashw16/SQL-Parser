"""
Recursive-descent parser for our supported SQL subset.
Consumes tokens from lexer.py, produces the same AST dict shape
used everywhere else in the project (ast_nodes.py).

Supported grammar (informal):

  statement   := select_stmt | insert_stmt | update_stmt | delete_stmt

  select_stmt := SELECT col_list FROM IDENT [where_clause] [order_clause] [limit_clause] [;]
  col_list    := STAR | IDENT (COMMA IDENT)*

  insert_stmt := INSERT INTO IDENT LPAREN col_list RPAREN VALUES LPAREN value_list RPAREN [;]
  value_list  := literal (COMMA literal)*

  update_stmt := UPDATE IDENT SET assign_list [where_clause] [;]
  assign_list := IDENT OP literal (COMMA IDENT OP literal)*   -- OP restricted to '=' here

  delete_stmt := DELETE FROM IDENT [where_clause] [;]

  where_clause  := WHERE condition
  condition     := and_cond (OR and_cond)*
  and_cond      := comparison (AND comparison)*
  comparison    := IDENT OP literal
  literal       := NUMBER | STRING

  order_clause  := ORDER BY IDENT [ASC|DESC]
  limit_clause  := LIMIT NUMBER
"""

from lexer import tokenize


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def current(self):
        return self.tokens[self.pos]

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, type_):
        tok = self.current()
        if tok.type != type_:
            raise ParseError(f"Expected {type_} but got {tok.type} ({tok.value!r}) at token index {self.pos}")
        return self.advance()

    def match(self, type_):
        if self.current().type == type_:
            return self.advance()
        return None

    # ---- entry point ----
    def parse_statement(self):
        tok = self.current()
        if tok.type == "SELECT":
            stmt = self.parse_select()
        elif tok.type == "INSERT":
            stmt = self.parse_insert()
        elif tok.type == "UPDATE":
            stmt = self.parse_update()
        elif tok.type == "DELETE":
            stmt = self.parse_delete()
        elif tok.type == "ALTER":
            stmt = self.parse_alter()
        elif tok.type == "SHOW":
            stmt = self.parse_show_tables()
        elif tok.type == "DROP":
            stmt = self.parse_drop_table()
        else:
            raise ParseError(f"Expected a statement (SELECT/INSERT/UPDATE/DELETE/ALTER/SHOW/DROP), got {tok.type}")

        self.match("SEMI")
        if self.current().type != "EOF":
            raise ParseError(f"Unexpected token after statement: {self.current().type}")
        return stmt
    # ---- SELECT ----
    def parse_select(self):
        self.expect("SELECT")

        # Peek ahead: if first token is an aggregate function keyword, parse aggregates first.
        # Otherwise parse the regular column list, then check for a comma + aggregate.
        # Strategy: parse col list that may be mixed plain cols and agg calls.
        columns, aggregates = self.parse_select_list()

        self.expect("FROM")
        table = self.expect("IDENT").value

        where = None
        if self.match("WHERE"):
            where = self.parse_condition()

        group_by = None
        if self.match("GROUP"):
            self.expect("BY")
            group_by = [self.expect("IDENT").value]
            while self.match("COMMA"):
                group_by.append(self.expect("IDENT").value)

        having = None
        if self.match("HAVING"):
            having = self.parse_condition()

        order_by = None
        if self.match("ORDER"):
            self.expect("BY")
            field = self.expect("IDENT").value
            order = "asc"
            if self.match("DESC"):
                order = "desc"
            else:
                self.match("ASC")
            order_by = {"field": field, "order": order}

        limit = None
        if self.match("LIMIT"):
            limit_tok = self.expect("NUMBER")
            limit = int(limit_tok.value)

        result = {
            "type": "SELECT",
            "table": table,
            "columns": columns,
            "where": where,
            "order_by": order_by,
            "limit": limit,
        }
        if aggregates:
            result["aggregates"] = aggregates
        if group_by:
            result["group_by"] = group_by
        if having is not None:
            result["having"] = having
        return result

    # Aggregate function keyword token types
    _AGG_FUNCS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}

    def parse_select_list(self):
        """
        Parses a mixed list of plain columns and aggregate calls.
        Returns (columns, aggregates) where:
          columns    = list of plain column names (or ["*"] if SELECT *)
          aggregates = list of {func, field, alias} dicts
        """
        # Special case: bare * (SELECT * FROM ...)
        if self.match("STAR"):
            return ["*"], []

        columns = []
        aggregates = []

        while True:
            tok = self.current()

            if tok.type in self._AGG_FUNCS:
                # aggregate call: COUNT(field) AS alias
                func = tok.type  # e.g. "COUNT"
                self.advance()
                self.expect("LPAREN")
                # field inside parens: either IDENT or STAR
                if self.match("STAR"):
                    field = "*"
                else:
                    field = self.expect("IDENT").value
                self.expect("RPAREN")
                # AS alias (optional but strongly expected)
                alias = f"{func.lower()}_{field}" if field != "*" else "count_all"
                if self.match("AS"):
                    alias = self.expect("IDENT").value
                aggregates.append({"func": func, "field": field, "alias": alias})

            else:
                # plain column name
                columns.append(self.expect("IDENT").value)

            if not self.match("COMMA"):
                break

        # If only aggregates were listed, set columns to ["*"] as placeholder
        if not columns:
            columns = ["*"]

        return columns, aggregates

    def parse_col_list(self):
        """Simple column list for INSERT/UPDATE — no aggregates."""
        if self.match("STAR"):
            return ["*"]
        cols = [self.expect("IDENT").value]
        while self.match("COMMA"):
            cols.append(self.expect("IDENT").value)
        return cols

    # ---- INSERT ----
    def parse_insert(self):
        self.expect("INSERT")
        self.expect("INTO")
        table = self.expect("IDENT").value
        self.expect("LPAREN")
        cols = [self.expect("IDENT").value]
        while self.match("COMMA"):
            cols.append(self.expect("IDENT").value)
        self.expect("RPAREN")
        self.expect("VALUES")

        rows = [self.parse_value_group(cols)]
        while self.match("COMMA"):
            rows.append(self.parse_value_group(cols))

        return {
            "type": "INSERT",
            "table": table,
            "values": rows,
        }

    def parse_value_group(self, cols):
        self.expect("LPAREN")
        vals = [self.parse_literal()]
        while self.match("COMMA"):
            vals.append(self.parse_literal())
        self.expect("RPAREN")

        if len(cols) != len(vals):
            raise ParseError(f"Column count ({len(cols)}) does not match value count ({len(vals)})")

        return dict(zip(cols, vals))

    # ---- UPDATE ----
    def parse_update(self):
        self.expect("UPDATE")
        table = self.expect("IDENT").value
        self.expect("SET")

        set_clause = {}
        field = self.expect("IDENT").value
        self.expect("OP")  # expect '=' -- any OP token accepted here, semantics assume '='
        value = self.parse_literal()
        set_clause[field] = value
        while self.match("COMMA"):
            field = self.expect("IDENT").value
            self.expect("OP")
            value = self.parse_literal()
            set_clause[field] = value

        where = None
        if self.match("WHERE"):
            where = self.parse_condition()

        return {
            "type": "UPDATE",
            "table": table,
            "set": set_clause,
            "where": where,
        }

    # ---- DELETE ----
    def parse_delete(self):
        self.expect("DELETE")
        self.expect("FROM")
        table = self.expect("IDENT").value

        where = None
        if self.match("WHERE"):
            where = self.parse_condition()

        return {
            "type": "DELETE",
            "table": table,
            "where": where,
        }

    # ---- shared: WHERE condition parsing ----
    def parse_condition(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        conditions = [left]
        while self.match("OR"):
            conditions.append(self.parse_and())
        if len(conditions) == 1:
            return conditions[0]
        return {"or": conditions}

    def parse_and(self):
        left = self.parse_comparison()
        conditions = [left]
        while self.match("AND"):
            conditions.append(self.parse_comparison())
        if len(conditions) == 1:
            return conditions[0]
        return {"and": conditions}

    def parse_comparison(self):
        # Leading NOT before the whole expression: NOT score > 90
        leading_not = bool(self.match("NOT"))

        field = self.expect("IDENT").value

        # Post-field NOT (SQL standard: name NOT LIKE / NOT IN / NOT BETWEEN)
        postfield_not = bool(self.match("NOT"))
        negate = leading_not or postfield_not

        # IS [NOT] NULL
        if self.match("IS"):
            is_not = bool(self.match("NOT"))
            self.expect("NULL")
            op = "IS_NOT_NULL" if is_not else "IS_NULL"
            cond = {"field": field, "op": op}
            return {"not": cond} if negate else cond

        # LIKE
        if self.match("LIKE"):
            pattern = self.expect("STRING").value
            cond = {"field": field, "op": "LIKE", "value": pattern}
            return {"not": cond} if negate else cond

        # IN (val, val, ...)
        if self.match("IN"):
            self.expect("LPAREN")
            values = [self.parse_literal()]
            while self.match("COMMA"):
                values.append(self.parse_literal())
            self.expect("RPAREN")
            cond = {"field": field, "op": "IN", "values": values}
            return {"not": cond} if negate else cond

        # BETWEEN low AND high
        if self.match("BETWEEN"):
            low = self.parse_literal()
            self.expect("AND")
            high = self.parse_literal()
            cond = {"field": field, "op": "BETWEEN", "low": low, "high": high}
            return {"not": cond} if negate else cond

        # Standard comparison  (=, !=, >, <, >=, <=)
        op_tok = self.expect("OP")
        value = self.parse_literal()
        cond = {"field": field, "op": op_tok.value, "value": value}
        return {"not": cond} if negate else cond



    def parse_literal(self):
        tok = self.current()
        if tok.type == "NUMBER":
            self.advance()
            return tok.value
        elif tok.type == "STRING":
            self.advance()
            return tok.value
        else:
            raise ParseError(f"Expected a literal (number or string), got {tok.type}")
    # ---- ALTER TABLE ----
    def parse_alter(self):
        self.expect("ALTER")
        self.expect("TABLE")
        table = self.expect("IDENT").value

        if self.match("ADD"):
            self.match("COLUMN")  # optional keyword
            col_name = self.expect("IDENT").value
            dtype = self.parse_dtype()
            return {
                "type": "ALTER_TABLE",
                "table": table,
                "action": "ADD_COLUMN",
                "column": {"name": col_name, "dtype": dtype},
            }

        elif self.match("DROP"):
            self.match("COLUMN")  # optional keyword
            col_name = self.expect("IDENT").value
            return {
                "type": "ALTER_TABLE",
                "table": table,
                "action": "DROP_COLUMN",
                "column_name": col_name,
            }

        elif self.match("RENAME"):
            self.match("COLUMN")  # optional keyword
            old_name = self.expect("IDENT").value
            self.expect("TO")
            new_name = self.expect("IDENT").value
            return {
                "type": "ALTER_TABLE",
                "table": table,
                "action": "RENAME_COLUMN",
                "old_name": old_name,
                "new_name": new_name,
            }

        elif self.match("MODIFY"):
            self.match("COLUMN")  # optional keyword
            col_name = self.expect("IDENT").value
            dtype = self.parse_dtype()
            return {
                "type": "ALTER_TABLE",
                "table": table,
                "action": "MODIFY_COLUMN",
                "column": {"name": col_name, "dtype": dtype},
            }

        else:
            raise ParseError(f"Expected ADD/DROP/RENAME/MODIFY after ALTER TABLE {table}, got {self.current().type}")

    def parse_dtype(self):
        tok = self.current()
        if tok.type in ("INT", "FLOAT", "STRING", "BOOL"):
            self.advance()
            return tok.type.lower()
        raise ParseError(f"Expected a data type (INT/FLOAT/STRING/BOOL), got {tok.type}")

    def parse_show_tables(self):
        self.expect("SHOW")
        self.expect("TABLES")
        return {"type": "SHOW_TABLES"}
    
    def parse_drop_table(self):
        self.expect("DROP")
        self.expect("TABLE")
        table = self.expect("IDENT").value
        return {"type": "DROP_TABLE", "table": table}
    
def parse_sql(sql_text):
    """Convenience entry point: raw SQL text -> AST dict."""
    tokens = tokenize(sql_text)
    parser = Parser(tokens)
    return parser.parse_statement()