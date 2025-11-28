from flask import Flask, jsonify, request, render_template
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import os
import db

app = Flask(__name__)

# Timezone Configuration
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

# Port state cache for all devices (keyed by device_id)
port_states = {}

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

def login_to_switch(device_config):
    """Login to a switch using device configuration"""
    login_url = f"http://{device_config['ip']}/logon.cgi"
    payload = {
        "username": device_config['username'],
        "password": device_config['password'],
        "cpassword": "",
        "logon": "Login"
    }
    session = requests.Session()
    response = session.post(login_url, data=payload, verify=False)
    if response.status_code == 200 and "H_P_SSID" in session.cookies:
        return session
    else:
        raise Exception(f"Failed to log in to switch {device_config['alias']}")

def control_port(session, device_config, enable):
    """Control a port on a switch"""
    state = 1 if enable else 0
    port_url = f"http://{device_config['ip']}/port_setting.cgi?portid={device_config['port_id']}&state={state}&speed=1&flowcontrol=0&apply=Apply"
    response = session.get(port_url, verify=False)
    if response.status_code == 200:
        return True
    else:
        return False

def get_device_id_from_request():
    """Extract device_id from request (query param or JSON body), default to default device"""
    device_id = None

    # Try query parameter first
    if request.args.get('device_id'):
        device_id = int(request.args.get('device_id'))
    # Try JSON body if it's a POST/PUT/DELETE with JSON
    elif request.is_json and request.get_json().get('device_id'):
        device_id = int(request.get_json().get('device_id'))

    # If no device_id specified, use default
    if device_id is None:
        device_id = db.get_default_device_id()

    return device_id

def sync_port_with_schedule(device_id=None):
    """
    Background job to sync port state with schedules
    This runs every minute to check if the port should be enabled/disabled
    If device_id is None, syncs all devices
    """
    global port_states
    try:
        now = db.get_local_now()
        print(f"[SCHEDULER] Running sync check at {now.strftime('%Y-%m-%d %H:%M:%S')}")

        # Cleanup expired temporary access and punishment mode for all devices
        db.cleanup_expired_temporary_access()
        db.cleanup_expired_punishment_mode()

        # Get devices to sync
        if device_id is None:
            devices = db.get_devices()
        else:
            device = db.get_device(device_id)
            devices = [device] if device else []

        for device in devices:
            dev_id = device['id']
            alias = device['alias']

            # Initialize port state if not exists
            if dev_id not in port_states:
                port_states[dev_id] = {"enabled": False}

            # Determine if port should be enabled
            should_be_enabled = db.should_port_be_enabled(dev_id)
            current_state = port_states[dev_id]["enabled"]
            print(f"[SCHEDULER] {alias}: Current={current_state}, Should be={should_be_enabled}")

            # Only update if state needs to change
            if current_state != should_be_enabled:
                print(f"[SCHEDULER] {alias}: State change needed, updating switch...")
                try:
                    session = login_to_switch(device)
                    success = control_port(session, device, should_be_enabled)
                    if success:
                        port_states[dev_id]["enabled"] = should_be_enabled
                        print(f"[SCHEDULER] {alias}: SUCCESS - Port synced to {'enabled' if should_be_enabled else 'disabled'}")
                    else:
                        print(f"[SCHEDULER] {alias}: FAILED - Could not update switch")
                except Exception as e:
                    print(f"[SCHEDULER] {alias}: ERROR - {e}")
            else:
                print(f"[SCHEDULER] {alias}: No change needed")

    except Exception as e:
        print(f"[SCHEDULER] ERROR: {e}")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/devices", methods=["GET"])
def get_devices():
    """Get all configured devices"""
    try:
        devices = db.get_devices()
        # Don't expose passwords in API response
        for device in devices:
            device.pop('password', None)
        return jsonify(devices)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/port/state", methods=["GET"])
def get_port_state():
    """Get port state for a device"""
    try:
        device_id = get_device_id_from_request()
        if device_id not in port_states:
            port_states[device_id] = {"enabled": False}
        return jsonify(port_states[device_id])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/port/toggle", methods=["POST"])
def toggle_port():
    """Toggle port state for a device"""
    global port_states
    try:
        device_id = get_device_id_from_request()
        device = db.get_device(device_id)
        if not device:
            return jsonify({"error": "Device not found"}), 404

        # Initialize port state if not exists
        if device_id not in port_states:
            port_states[device_id] = {"enabled": False}

        new_state = not port_states[device_id]["enabled"]
        session = login_to_switch(device)
        success = control_port(session, device, new_state)
        if success:
            port_states[device_id]["enabled"] = new_state
            return jsonify(port_states[device_id])
        else:
            return jsonify({"error": "Failed to update port state"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/port/set", methods=["POST"])
def set_port_state():
    """
    Allows explicitly enabling or disabling the port via an API endpoint.
    Expects a JSON payload: { "enabled": true/false, "device_id": <optional> }
    """
    global port_states
    try:
        data = request.get_json()
        if "enabled" not in data:
            return jsonify({"error": "'enabled' field is required"}), 400

        desired_state = data["enabled"]
        device_id = get_device_id_from_request()
        device = db.get_device(device_id)
        if not device:
            return jsonify({"error": "Device not found"}), 404

        # Initialize port state if not exists
        if device_id not in port_states:
            port_states[device_id] = {"enabled": False}

        session = login_to_switch(device)
        success = control_port(session, device, desired_state)
        if success:
            port_states[device_id]["enabled"] = desired_state
            return jsonify(port_states[device_id])
        else:
            return jsonify({"error": "Failed to set port state"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Schedule Management Endpoints

@app.route("/api/schedules", methods=["GET"])
def get_schedules():
    """Get all schedules for a device"""
    try:
        device_id = get_device_id_from_request()
        schedules = db.get_schedules(device_id)
        return jsonify(schedules)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/schedules", methods=["POST"])
def add_schedule():
    """
    Add a new schedule
    Expects: { "day_of_week": 0-6, "start_time": "HH:MM", "end_time": "HH:MM", "device_id": <optional> }
    """
    try:
        data = request.get_json()
        day_of_week = data.get("day_of_week")
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if day_of_week is None or not start_time or not end_time:
            return jsonify({"error": "day_of_week, start_time, and end_time are required"}), 400

        device_id = get_device_id_from_request()
        schedule_id = db.add_schedule(day_of_week, start_time, end_time, device_id)
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
    Expects: { "duration_minutes": <number>, "device_id": <optional> }
    """
    try:
        data = request.get_json()
        duration_minutes = data.get("duration_minutes")

        if not duration_minutes or duration_minutes <= 0:
            return jsonify({"error": "duration_minutes must be a positive number"}), 400

        device_id = get_device_id_from_request()
        result = db.grant_temporary_access(duration_minutes, device_id)
        # Immediately sync the port state for this device
        sync_port_with_schedule(device_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/temporary-access", methods=["GET"])
def get_temporary_access():
    """Get active temporary access for a device"""
    try:
        device_id = get_device_id_from_request()
        temp_access = db.get_active_temporary_access(device_id)
        return jsonify(temp_access if temp_access else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/temporary-access", methods=["DELETE"])
def revoke_temporary_access():
    """Revoke active temporary access for a device"""
    try:
        device_id = get_device_id_from_request()
        db.revoke_temporary_access(device_id)
        # Immediately sync the port state for this device
        sync_port_with_schedule(device_id)
        return jsonify({"message": "Temporary access revoked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Punishment Mode Endpoints

@app.route("/api/punishment-mode", methods=["POST"])
def activate_punishment_mode():
    """
    Activate punishment mode - disables internet until next schedule starts
    Expects: { "device_id": <optional> }
    """
    try:
        device_id = get_device_id_from_request()
        result = db.activate_punishment_mode(device_id)
        if not result:
            return jsonify({"error": "No schedules configured - cannot activate punishment mode"}), 400
        # Immediately sync the port state to disable for this device
        sync_port_with_schedule(device_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/punishment-mode", methods=["GET"])
def get_punishment_mode():
    """Get active punishment mode for a device"""
    try:
        device_id = get_device_id_from_request()
        punishment = db.get_active_punishment_mode(device_id)
        return jsonify(punishment if punishment else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/punishment-mode", methods=["DELETE"])
def revoke_punishment_mode():
    """Revoke active punishment mode for a device"""
    try:
        device_id = get_device_id_from_request()
        db.revoke_punishment_mode(device_id)
        # Immediately sync the port state for this device
        sync_port_with_schedule(device_id)
        return jsonify({"message": "Punishment mode revoked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/status", methods=["GET"])
def get_status():
    """Get comprehensive status including port state, schedules, and temporary access for a device"""
    try:
        device_id = get_device_id_from_request()
        now = db.get_local_now()

        # Initialize port state if not exists
        if device_id not in port_states:
            port_states[device_id] = {"enabled": False}

        return jsonify({
            "port_state": port_states[device_id],
            "active_temporary_access": db.get_active_temporary_access(device_id),
            "active_punishment_mode": db.get_active_punishment_mode(device_id),
            "should_be_enabled": db.should_port_be_enabled(device_id),
            "schedules_count": len(db.get_schedules(device_id)),
            "debug": {
                "current_day": now.weekday(),
                "current_time": now.strftime("%H:%M"),
                "current_datetime": now.isoformat(),
                "timezone": TIMEZONE,
                "device_id": device_id
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/debug/schedule-check", methods=["GET"])
def debug_schedule_check():
    """Debug endpoint to see schedule checking logic for a device"""
    try:
        device_id = get_device_id_from_request()
        now = db.get_local_now()
        current_day = now.weekday()
        current_time = now.strftime("%H:%M")

        schedules = db.get_schedules(device_id)
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

        # Initialize port state if not exists
        if device_id not in port_states:
            port_states[device_id] = {"enabled": False}

        return jsonify({
            "current_day": current_day,
            "current_time": current_time,
            "current_datetime": now.isoformat(),
            "timezone": TIMEZONE,
            "device_id": device_id,
            "should_be_enabled": db.should_port_be_enabled(device_id),
            "schedules": matching_schedules,
            "scheduler": {
                "running": scheduler_running,
                "jobs": jobs
            },
            "port_state": port_states[device_id]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Initialize database
    db.init_db()

    # Force initial sync on startup for all devices to ensure switch matches schedule
    try:
        devices = db.get_devices()
        for device in devices:
            device_id = device['id']
            alias = device['alias']
            try:
                should_be_enabled = db.should_port_be_enabled(device_id)
                session = login_to_switch(device)
                success = control_port(session, device, should_be_enabled)
                if success:
                    port_states[device_id] = {"enabled": should_be_enabled}
                    print(f"Startup [{alias}]: Port initialized to {'enabled' if should_be_enabled else 'disabled'} at {db.get_local_now()}")
                else:
                    print(f"Warning [{alias}]: Failed to set port state on startup")
                    port_states[device_id] = {"enabled": False}
            except Exception as e:
                print(f"Warning [{alias}]: Could not sync port on startup: {e}")
                port_states[device_id] = {"enabled": False}
    except Exception as e:
        print(f"Warning: Could not initialize devices on startup: {e}")

    # Schedule the port sync job to run every minute for all devices
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
