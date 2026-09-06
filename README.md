# MySQL-Lite: AI Database Workbench 

**MySQL-Lite** is a project that bridges the gap between natural language and deterministic database querying.

![MySQL-Lite Screenshot](https://via.placeholder.com/800x450.png?text=MySQL-Lite+Terminal+Workbench)

## Documentation
-  [**Overview**](OVERVIEW.md) - Learn about the core philosophy of this project and why we built it.
-  [**Setup Guide**](SETUP_GUIDE.md) - Get the application running on your machine in under 2 minutes.

## How We Built It
MySQL-Lite is packaged as a sleek, standalone Windows Desktop application. Here is a breakdown of the tech stack and architecture used to bring it to life:

### 1. The Frontend (UI)
The frontend is built using entirely vanilla **HTML, CSS, and JavaScript** without heavy frameworks. 
- Designed with a premium, frameless **Dark Terminal** aesthetic inspired by modern IDEs.
- Supports native window dragging, a glowing `>` prompt, and terminal-style command history (`↑` and `↓` arrow keys).

### 2. The Backend Engine (Python + Flask)
The core logic resides in a robust **Python Flask** server.
- **Deterministic SQL Parser**: We wrote a custom Lexer and Recursive-Descent Parser (`lexer.py`, `parser.py`) from scratch. It handles a massive subset of SQL (including joins, aggregates, where logic trees, and schema manipulation).
- **Abstract Syntax Tree (AST)**: Whether the user types raw SQL or plain English, the query is converted into a strictly validated JSON AST (`ast_nodes.py`) before execution.

### 3. The AI Integration (Google Gemini)
We use the modern **`google-genai`** Python SDK connected to the `gemini-3.5-flash-lite` model.
- **Dynamic Context**: The backend automatically reads the live schema of your MySQL database (`db.py`) and passes it into Gemini's system prompt. If you create a table, the AI instantly knows about it.
- **Zero Hallucination Loop**: Gemini is strictly constrained to outputting our custom JSON AST format. If it makes a syntax mistake or hallucinates, the validation layer catches the error and automatically feeds it back to the AI to self-correct before the user even notices.

### 4. The Packaging (PyWebView + PyInstaller)
To make sharing and running the app incredibly easy, we wrapped the web frontend and the Python backend together into a single executable.
- **PyWebView**: Spins up a headless Chromium window and dynamically serves the Flask backend on a random port.
- **PyInstaller**: Bundles the entire Python environment, all dependencies, and the UI assets into a single `MySQL-Lite.exe` file. Users don't need Python installed to run it!
