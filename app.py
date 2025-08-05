from flask import Flask

app = Flask(__name__)


@app.route("/")
def hello_world() -> str:
    """Return a simple greeting for the root route."""
    return "LXP Learning"


if __name__ == "__main__":
    # Run a minimal Flask application when executed directly.  In a cloud
    # environment this will be started by a Procfile/gunicorn instead.
    app.run()
