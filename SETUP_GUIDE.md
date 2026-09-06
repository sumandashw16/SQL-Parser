# Setup Guide: MySQL-Lite 🛠️

Follow these simple steps to get MySQL-Lite running on your machine.

## Prerequisites
1. **Windows OS**: This application is currently packaged as a Windows executable.
2. **A MySQL Database**: You need a local or remote MySQL server running (version 8.0+ recommended). 
3. **Gemini API Key**: You need a free Google Gemini API key to use the natural language "English-to-SQL" feature. Get one at [Google AI Studio](https://aistudio.google.com/).

## Installation & Running
You do **not** need to install Python or configure virtual environments to use the app!

1. Download the `MySQL-Lite.exe` file from the `dist/` folder.
2. Double-click `MySQL-Lite.exe` to launch the workbench.
3. On the first launch, the **Setup Modal** will appear automatically.

## Configuration
In the setup screen, enter the following details:
- **Gemini API Key**: Your personal API key (e.g., `AIzaSy...`).
- **MySQL Host**: The address of your database (default is usually `localhost`).
- **MySQL Port**: The port your database is running on (default is `3306`).
- **MySQL User**: Your database user (e.g., `root`).
- **MySQL Password**: The password for your database user.
- **MySQL Database**: The name of the specific database you want to query (e.g., `mysql_lite_project`). *Note: This database must already exist in your MySQL server.*

Click **Save & Connect**. The application will securely save your settings locally and connect to the database!

## Usage Guide
- **Toggle Modes**: Click the **English** or **SQL** buttons at the top left to switch between Natural Language mode and raw Typed SQL mode.
- **Run Queries**: Type your question/query in the terminal box and press `Enter`. (Use `Shift+Enter` or `Ctrl+Enter` to add a new line without running).
- **History Navigation**: Press `↑` (Up Arrow) and `↓` (Down Arrow) to cycle through your past queries, just like a real terminal.
- **Results**: The output of your query, along with the *exact* SQL that the AI generated, will appear in the history panel and results view below.

## Troubleshooting
- **"Network error while saving settings"**: Ensure you are connected to the internet and that your MySQL server is currently running.
- **"Database error"**: Double check your MySQL credentials and make sure the database name you provided actually exists.
- **Settings Icon**: You can always click the gear icon `⚙️` in the top right to update your API key or database credentials.
