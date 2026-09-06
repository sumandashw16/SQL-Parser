# build.ps1
# This script bundles the Flask app, PyWebView, and frontend assets into a single .exe

Write-Host "Building MySQL-Lite Desktop Workbench..." -ForegroundColor Cyan

# Run PyInstaller
# --noconfirm: overwrite existing build directories
# --onefile: bundle everything into a single .exe file
# --windowed: do not open a command prompt when the .exe is run
# --add-data "frontend;frontend": bundle the frontend folder into the root of the executable
# --name "MySQL-Lite": name of the generated .exe
.\backend\venv\Scripts\pyinstaller --noconfirm --onefile --windowed --paths "backend" --add-data "frontend;frontend" --name "MySQL-Lite" main.py

Write-Host "Build complete! The executable is located in the 'dist' folder." -ForegroundColor Green
