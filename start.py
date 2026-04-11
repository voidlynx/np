from waitress import serve

from env import PORT
from main import app

print("Launching!")
serve(app, host="0.0.0.0", port=PORT)
