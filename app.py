from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Mock state for the port
port_state = {"enabled": False}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/port/state", methods=["GET"])
def get_port_state():
    return jsonify(port_state)

@app.route("/api/port/toggle", methods=["POST"])
def toggle_port():
    global port_state
    # Toggle the state
    port_state["enabled"] = not port_state["enabled"]
    # Perform action here to control the switch (placeholder)
    # e.g., call a function to enable/disable port via the API
    return jsonify(port_state)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
