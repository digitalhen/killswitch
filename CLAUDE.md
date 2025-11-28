# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Internet Kill Switch - A Flask-based web application for controlling multiple network switch ports to manage internet access. Features multi-device support, scheduling, temporary access grants, and punishment mode for parental controls.

## Development Commands

### Docker (Primary workflow)
```bash
# Build and run the application
docker-compose up -d

# Rebuild after code changes
docker-compose up --build -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

### Local Development (Python)
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application directly
python app.py
```

The application runs on port 5000 internally (mapped to 9090 via Docker Compose).

## Architecture

### Core Components

**app.py** - Main Flask application with:
- REST API endpoints for device management, port control, schedules, temporary access, and punishment mode
- Background scheduler (APScheduler) that runs `sync_port_with_schedule()` every minute for all devices
- Switch interaction via HTTP session-based login and CGI endpoints
- Priority order for port control (per device): punishment mode > temporary access > schedules > default (enabled)
- Device-specific port state caching in `port_states` dictionary

**db.py** - Database layer with:
- SQLite database operations using context managers
- Timezone-aware datetime handling using `zoneinfo.ZoneInfo`
- Tables: `devices`, `schedules`, `temporary_access`, `punishment_mode`, `settings`
- All control tables (schedules, etc.) are linked to devices via `device_id` foreign key
- Priority logic in `should_port_be_enabled(device_id)` function
- Device CRUD operations with automatic default device management

**templates/index.html** - Frontend UI for device selection, manual controls, and schedule management
**templates/config.html** - Device configuration page for adding/editing/deleting switches

**static/script.js** - Client-side JavaScript for main dashboard API interactions
**static/config.js** - Device configuration page JavaScript

### Key Architectural Patterns

1. **Multi-Device Support**: The application can control multiple network switches simultaneously. Each device has its own schedules, temporary access, and punishment mode settings. All devices are synchronized every minute by the background scheduler.

2. **Automatic Synchronization**: The `sync_port_with_schedule()` function runs every minute via APScheduler to enforce schedules and cleanup expired states for all devices. It only updates the physical switch if the desired state differs from current state.

3. **Immediate Sync Triggers**: Temporary access and punishment mode endpoints call `sync_port_with_schedule(device_id)` immediately after state changes to avoid waiting up to 1 minute for the scheduler.

4. **Timezone Handling**: All datetime operations use `get_local_now()` from db.py, which returns timezone-aware datetimes based on the `TIMEZONE` environment variable. Python's `zoneinfo` module handles DST automatically.

5. **Priority-Based Control**: `should_port_be_enabled(device_id)` implements the control hierarchy per device:
   - Punishment mode active → always disabled
   - Temporary access active → always enabled
   - Within schedule window → enabled
   - No schedules configured → enabled (default)
   - Outside schedule windows → disabled

6. **Switch Communication**: Uses HTTP session cookies (H_P_SSID) after login, then sends port control commands via CGI parameters (portid, state, speed, flowcontrol). Each device maintains its own session and configuration.

### Database Schema

- **devices**: `id`, `alias`, `ip`, `username`, `password`, `port_id`, `is_default` (boolean)
- **schedules**: `id`, `device_id` (FK), `day_of_week` (0=Monday, 6=Sunday), `start_time` (HH:MM), `end_time` (HH:MM), `enabled`
- **temporary_access**: `id`, `device_id` (FK), `granted_at`, `expires_at`, `active` (boolean)
- **punishment_mode**: `id`, `device_id` (FK), `activated_at`, `expires_at`, `active` (boolean)
- **settings**: `key`, `value` (app-level configuration)

All times in the database are stored as ISO format strings in the configured timezone. Device deletion cascades to all associated schedules, temporary access, and punishment mode records.

## Configuration

### Environment Variables

Required environment variables (see `.env.example`):
- `TIMEZONE` - IANA timezone identifier (e.g., "America/New_York") **[REQUIRED]**
- `DB_PATH` - SQLite database file path (default: /app/data/killswitch.db in Docker) **[REQUIRED]**

Optional environment variables (only used for initial setup on first run):
- `SWITCH_ALIAS` - Friendly name for the initial device (default: "Default Switch")
- `SWITCH_IP` - Network switch IP address
- `SWITCH_USERNAME` - Switch login username (default: "admin")
- `SWITCH_PASSWORD` - Switch login password (default: "")
- `SWITCH_PORT_ID` - Port number to control (default: 1)

**Note**: After initial setup, all device management is done through the web UI at `/config`. Environment variables are only used to create the first device if the database is empty.

### Device Configuration

Devices can be managed through the web UI at `http://localhost:9090/config` or via API:

```bash
# List all devices
curl http://localhost:9090/api/devices

# Add a new device
curl -X POST http://localhost:9090/api/devices -H "Content-Type: application/json" \
  -d '{"alias":"Kitchen","ip":"192.168.1.50","port_id":3,"username":"admin","password":"pass","is_default":false}'

# Update a device
curl -X PUT http://localhost:9090/api/devices/2 -H "Content-Type: application/json" \
  -d '{"alias":"Updated Name","ip":"192.168.1.51","port_id":3,"username":"admin","password":"pass","is_default":false}'

# Delete a device
curl -X DELETE http://localhost:9090/api/devices/2
```

## Testing the Application

Manual testing via web interface at `http://localhost:9090` or API endpoints:

```bash
# Get current status for device 1
curl "http://localhost:9090/api/status?device_id=1"

# Grant temporary access for 30 minutes to device 1
curl -X POST "http://localhost:9090/api/temporary-access?device_id=1" \
  -H "Content-Type: application/json" -d '{"duration_minutes": 30}'

# Add a schedule (Monday 7am-10pm) to device 1
curl -X POST "http://localhost:9090/api/schedules?device_id=1" \
  -H "Content-Type: application/json" -d '{"day_of_week": 0, "start_time": "07:00", "end_time": "22:00"}'

# Debug schedule checking logic for device 1
curl "http://localhost:9090/api/debug/schedule-check?device_id=1"
```

**Note**: All control endpoints (schedules, temporary access, punishment mode, status) accept an optional `device_id` query parameter. If not specified, the default device is used.

## Important Implementation Notes

- The application maintains a global `port_states` dict (keyed by device_id) that caches the last known switch state to avoid unnecessary switch commands.
- Schedule time comparisons use string comparison (`"07:00" <= "14:30" <= "22:00"`), which works correctly for HH:MM format.
- Temporary access grants can be extended by calling the grant endpoint again while access is active - it adds to the existing expiration time rather than replacing it.
- Punishment mode requires at least one schedule to exist (calculates expiration as next schedule start time).
- The `/api/port/set` endpoint allows explicit port control without toggling, useful for automation or external integrations.
- Each device operates independently - schedules, temporary access, and punishment mode are all device-specific.
- The default device is used when no `device_id` is specified in API requests.
- Deleting a device cascades to all associated data (schedules, temporary access, punishment mode).
- At least one device must exist in the system - the last device cannot be deleted.
