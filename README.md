# Internet Kill Switch

A Docker-based web application for controlling a network switch port to manage internet access. Designed for parental controls with scheduling capabilities.

## Hardware Compatibility

This application is designed to work with **TP-Link Easy Smart Switches**, specifically tested with the **TL-SG105E** and similar models in the series (TL-SG108E, etc.). These switches provide a web-based management interface that the application uses to control individual ports.

## Parental Control Use Case

This tool provides **hardware-level internet control** for parental supervision. By connecting a child's computer or an entire room's network equipment to a managed switch port, you can enforce internet access schedules at the network layer.

**Key advantage**: As long as the physical switch is secured (locked in a network cabinet or placed out of reach), this provides tamper-proof internet control. Unlike software-based parental controls that can be bypassed, circumvented, or disabled, controlling the network switch port completely cuts off internet connectivity at the hardware level - there's no workaround available to the end user.

**Typical setup**: Place the child's computer, gaming console, or room's access point on the controlled switch port. The switch itself should be physically secured where it cannot be accessed or reset by the child.

## Features

- Manual port control via web interface
- Weekly scheduling (set allowed hours per day)
- Temporary access grants (override schedules for a set duration)
- Internal scheduler (no external cron required)
- Persistent SQLite database

## Quick Start

1. Copy the example environment file and configure:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your switch credentials and settings:
   ```
   SWITCH_IP=192.168.1.1
   SWITCH_USERNAME=admin
   SWITCH_PASSWORD=your_password
   SWITCH_PORT_ID=1
   TIMEZONE=America/New_York
   ```

3. Build and run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

4. Access the web interface at `http://localhost:9090`

## Configuration

All configuration is done via the `.env` file:
- `SWITCH_IP`: Your network switch IP address
- `SWITCH_USERNAME`: Switch admin username
- `SWITCH_PASSWORD`: Switch admin password
- `SWITCH_PORT_ID`: Port number to control
- `TIMEZONE`: Your local timezone
  - Examples: "America/New_York", "America/Los_Angeles", "America/Chicago", "Europe/London"
  - Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
- `DB_PATH`: Database file path (default: /app/data/killswitch.db)

## Usage

### Manual Control
Click the toggle button to enable/disable the port immediately.

### Weekly Schedules
1. Select a day of week (Monday=0, Sunday=6)
2. Set start and end times (24-hour format)
3. Click "Add Schedule"
4. Internet will only be available during scheduled windows

### Temporary Access
Grant temporary internet access that overrides schedules:
- Click preset buttons (30min, 1hr, 2hr, 3hr)
- Access automatically revokes when time expires
- Use "Revoke Access" to cancel early

### Punishment Mode
Disable internet immediately until the next scheduled time window:
- Click "Disable Until Next Schedule" to activate
- Internet will be disabled regardless of current schedule
- Automatically re-enables when the next schedule window starts
- Use "Cancel Punishment" to end early

## Scheduling Behavior

Priority order (highest to lowest):
1. **Punishment mode** - always disables, overrides everything
2. **Temporary access** - always enables, overrides schedules
3. **Weekly schedules** - internet allowed during defined windows
4. **Default** - internet enabled if no schedules exist

The scheduler checks every minute and automatically adjusts port state.

## API Endpoints

### Port Control
- `GET /api/port/state` - Get current port state
- `POST /api/port/toggle` - Toggle port state
- `POST /api/port/set` - Set port state (body: `{"enabled": true/false}`)

### Schedules
- `GET /api/schedules` - Get all schedules
- `POST /api/schedules` - Add schedule (body: `{"day_of_week": 0-6, "start_time": "HH:MM", "end_time": "HH:MM"}`)
- `DELETE /api/schedules/<id>` - Delete schedule

### Temporary Access
- `GET /api/temporary-access` - Get active temporary access
- `POST /api/temporary-access` - Grant access (body: `{"duration_minutes": N}`)
- `DELETE /api/temporary-access` - Revoke access

### Punishment Mode
- `GET /api/punishment-mode` - Get active punishment mode
- `POST /api/punishment-mode` - Activate punishment (disables until next schedule)
- `DELETE /api/punishment-mode` - Cancel punishment

### Status
- `GET /api/status` - Get comprehensive status

## Data Persistence

The SQLite database is stored in `./data/killswitch.db` and persists across container restarts.