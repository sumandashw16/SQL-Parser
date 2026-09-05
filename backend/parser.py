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
        else:
            raise ParseError(f"Expected a statement (SELECT/INSERT/UPDATE/DELETE), got {tok.type}")

        self.match("SEMI")
        if self.current().type != "EOF":
            raise ParseError(f"Unexpected token after statement: {self.current().type}")
        return stmt

    # ---- SELECT ----
    def parse_select(self):
        self.expect("SELECT")
        columns = self.parse_col_list()
        self.expect("FROM")
        table = self.expect("IDENT").value

        where = None
        if self.match("WHERE"):
            where = self.parse_condition()

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

        return {
            "type": "SELECT",
            "table": table,
            "columns": columns,
            "where": where,
            "order_by": order_by,
            "limit": limit,
        }

    def parse_col_list(self):
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
        self.expect("LPAREN")
        vals = [self.parse_literal()]
        while self.match("COMMA"):
            vals.append(self.parse_literal())
        self.expect("RPAREN")

        if len(cols) != len(vals):
            raise ParseError(f"Column count ({len(cols)}) does not match value count ({len(vals)})")

        return {
            "type": "INSERT",
            "table": table,
            "values": dict(zip(cols, vals)),
        }

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
        field = self.expect("IDENT").value
        op_tok = self.expect("OP")
        value = self.parse_literal()
        return {"field": field, "op": op_tok.value, "value": value}

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


def parse_sql(sql_text):
    """Convenience entry point: raw SQL text -> AST dict."""
    tokens = tokenize(sql_text)
    parser = Parser(tokens)
    return parser.parse_statement()