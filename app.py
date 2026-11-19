"""Run the Flask web application: python app.py."""

import atexit
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from yanji.flask_app import create_app

app = create_app()
if __name__ == "__main__":
    # One command starts the complete local application. A separately managed
    # worker can still be used; its existing lock prevents duplicate consumers.
    if os.environ.get("YANJI_EXTERNAL_WORKER") != "1":
        worker = subprocess.Popen([sys.executable, str(Path(__file__).with_name("worker.py"))])

        def stop_worker():
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()

        atexit.register(stop_worker)
    app.run(host="127.0.0.1", port=int(os.environ.get("YANJI_PORT", "8810")), debug=False)
