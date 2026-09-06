"""
Calls Google Gemini to convert an English question into our AST JSON format.
This is the ONLY place the LLM is used -- it never touches the database directly,
it only produces a structured dict, which then gets validated (ast_nodes.py)
before anything runs.
"""

import db
import json
import re
# pyrefly: ignore [missing-import]
from google import genai
import config
from ast_nodes import validate_ast, ASTValidationError

_client = None
_client_api_key = None

def get_client():
    global _client, _client_api_key
    if not config.GEMINI_API_KEY:
        raise ValueError("SETUP_REQUIRED: Missing Gemini API Key")
    
    if _client is None or _client_api_key != config.GEMINI_API_KEY:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
        _client_api_key = config.GEMINI_API_KEY
        
    return _client

# Describe your real schema here -- keep this in sync with your actual MySQL table(s).
def build_system_prompt():
    """Builds the system prompt fresh each call, using the live MySQL schema
    so the LLM always knows about tables created earlier in this session
    (including ones created via CREATE_TABLE through this same app)."""
    live_schema = db.get_live_schema()

    return f"""You convert an English question about a database into a JSON object representing a query.

Current database schema:
{live_schema}

You must output ONLY valid JSON matching one of these exact shapes. No explanation, no markdown, no code fences, no extra text -- just the raw JSON object.

SELECT (plain):
{{"type": "SELECT", "table": "students", "columns": ["name", "score"], "where": <condition_or_null>, "order_by": <order_or_null>, "limit": <int_or_null>}}

SELECT with JOINs:
{{"type": "SELECT", "table": "students", "joins": [{{"type": "INNER JOIN", "table": "courses", "on": {{"field": "students.course_id", "op": "=", "right_field": "courses.id"}}}}], "columns": ["students.name", "courses.title"], "where": <condition_or_null>, "order_by": <order_or_null>, "limit": <int_or_null>}}

CREATE_TABLE:
{{"type": "CREATE_TABLE", "table": "teachers", "columns": [{{"name": "name", "dtype": "string"}}, {{"name": "age", "dtype": "int"}}]}}

ALTER_TABLE (four possible actions):
{{"type": "ALTER_TABLE", "table": "teachers", "action": "ADD_COLUMN", "columns": [{{"name": "email", "dtype": "string"}}, {{"name": "phone", "dtype": "string"}}]}}
{{"type": "ALTER_TABLE", "table": "teachers", "action": "DROP_COLUMN", "column_names": ["age", "department"]}}
{{"type": "ALTER_TABLE", "table": "teachers", "action": "RENAME_COLUMN", "columns": [{{"old_name": "age", "new_name": "years"}}]}}
{{"type": "ALTER_TABLE", "table": "teachers", "action": "MODIFY_COLUMN", "columns": [{{"name": "age", "dtype": "float"}}]}}

INSERT:
{{"type": "INSERT", "table": "students", "values": [{{"name": "Asha", "score": 88.5, "subject": "Math"}}]}}

For multiple rows, include more objects in the list:
{{"type": "INSERT", "table": "students", "values": [{{"name": "Asha", "score": 88.5, "subject": "Math"}}, {{"name": "Rohan", "score": 76, "subject": "Math"}}]}}

UPDATE:
{{"type": "UPDATE", "table": "students", "set": {{"score": 90}}, "where": <condition_or_null>}}

DELETE:
{{"type": "DELETE", "table": "students", "where": <condition_or_null>}}

SHOW_TABLES:
{{"type": "SHOW_TABLES"}}

DESCRIBE (see all columns/schema of a table):
{{"type": "DESCRIBE", "table": "students"}}

DROP_TABLE: (deletes an entire table, not just rows):
{{"type": "DROP_TABLE", "table": "panihouse"}}

A <condition> is one of:

  Standard comparison (value):
  {{"field": "score", "op": ">", "value": 80}}
  Valid ops: = != > < >= <=

  Field-to-field comparison (e.g., for JOINs):
  {{"field": "students.course_id", "op": "=", "right_field": "courses.id"}}

  LIKE  (use % as wildcard):
  {{"field": "name", "op": "LIKE", "value": "%ali%"}}

  IN  (match any value in a list):
  {{"field": "subject", "op": "IN", "values": ["Math", "Science"]}}

  BETWEEN  (inclusive range):
  {{"field": "score", "op": "BETWEEN", "low": 50, "high": 90}}

  IS NULL / IS NOT NULL:
  {{"field": "email", "op": "IS_NULL"}}
  {{"field": "email", "op": "IS_NOT_NULL"}}

  NOT  (negate any condition):
  {{"not": <condition>}}

  AND / OR combinators:
  {{"and": [<condition>, <condition>, ...]}}
  {{"or":  [<condition>, <condition>, ...]}}

An <order> looks like:
  {{"field": "score", "order": "desc"}}

Rules:
- Only use tables and columns that exist in the schema above.
- Use columns=["*"] for "all columns" if not specified.
- For queries involving relationships or matching data across tables, use the optional "joins" array (types: INNER JOIN, LEFT JOIN, RIGHT JOIN).
- When using JOINs, ALWAYS fully qualify column names (e.g. "table.column" instead of "column") in 'columns', 'where', 'group_by', 'having', and 'order_by' to prevent ambiguity errors.
- If the question asks for "top N" or "N highest", use order_by desc on the relevant numeric column and set limit=N.
- If the question asks for "lowest" or "bottom N", use order_by asc.
- Valid dtypes for CREATE_TABLE: int, float, string, text, bool, date, datetime, timestamp.
- If the question asks to create a new table, use CREATE_TABLE and infer reasonable dtypes for each column based on its name (e.g. "age" -> int, "score" -> float, "name" -> string, "created_at" -> timestamp, "dob" -> date) unless the user specifies types explicitly.
- "values" for INSERT is always a list of row objects, even for a single row.
- All rows in one INSERT must have exactly the same set of column names.
- If the user asks to see all columns, schema, or structure of a table, use the DESCRIBE command.
- Output ONLY the JSON object. Nothing before or after it.
- Only generate SELECT, INSERT, UPDATE, DELETE, CREATE_TABLE, ALTER_TABLE, SHOW_TABLES, or DROP_TABLE. Never anything else.
- If the question asks to delete/drop/remove an entire TABLE (not rows), use DROP_TABLE, never DELETE. DELETE only removes rows from within a table.
- When the question uses words like "average", "total", "count", "sum", "minimum", "maximum", or "per group", use aggregates with the "aggregates" field.
- For aggregate queries that group by a column: put that column in both "columns" AND "group_by". Never put a non-aggregate column in "columns" without also adding it to "group_by" — MySQL will reject it.
- Use "having" (not "where") to filter on aggregate results (e.g. "groups where average score > 70").
- "field": "*" is only valid inside COUNT. All other functions (SUM, AVG, MIN, MAX) must reference a real column name.
- If no grouping is needed (e.g. just "count all rows"), omit "group_by" and use "columns": ["*"].
- Subqueries are explicitly NOT supported. To find records missing from another table (e.g., 'riders who have never made a delivery'), do NOT use a NOT IN clause. Instead, use a LEFT JOIN and add an IS_NULL condition on the joined table's primary key.

Examples:
English: show me students who scored above 80
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": {{"field": "score", "op": ">", "value": 80}}, "order_by": null, "limit": null}}

English: top 5 students by score
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": null, "order_by": {{"field": "score", "order": "desc"}}, "limit": 5}}

English: delete the student named Kabir
JSON: {{"type": "DELETE", "table": "students", "where": {{"field": "name", "op": "=", "value": "Kabir"}}}}

English: create a table called teachers with columns name, age, and department
JSON: {{"type": "CREATE_TABLE", "table": "teachers", "columns": [{{"name": "name", "dtype": "string"}}, {{"name": "age", "dtype": "int"}}, {{"name": "department", "dtype": "string"}}]}}

English: add an email column to the teachers table
JSON: {{"type": "ALTER_TABLE", "table": "teachers", "action": "ADD_COLUMN", "column": {{"name": "email", "dtype": "string"}}}}

English: remove the email column from teachers
JSON: {{"type": "ALTER_TABLE", "table": "teachers", "action": "DROP_COLUMN", "column_name": "email"}}

English: rename dept column to department in teachers
JSON: {{"type": "ALTER_TABLE", "table": "teachers", "action": "RENAME_COLUMN", "old_name": "dept", "new_name": "department"}}

English: change age column in teachers to float
JSON: {{"type": "ALTER_TABLE", "table": "teachers", "action": "MODIFY_COLUMN", "column": {{"name": "age", "dtype": "float"}}}}

English: show me all the tables
JSON: {{"type": "SHOW_TABLES"}}

English: delete the table called panihouse
JSON: {{"type": "DROP_TABLE", "table": "panihouse"}}

English: drop the wardens table
JSON: {{"type": "DROP_TABLE", "table": "wardens"}}

English: find students whose name contains 'ali'
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": {{"field": "name", "op": "LIKE", "value": "%ali%"}}, "order_by": null, "limit": null}}

English: show students in Math or Science
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": {{"field": "subject", "op": "IN", "values": ["Math", "Science"]}}, "order_by": null, "limit": null}}

English: students with score between 60 and 90
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": {{"field": "score", "op": "BETWEEN", "low": 60, "high": 90}}, "order_by": null, "limit": null}}

English: students with no email address
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": {{"field": "email", "op": "IS_NULL"}}, "order_by": null, "limit": null}}

English: students who have an email address
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": {{"field": "email", "op": "IS_NOT_NULL"}}, "order_by": null, "limit": null}}

English: average score per subject
JSON: {{"type": "SELECT", "table": "students", "columns": ["subject"], "aggregates": [{{"func": "AVG", "field": "score", "alias": "avg_score"}}], "where": null, "group_by": ["subject"], "having": null, "order_by": null, "limit": null}}

English: how many students are in each subject
JSON: {{"type": "SELECT", "table": "students", "columns": ["subject"], "aggregates": [{{"func": "COUNT", "field": "*", "alias": "total"}}], "where": null, "group_by": ["subject"], "having": null, "order_by": null, "limit": null}}

English: subjects where the average score is above 70
JSON: {{"type": "SELECT", "table": "students", "columns": ["subject"], "aggregates": [{{"func": "AVG", "field": "score", "alias": "avg_score"}}], "where": null, "group_by": ["subject"], "having": {{"field": "avg_score", "op": ">", "value": 70}}, "order_by": null, "limit": null}}

English: total number of students
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "aggregates": [{{"func": "COUNT", "field": "*", "alias": "total"}}], "where": null, "group_by": null, "having": null, "order_by": null, "limit": null}}

English: show me students and their associated course titles using an inner join
JSON: {{"type": "SELECT", "table": "students", "joins": [{{"type": "INNER JOIN", "table": "courses", "on": {{"field": "students.course_id", "op": "=", "right_field": "courses.id"}}}}], "columns": ["students.name", "courses.title"], "where": null, "order_by": null, "limit": null}}
"""



def _extract_json(text):
    """Strip markdown code fences if the model adds them despite instructions."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def english_to_ast(english_query, max_retries=2):
    """
    Sends English to Gemini, parses + validates the JSON it returns.
    Retries once with the error message fed back if validation fails.
    Raises ASTValidationError or ValueError if it still fails after retries.
    """
    last_error = None
    prompt = english_query

    for attempt in range(max_retries + 1):
        response = get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config={"system_instruction": build_system_prompt()},
        )
        raw_text = _extract_json(response.text)

        try:
            ast = json.loads(raw_text)
        except json.JSONDecodeError as e:
            last_error = f"Model did not return valid JSON: {e}. Raw output: {raw_text}"
            prompt = f"{nl_query}\n\nYour previous output was not valid JSON. Error: {last_error}\nRespond with ONLY the corrected JSON object."
            continue

        try:
            validate_ast(ast)
            return ast
        except ASTValidationError as e:
            last_error = str(e)
            prompt = f"{nl_query}\n\nYour previous JSON was invalid: {last_error}\nRespond with ONLY the corrected JSON object."
            continue

    raise ValueError(f"Failed to get valid AST after {max_retries + 1} attempts. Last error: {last_error}")