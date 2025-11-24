# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Internet Kill Switch - A Flask-based web application for controlling network switch ports to manage internet access. Features scheduling, temporary access grants, and punishment mode for parental controls.

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
- REST API endpoints for port control, schedules, temporary access, and punishment mode
- Background scheduler (APScheduler) that runs `sync_port_with_schedule()` every minute
- Switch interaction via HTTP session-based login and CGI endpoints
- Priority order for port control: punishment mode > temporary access > schedules > default (enabled)

**db.py** - Database layer with:
- SQLite database operations using context managers
- Timezone-aware datetime handling using `zoneinfo.ZoneInfo`
- Tables: `schedules`, `temporary_access`, `punishment_mode`, `settings`
- Priority logic in `should_port_be_enabled()` function

**templates/index.html** - Frontend UI for manual controls and schedule management

**static/script.js** - Client-side JavaScript for API interactions

### Key Architectural Patterns

1. **Automatic Synchronization**: The `sync_port_with_schedule()` function runs every minute via APScheduler to enforce schedules and cleanup expired states. It only updates the physical switch if the desired state differs from current state.

2. **Immediate Sync Triggers**: Temporary access and punishment mode endpoints call `sync_port_with_schedule()` immediately after state changes to avoid waiting up to 1 minute for the scheduler.

3. **Timezone Handling**: All datetime operations use `get_local_now()` from db.py, which returns timezone-aware datetimes based on the `TIMEZONE` environment variable. Python's `zoneinfo` module handles DST automatically.

4. **Priority-Based Control**: `should_port_be_enabled()` implements the control hierarchy:
   - Punishment mode active → always disabled
   - Temporary access active → always enabled
   - Within schedule window → enabled
   - No schedules configured → enabled (default)
   - Outside schedule windows → disabled

5. **Switch Communication**: Uses HTTP session cookies (H_P_SSID) after login, then sends port control commands via CGI parameters (portid, state, speed, flowcontrol).

### Database Schema

- **schedules**: `day_of_week` (0=Monday, 6=Sunday), `start_time` (HH:MM), `end_time` (HH:MM)
- **temporary_access**: `granted_at`, `expires_at`, `active` (boolean)
- **punishment_mode**: `activated_at`, `expires_at`, `active` (boolean)

All times in the database are stored as ISO format strings in the configured timezone.

## Configuration

Required environment variables (see `.env.example`):
- `SWITCH_IP` - Network switch IP address
- `SWITCH_USERNAME` - Switch login username
- `SWITCH_PASSWORD` - Switch login password
- `SWITCH_PORT_ID` - Port number to control
- `TIMEZONE` - IANA timezone identifier (e.g., "America/New_York")
- `DB_PATH` - SQLite database file path (default: /app/data/killswitch.db in Docker)

## Testing the Application

Manual testing via web interface at `http://localhost:9090` or API endpoints:

```bash
# Get current status
curl http://localhost:9090/api/status

# Grant temporary access for 30 minutes
curl -X POST http://localhost:9090/api/temporary-access -H "Content-Type: application/json" -d '{"duration_minutes": 30}'

# Add a schedule (Monday 7am-10pm)
curl -X POST http://localhost:9090/api/schedules -H "Content-Type: application/json" -d '{"day_of_week": 0, "start_time": "07:00", "end_time": "22:00"}'

# Debug schedule checking logic
curl http://localhost:9090/api/debug/schedule-check
```

## Important Implementation Notes

- The application maintains a global `port_state` dict that caches the last known switch state to avoid unnecessary switch commands.
- Schedule time comparisons use string comparison (`"07:00" <= "14:30" <= "22:00"`), which works correctly for HH:MM format.
- Temporary access grants can be extended by calling the grant endpoint again while access is active - it adds to the existing expiration time rather than replacing it.
- Punishment mode requires at least one schedule to exist (calculates expiration as next schedule start time).
- The `/api/port/set` endpoint allows explicit port control without toggling, useful for automation or external integrations.
