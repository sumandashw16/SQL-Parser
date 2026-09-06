# MySQL-Lite: Agent Context File

> **For AI agents**: Read this entire file before doing anything. It contains the full
> project context so you don't need to ask the user to repeat themselves.

---

## What This Project Is

A college AI/ML lab project demonstrating a core principle:
**LLMs should only parse/structure natural language ΓÇö never perform the actual computation.**

A deterministic engine (hand-built lexer + recursive-descent parser + real MySQL) handles
execution. Results are never hallucinated. This is the same philosophy as an earlier
"arithmetic word problem solver" project (LLM ΓåÆ structured JSON ΓåÆ deterministic evaluator),
applied to a database/SQL context.

---

## Architecture Overview

Two input modes ΓåÆ same execution pipeline:

```
[English input]  ΓåÆ Gemini LLM ΓåÆ JSON AST ΓöÇΓöÇΓöÉ
                                             Γö£ΓöÇΓåÆ validate_ast() ΓåÆ ast_to_sql() ΓåÆ MySQL ΓåÆ results
[SQL input]      ΓåÆ lexer ΓåÆ parser ΓåÆ AST ΓöÇΓöÇΓöÇΓöÿ
```

- **LLM's only job**: understand intent, produce structured JSON (our AST format)
- **Validation layer** (`ast_nodes.py`): checks LLM JSON against strict schema before anything runs. Invalid ΓåÆ error fed back to LLM for retry (self-correction loop, max 2 retries)
- **One shared AST format** used by both paths ΓåÆ one execution engine
- **MySQL is real** (local, v8.0.26, Windows) ΓÇö we didn't fake a DB, we built a custom query language + parser + LLM front-end on top of it

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python + Flask (`app.py`), port 5000 |
| Database | MySQL 8.0.26, local `localhost:3306`, database `mysql_lite_project` |
| LLM | Google Gemini via `google-genai` SDK (NOT `google-generativeai` ΓÇö that's deprecated) |
| Gemini model | `gemini-3.5-flash-lite` (switched from `gemini-2.5-flash-lite`) |
| Frontend | Plain HTML + CSS + JS, no framework, dark "workbench" theme |
| Virtual env | `backend/venv/` ΓÇö always use this venv, all packages installed there |

---

## Project Structure

```
SQL Parser/              ΓåÉ git root
Γö£ΓöÇΓöÇ AGENTS.md            ΓåÉ this file
Γö£ΓöÇΓöÇ .gitignore
Γö£ΓöÇΓöÇ backend/
Γöé   Γö£ΓöÇΓöÇ app.py           ΓåÉ Flask server: POST /query/sql, POST /query/nl, GET /health
Γöé   Γö£ΓöÇΓöÇ config.py        ΓåÉ MySQL + Gemini credentials (gitignored, never commit)
Γöé   Γö£ΓöÇΓöÇ ast_nodes.py     ΓåÉ canonical AST schema + validate_ast()
Γöé   Γö£ΓöÇΓöÇ ast_to_sql.py    ΓåÉ validated AST dict ΓåÆ real SQL string + params tuple
Γöé   Γö£ΓöÇΓöÇ db.py            ΓåÉ MySQL connection, run_query(), get_live_schema()
Γöé   Γö£ΓöÇΓöÇ llm.py           ΓåÉ calls Gemini, builds system prompt from live schema, english_to_ast()
Γöé   Γö£ΓöÇΓöÇ lexer.py         ΓåÉ tokenizer for typed SQL text
Γöé   Γö£ΓöÇΓöÇ parser.py        ΓåÉ recursive-descent parser: tokens ΓåÆ AST (parse_sql() entry point)
Γöé   Γö£ΓöÇΓöÇ requirements.txt
Γöé   ΓööΓöÇΓöÇ venv/            ΓåÉ virtual environment (gitignored)
ΓööΓöÇΓöÇ frontend/
    Γö£ΓöÇΓöÇ index.html
    Γö£ΓöÇΓöÇ style.css
    ΓööΓöÇΓöÇ script.js
```

---

## AST Schema (Shared Format ΓÇö Both Parsers Must Produce This)

### Statement types supported

| Type | Notes |
|---|---|
| `SELECT` | columns, where, order_by, limit |
| `INSERT` | values is always a LIST of row objects, even for one row |
| `UPDATE` | set dict + optional where |
| `DELETE` | optional where (no where = delete all rows) |
| `CREATE_TABLE` | columns list with name + dtype |
| `ALTER_TABLE` | actions: ADD_COLUMN, DROP_COLUMN, RENAME_COLUMN, MODIFY_COLUMN |
| `SHOW_TABLES` | no "table" field |
| `DESCRIBE` | lists columns and schema for a specific table |
| `DROP_TABLE` | drops entire table (distinct from DELETE which removes rows) |

### Valid dtypes
`int`, `float`, `string`, `text`, `bool`, `date`, `datetime`, `timestamp`

### Valid WHERE ops
`=`, `!=`, `>`, `<`, `>=`, `<=`

### WHERE condition shapes
```json
{"field": "score", "op": ">", "value": 80}
{"and": [<condition>, <condition>, ...]}
{"or":  [<condition>, <condition>, ...]}
```

### Deliberately NOT supported (scoped out)
Subqueries, transactions, views, indexes, stored procedures,
triggers, PK/FK/UNIQUE constraints via the app's own language.

---

## Key Implementation Details

### `db.py` ΓÇö `run_query(sql, params)`
- If `params` is a **list** ΓåÆ `executemany` (multi-row INSERT)
- If `params` is a **tuple** ΓåÆ `execute` (everything else)
- If SQL starts with SELECT or SHOW ΓåÆ returns `(columns, rows)`
- Otherwise ΓåÆ returns `(None, affected_row_count)`

### `db.py` ΓÇö `get_live_schema()`
- Runs `SHOW TABLES` + `DESCRIBE <table>` on every call
- Returns human-readable schema string used to build Gemini's system prompt
- Called fresh on **every** NL query ΓÇö so newly created/altered tables are immediately visible to the LLM without a server restart

### `llm.py` ΓÇö `english_to_ast()`
- Calls Gemini with a dynamically built system prompt (live schema included)
- Strips markdown fences from response (`_extract_json`)
- Validates result with `validate_ast()` ΓÇö on failure, feeds error back to Gemini and retries (max 2 retries total)

### `parser.py` ΓÇö Supported typed SQL grammar
```
SELECT col_list FROM table [WHERE condition] [ORDER BY field [ASC|DESC]] [LIMIT n] [;]
INSERT INTO table (cols) VALUES (vals) [, (vals) ...] [;]
UPDATE table SET col=val [, col=val] [WHERE condition] [;]
DELETE FROM table [WHERE condition] [;]
ALTER TABLE table ADD [COLUMN] col dtype [;]
ALTER TABLE table DROP [COLUMN] col [;]
ALTER TABLE table RENAME [COLUMN] old TO new [;]
ALTER TABLE table MODIFY [COLUMN] col dtype [;]
SHOW TABLES [;]
DROP TABLE table [;]
```
> **Note**: `CREATE TABLE` is NOT supported in typed SQL mode ΓÇö only via English/LLM mode.

---

## What's Confirmed Working

- MySQL connection from Flask (local, root user)
- English ΓåÆ Gemini ΓåÆ JSON ΓåÆ validated ΓåÆ real SQL ΓåÆ MySQL ΓåÆ results shown in browser
- Typed SQL path through custom lexer/parser ΓåÆ same pipeline
- SELECT with WHERE / ORDER BY / LIMIT
- INNER / LEFT / RIGHT JOINs across multiple tables
- CREATE_TABLE (both modes)
- Multi-row INSERT (both modes)
- LIKE, IN, BETWEEN, IS NULL operators in WHERE clauses
- Aggregate functions (COUNT, SUM, AVG, MIN, MAX) with GROUP BY / HAVING
- ALTER_TABLE (all 4 actions, both modes)
- SHOW_TABLES (both modes)
- DROP_TABLE (both modes) ΓÇö correctly distinct from DELETE
- Dynamic live schema fetch ΓÇö LLM always knows current DB state
- Rate limit issue resolved by switching Gemini model to `gemini-2.5-flash-lite`

---

## Bugs Fixed (History ΓÇö Don't Re-introduce)

1. **`ast_nodes.py` indentation** ΓÇö CREATE_TABLE/INSERT validation branches were accidentally nested inside an unrelated `if` block. Fixed.

2. **`ast_to_sql.py` unconditional `ast["table"]` access** ΓÇö crashed for SHOW_TABLES (no "table" key). Fixed by checking SHOW_TABLES before the table lookup.

3. **`parser.py` missing `self.match("SEMI")` / `return stmt`** ΓÇö every parsed statement silently returned None after ALTER/SHOW branches were added. Fixed.

4. **LLM using DELETE instead of DROP_TABLE** ΓÇö for "delete the table called X". Fixed by adding DROP_TABLE type + explicit prompt rule distinguishing the two.

5. **`ast_nodes.py` spurious SQL return in `validate_ast()`** ΓÇö `validate_ast()` was returning `("SHOW TABLES", ())` for SHOW_TABLES ΓÇö that's `ast_to_sql`'s job, not the validator's. Removed.

6. **`llm.py` duplicate SHOW_TABLES example** ΓÇö same example appeared twice in the system prompt. Removed duplicate.

7. **`parser.py` misleading error message** ΓÇö listed `SHOW` but not `DROP` in the "expected statement" error even though DROP TABLE is fully supported. Fixed to include DROP.

8. **PyInstaller windowed mode crash** ΓÇö The executable crashed instantly when built with `--windowed` because `sys.stdout` and `sys.stderr` are `None` in windowed apps, causing the underlying Flask/Waitress server to throw an exception when trying to log. Fixed by redirecting `sys.stdout` and `sys.stderr` to dummy streams in `main.py`.

9. **PyWebView dynamic port issue** ΓÇö `frontend/script.js` was hardcoded to fetch from `http://127.0.0.1:5000`, causing a "Network Error" when running in the executable wrapper because PyWebView spins up the Flask server on a random port. Fixed by making `API_BASE` dynamic based on the window's protocol/origin.

10. **google-genai HTTP client closed error** ΓÇö The `google-genai` Python SDK's underlying connection pool was being closed prematurely because `genai.Client()` was being re-instantiated on every query in `llm.py`. Fixed by caching the Gemini Client as a singleton and reusing the connection pool.

---

## Known Gaps / Not Yet Done

- **Frontend is MVP** ΓÇö functional but plain. User wants terminal-style feel: prompt symbol (`>`), command history (up-arrow), better workbench aesthetics
- **Error handling** ΓÇö works for happy path, not exhaustively tested against adversarial/edge-case input

---

## How the User Works (Important)

- Student, not a professional dev. Keep explanations clear, avoid jargon-heavy shorthand.
- Uses Windows, VS Code, Python venv at `backend/venv/`
- **Prefers plain code blocks in chat** they can copy-paste manually. Do NOT create zip files or push to canvas.
- Tests by running `python app.py` in the venv and using the browser frontend or manual API calls.
- Reports exact error messages ΓÇö diagnose precisely before proposing a fix.

### The pattern for adding a new statement type
When adding any new feature/statement type, follow this order:
1. `ast_nodes.py` ΓÇö add to `VALID_STMT_TYPES`, add validation branch in `validate_ast()`
2. `ast_to_sql.py` ΓÇö add SQL generation branch
3. `llm.py` ΓÇö add to system prompt: schema shape + example + any new rules
4. `lexer.py` ΓÇö add any new keywords to `KEYWORDS` set
5. `parser.py` ΓÇö add parse method + branch in `parse_statement()`
6. `db.py` ΓÇö only if execution handling needs to change (e.g. new result shape)

---

## MySQL Database

- Database name: `mysql_lite_project`
- Known tables: `students` (id, name, score, subject) with ~10 sample rows
- Other tables created during testing: `teachers`, `wardens`, etc. (may or may not exist currently)
- The live schema is always fetched dynamically ΓÇö don't hardcode table names

---

## Running the Project

```powershell
# From project root:
cd backend
.\venv\Scripts\activate
python app.py
# Server runs at http://127.0.0.1:5000
# Frontend: open frontend/index.html directly in browser
```
