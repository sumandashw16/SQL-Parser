"""
Lexer (tokenizer) for our supported SQL subset.
Turns raw SQL text into a flat list of Token objects.

Supported tokens: keywords, identifiers, numbers, strings, symbols.
"""

import re

KEYWORDS = {
    "SELECT", "FROM", "WHERE", "ORDER", "BY", "ASC", "DESC", "LIMIT",
    "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
    "AND", "OR", "NOT", "NULL",
    "ALTER", "TABLE", "ADD", "COLUMN", "DROP", "RENAME", "TO", "MODIFY",
    "INT", "FLOAT", "STRING", "BOOL", "SHOW", "TABLES",
    # extended WHERE operators
    "LIKE", "IN", "BETWEEN", "IS",
    # aggregate functions + GROUP BY / HAVING
    "COUNT", "SUM", "AVG", "MIN", "MAX", "GROUP", "HAVING", "AS",
}

# Order matters: longer operators must be checked before shorter ones (>= before >)
TOKEN_SPEC = [
    ("WHITESPACE", r"[ \t\n]+"),
    ("STRING",     r"'([^'\\]|\\.)*'"),
    ("NUMBER",     r"\d+\.\d+|\d+"),
    ("OP",         r">=|<=|!=|=|>|<"),
    ("COMMA",      r","),
    ("LPAREN",     r"\("),
    ("RPAREN",     r"\)"),
    ("SEMI",       r";"),
    ("STAR",       r"\*"),
    ("IDENT",      r"[A-Za-z_][A-Za-z0-9_]*"),
]

MASTER_PATTERN = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_SPEC))


class Token:
    def __init__(self, type_, value):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


class LexerError(Exception):
    pass


def tokenize(text):
    tokens = []
    pos = 0
    length = len(text)

    while pos < length:
        match = MASTER_PATTERN.match(text, pos)
        if not match:
            raise LexerError(f"Unexpected character {text[pos]!r} at position {pos}")

        kind = match.lastgroup
        value = match.group()
        pos = match.end()

        if kind == "WHITESPACE":
            continue  # skip, doesn't produce a token

        if kind == "IDENT":
            upper = value.upper()
            if upper in KEYWORDS:
                tokens.append(Token(upper, upper))
            else:
                tokens.append(Token("IDENT", value))
        elif kind == "STRING":
            # strip surrounding quotes, unescape \' -> '
            inner = value[1:-1].replace("\\'", "'")
            tokens.append(Token("STRING", inner))
        elif kind == "NUMBER":
            num = float(value) if "." in value else int(value)
            tokens.append(Token("NUMBER", num))
        else:
            tokens.append(Token(kind, value))

    tokens.append(Token("EOF", None))
    return tokens