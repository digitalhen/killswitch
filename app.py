from flask import Flask, jsonify, request, render_template
import requests

app = Flask(__name__)

# Switch Configuration
SWITCH_IP = "REDACTED_IP"
USERNAME = "admin"
PASSWORD = "REDACTED_PASSWORD"
PORT_ID = 1

# Mock state for demo purposes
port_state = {"enabled": False}

def login_to_switch():
    login_url = f"http://{SWITCH_IP}/logon.cgi"
    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "cpassword": "",
        "logon": "Login"
    }
    session = requests.Session()
    response = session.post(login_url, data=payload, verify=False)
    if response.status_code == 200 and "H_P_SSID" in session.cookies:
        return session
    else:
        raise Exception("Failed to log in to the switch")

def control_port(session, enable):
    state = 1 if enable else 0
    port_url = f"http://{SWITCH_IP}/port_setting.cgi?portid={PORT_ID}&state={state}&speed=1&flowcontrol=0&apply=Apply"
    response = session.get(port_url, verify=False)
    if response.status_code == 200:
        return True
    else:
        return False

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/port/state", methods=["GET"])
def get_port_state():
    return jsonify(port_state)

@app.route("/api/port/toggle", methods=["POST"])
def toggle_port():
    global port_state
    try:
        session = login_to_switch()
        new_state = not port_state["enabled"]
        success = control_port(session, new_state)
        if success:
            port_state["enabled"] = new_state
            return jsonify(port_state)
        else:
            return jsonify({"error": "Failed to update port state"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/port/set", methods=["POST"])
def set_port_state():
    """
    Allows explicitly enabling or disabling the port via an API endpoint.
    Expects a JSON payload: { "enabled": true/false }
    """
    global port_state
    try:
        # Parse JSON payload
        data = request.get_json()
        if "enabled" not in data:
            return jsonify({"error": "'enabled' field is required"}), 400

        desired_state = data["enabled"]

        # Login and control the port
        session = login_to_switch()
        success = control_port(session, desired_state)
        if success:
            port_state["enabled"] = desired_state
            return jsonify(port_state)
        else:
            return jsonify({"error": "Failed to set port state"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
