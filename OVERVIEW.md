# Overview: MySQL-Lite 

## What is this?
**MySQL-Lite** is an AI-powered database workbench built as a college AI/ML lab project. It provides a sleek, terminal-style desktop application that allows users to interact with a real MySQL database using either **plain English** or **raw SQL**.

## The Core Philosophy
The main objective of this project was to demonstrate a critical principle in modern AI application design:
> **LLMs should only parse and structure natural language—they should *never* perform the actual computation or hallucinate data.**

Instead of asking an AI to guess the answer to a question, MySQL-Lite uses Google's Gemini model purely as a **translation layer**. 

1. **You ask a question** (e.g., *"Show me the top 5 students in Math"*).
2. **The LLM translates** the intent into a strictly typed, predefined JSON Abstract Syntax Tree (AST).
3. **The engine validates** the JSON to ensure it matches our strict schema. If the LLM hallucinates an invalid structure, the system automatically catches it and forces the LLM to self-correct.
4. **The deterministic engine** (a hand-built recursive-descent parser and SQL generator) converts that AST into a perfectly safe, parameterized SQL query.
5. **Real MySQL** executes the query and returns actual, deterministic results.

Results are **never** hallucinated. The AI simply acts as a natural language compiler.

## What can it do?
MySQL-Lite supports a robust subset of SQL operations through both its Custom Lexer/Parser (for typed SQL) and the Gemini LLM (for English queries):

- **Querying Data**: `SELECT` with `WHERE`, `ORDER BY`, `LIMIT`, and complex `JOIN`s across multiple tables.
- **Data Manipulation**: Multi-row `INSERT`, `UPDATE`, and `DELETE` operations.
- **Schema Management**: `CREATE TABLE`, `DROP TABLE`, `SHOW TABLES`, `DESCRIBE`, and `ALTER TABLE` (Add, Drop, Rename, and Modify columns).
- **Aggregations**: Functions like `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` using `GROUP BY` and `HAVING`.
- **Advanced Filtering**: Support for `LIKE`, `IN`, `BETWEEN`, `IS NULL`, and complex `AND`/`OR` logic trees.

By keeping the execution deterministic and the AI constrained to parsing, MySQL-Lite provides a reliable, hallucination-free way to interact with databases using natural language.
