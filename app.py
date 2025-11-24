from flask import Flask, jsonify, request, render_template
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import os
import db

app = Flask(__name__)

# Switch Configuration (from environment variables)
SWITCH_IP = os.getenv("SWITCH_IP", "REDACTED_IP")
USERNAME = os.getenv("SWITCH_USERNAME", "admin")
PASSWORD = os.getenv("SWITCH_PASSWORD", "")
PORT_ID = int(os.getenv("SWITCH_PORT_ID", "1"))

# Timezone Configuration
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

# Port state (will be synced with actual switch and schedules)
port_state = {"enabled": False}

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

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

def sync_port_with_schedule():
    """
    Background job to sync port state with schedules
    This runs every minute to check if the port should be enabled/disabled
    """
    global port_state
    try:
        now = db.get_local_now()
        print(f"[SCHEDULER] Running sync check at {now.strftime('%Y-%m-%d %H:%M:%S')}")

        # Cleanup expired temporary access and punishment mode
        db.cleanup_expired_temporary_access()
        db.cleanup_expired_punishment_mode()

        # Determine if port should be enabled
        should_be_enabled = db.should_port_be_enabled()
        print(f"[SCHEDULER] Current port state: {port_state['enabled']}, Should be: {should_be_enabled}")

        # Only update if state needs to change
        if port_state["enabled"] != should_be_enabled:
            print(f"[SCHEDULER] State change needed, updating switch...")
            session = login_to_switch()
            success = control_port(session, should_be_enabled)
            if success:
                port_state["enabled"] = should_be_enabled
                print(f"[SCHEDULER] SUCCESS: Port state synced to {'enabled' if should_be_enabled else 'disabled'}")
            else:
                print(f"[SCHEDULER] FAILED: Could not update switch")
        else:
            print(f"[SCHEDULER] No change needed, port already in correct state")
    except Exception as e:
        print(f"[SCHEDULER] ERROR: {e}")

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

# Schedule Management Endpoints

@app.route("/api/schedules", methods=["GET"])
def get_schedules():
    """Get all schedules"""
    try:
        schedules = db.get_schedules()
        return jsonify(schedules)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/schedules", methods=["POST"])
def add_schedule():
    """
    Add a new schedule
    Expects: { "day_of_week": 0-6, "start_time": "HH:MM", "end_time": "HH:MM" }
    """
    try:
        data = request.get_json()
        day_of_week = data.get("day_of_week")
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if day_of_week is None or not start_time or not end_time:
            return jsonify({"error": "day_of_week, start_time, and end_time are required"}), 400

        schedule_id = db.add_schedule(day_of_week, start_time, end_time)
        return jsonify({"id": schedule_id, "message": "Schedule added successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
def delete_schedule(schedule_id):
    """Delete a schedule"""
    try:
        db.delete_schedule(schedule_id)
        return jsonify({"message": "Schedule deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Temporary Access Endpoints

@app.route("/api/temporary-access", methods=["POST"])
def grant_temporary_access():
    """
    Grant temporary access
    Expects: { "duration_minutes": <number> }
    """
    try:
        data = request.get_json()
        duration_minutes = data.get("duration_minutes")

        if not duration_minutes or duration_minutes <= 0:
            return jsonify({"error": "duration_minutes must be a positive number"}), 400

        result = db.grant_temporary_access(duration_minutes)
        # Immediately sync the port state
        sync_port_with_schedule()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/temporary-access", methods=["GET"])
def get_temporary_access():
    """Get active temporary access"""
    try:
        temp_access = db.get_active_temporary_access()
        return jsonify(temp_access if temp_access else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/temporary-access", methods=["DELETE"])
def revoke_temporary_access():
    """Revoke active temporary access"""
    try:
        db.revoke_temporary_access()
        # Immediately sync the port state
        sync_port_with_schedule()
        return jsonify({"message": "Temporary access revoked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Punishment Mode Endpoints

@app.route("/api/punishment-mode", methods=["POST"])
def activate_punishment_mode():
    """
    Activate punishment mode - disables internet until next schedule starts
    """
    try:
        result = db.activate_punishment_mode()
        if not result:
            return jsonify({"error": "No schedules configured - cannot activate punishment mode"}), 400
        # Immediately sync the port state to disable
        sync_port_with_schedule()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/punishment-mode", methods=["GET"])
def get_punishment_mode():
    """Get active punishment mode"""
    try:
        punishment = db.get_active_punishment_mode()
        return jsonify(punishment if punishment else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/punishment-mode", methods=["DELETE"])
def revoke_punishment_mode():
    """Revoke active punishment mode"""
    try:
        db.revoke_punishment_mode()
        # Immediately sync the port state
        sync_port_with_schedule()
        return jsonify({"message": "Punishment mode revoked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/status", methods=["GET"])
def get_status():
    """Get comprehensive status including port state, schedules, and temporary access"""
    try:
        now = db.get_local_now()
        return jsonify({
            "port_state": port_state,
            "active_temporary_access": db.get_active_temporary_access(),
            "active_punishment_mode": db.get_active_punishment_mode(),
            "should_be_enabled": db.should_port_be_enabled(),
            "schedules_count": len(db.get_schedules()),
            "debug": {
                "current_day": now.weekday(),
                "current_time": now.strftime("%H:%M"),
                "current_datetime": now.isoformat(),
                "timezone": TIMEZONE
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/debug/schedule-check", methods=["GET"])
def debug_schedule_check():
    """Debug endpoint to see schedule checking logic"""
    try:
        now = db.get_local_now()
        current_day = now.weekday()
        current_time = now.strftime("%H:%M")

        schedules = db.get_schedules()
        matching_schedules = []

        for schedule in schedules:
            is_today = schedule['day_of_week'] == current_day
            time_match = schedule['start_time'] <= current_time <= schedule['end_time']
            matching_schedules.append({
                "schedule": schedule,
                "is_today": is_today,
                "time_in_range": time_match,
                "matches": is_today and time_match
            })

        # Get scheduler status
        scheduler_running = scheduler.running
        jobs = [{
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None
        } for job in scheduler.get_jobs()]

        return jsonify({
            "current_day": current_day,
            "current_time": current_time,
            "current_datetime": now.isoformat(),
            "timezone": TIMEZONE,
            "should_be_enabled": db.should_port_be_enabled(),
            "schedules": matching_schedules,
            "scheduler": {
                "running": scheduler_running,
                "jobs": jobs
            },
            "port_state": port_state
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Initialize database
    db.init_db()

    # Force initial sync on startup to ensure switch matches schedule
    try:
        should_be_enabled = db.should_port_be_enabled()
        session = login_to_switch()
        success = control_port(session, should_be_enabled)
        if success:
            port_state["enabled"] = should_be_enabled
            print(f"Startup: Port initialized to {'enabled' if should_be_enabled else 'disabled'} at {db.get_local_now()}")
        else:
            print("Warning: Failed to set port state on startup")
    except Exception as e:
        print(f"Warning: Could not sync port on startup: {e}")

    # Schedule the port sync job to run every minute
    scheduler.add_job(
        func=sync_port_with_schedule,
        trigger="interval",
        minutes=1,
        id="port_sync",
        name="Sync port state with schedule",
        replace_existing=True,
        misfire_grace_time=30,  # Allow up to 30 seconds delay without warning
        coalesce=True  # If multiple runs are missed, only run once
    )

    app.run(host="0.0.0.0", port=5000)
