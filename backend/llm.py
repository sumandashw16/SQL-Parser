"""
Calls Google Gemini to convert an English question into our AST JSON format.
This is the ONLY place the LLM is used -- it never touches the database directly,
it only produces a structured dict, which then gets validated (ast_nodes.py)
before anything runs.
"""

import json
import re
import google.generativeai as genai
import config
from ast_nodes import validate_ast, ASTValidationError

genai.configure(api_key=config.GEMINI_API_KEY)

# Describe your real schema here -- keep this in sync with your actual MySQL table(s).
SCHEMA_DESCRIPTION = """
Table: students
Columns:
  - id (int)
  - name (string)
  - score (float)
  - subject (string)
"""

SYSTEM_PROMPT = f"""You convert an English question about a database into a JSON object representing a query.

{SCHEMA_DESCRIPTION}

You must output ONLY valid JSON matching one of these exact shapes. No explanation, no markdown, no code fences, no extra text -- just the raw JSON object.

SELECT:
{{"type": "SELECT", "table": "students", "columns": ["name", "score"], "where": <condition_or_null>, "order_by": <order_or_null>, "limit": <int_or_null>}}

INSERT:
{{"type": "INSERT", "table": "students", "values": {{"name": "Asha", "score": 88.5, "subject": "Math"}}}}

UPDATE:
{{"type": "UPDATE", "table": "students", "set": {{"score": 90}}, "where": <condition_or_null>}}

DELETE:
{{"type": "DELETE", "table": "students", "where": <condition_or_null>}}

A <condition> is one of:
  {{"field": "score", "op": ">", "value": 80}}
  {{"and": [<condition>, <condition>, ...]}}
  {{"or": [<condition>, <condition>, ...]}}

Valid ops: = != > < >= <=

An <order> looks like:
  {{"field": "score", "order": "desc"}}

Rules:
- Only use columns that exist in the schema above.
- Use columns=["*"] for "all columns" if not specified.
- If the question asks for "top N" or "N highest", use order_by desc on the relevant numeric column and set limit=N.
- If the question asks for "lowest" or "bottom N", use order_by asc.
- Only generate SELECT, INSERT, UPDATE, or DELETE. Never anything else.
- Output ONLY the JSON object. Nothing before or after it.

Examples:
English: show me students who scored above 80
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": {{"field": "score", "op": ">", "value": 80}}, "order_by": null, "limit": null}}

English: top 5 students by score
JSON: {{"type": "SELECT", "table": "students", "columns": ["*"], "where": null, "order_by": {{"field": "score", "order": "desc"}}, "limit": 5}}

English: delete the student named Kabir
JSON: {{"type": "DELETE", "table": "students", "where": {{"field": "name", "op": "=", "value": "Kabir"}}}}
"""

model = genai.GenerativeModel(
    model_name=config.GEMINI_MODEL,
    system_instruction=SYSTEM_PROMPT,
)


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
        response = model.generate_content(prompt)
        raw_text = _extract_json(response.text)

        try:
            ast = json.loads(raw_text)
        except json.JSONDecodeError as e:
            last_error = f"Model did not return valid JSON: {e}. Raw output: {raw_text}"
            prompt = f"{english_query}\n\nYour previous output was not valid JSON. Error: {last_error}\nRespond with ONLY the corrected JSON object."
            continue

        try:
            validate_ast(ast)
            return ast
        except ASTValidationError as e:
            last_error = str(e)
            prompt = f"{english_query}\n\nYour previous JSON was invalid: {last_error}\nRespond with ONLY the corrected JSON object."
            continue

    raise ValueError(f"Failed to get valid AST after {max_retries + 1} attempts. Last error: {last_error}")