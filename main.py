import sys
import os
import webview

# Fix for PyInstaller windowed mode where stdout/stderr are None
if sys.stdout is None:
    class DummyStream:
        def write(self, *args, **kwargs): pass
        def flush(self, *args, **kwargs): pass
    sys.stdout = DummyStream()
    sys.stderr = DummyStream()

# Determine the absolute base directory. 
# PyInstaller unpacks the executable into a temporary folder sys._MEIPASS
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

# Add backend to Python path so absolute imports in app.py work
sys.path.insert(0, os.path.join(base_dir, 'backend'))

from app import app

# Ensure Flask knows exactly where the frontend folder is, regardless of how it's launched
app.static_folder = os.path.join(base_dir, 'frontend')

if __name__ == '__main__':
    # Pass the Flask 'app' directly. PyWebView will automatically spawn an internal 
    # WSGI server on a random open port, avoiding port 5000 conflicts!
    webview.create_window('MySQL-Lite Workbench', app, width=1200, height=800, background_color='#1e1e1e')
    webview.start()

