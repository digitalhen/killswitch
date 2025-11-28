# Internet Kill Switch

A Docker-based web application for controlling multiple network switch ports to manage internet access. Designed for parental controls with multi-device support, scheduling capabilities, and a user-friendly configuration interface.

## Hardware Compatibility

This application is designed to work with **TP-Link Easy Smart Switches**, specifically tested with the **TL-SG105E** and similar models in the series (TL-SG108E, etc.). These switches provide a web-based management interface that the application uses to control individual ports.

## Parental Control Use Case

This tool provides **hardware-level internet control** for parental supervision across multiple devices or rooms. By connecting computers, gaming consoles, or network equipment to managed switch ports, you can enforce internet access schedules at the network layer.

**Key advantage**: As long as the physical switches are secured (locked in a network cabinet or placed out of reach), this provides tamper-proof internet control. Unlike software-based parental controls that can be bypassed, circumvented, or disabled, controlling the network switch port completely cuts off internet connectivity at the hardware level - there's no workaround available to the end user.

**Typical setup**:
- Connect each child's computer, gaming console, or room's access point to a dedicated switch port
- Add each switch/port combination to the application
- Configure independent schedules for each device
- Physically secure the switches where they cannot be accessed or reset

## Features

- **Multi-Device Support**: Control multiple switches and ports from a single interface
- **Device Configuration UI**: Add, edit, and remove devices through the web interface
- **Manual Port Control**: Toggle ports on/off instantly via web interface
- **Weekly Scheduling**: Set allowed hours per day for each device independently
- **Temporary Access Grants**: Override schedules for a set duration
- **Punishment Mode**: Disable internet until the next scheduled time window
- **Internal Scheduler**: Automatic synchronization every minute (no external cron required)
- **Persistent SQLite Database**: All configurations and schedules survive restarts
- **Timezone Support**: Handles DST changes automatically

## Quick Start

1. Copy the example environment file and configure:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your timezone (required) and optionally configure your first device:
   ```
   TIMEZONE=America/New_York

   # Optional: Configure first device (or add via web UI later)
   SWITCH_ALIAS=My Switch
   SWITCH_IP=192.168.1.1
   SWITCH_USERNAME=admin
   SWITCH_PASSWORD=your_password
   SWITCH_PORT_ID=1
   ```

3. Build and run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

4. Access the web interface:
   - **Main Dashboard**: `http://localhost:9090`
   - **Device Configuration**: `http://localhost:9090/config`

5. Add additional devices through the configuration page (`⚙️ Configure Devices` link)

## Configuration

### Environment Variables (.env file)

**Required:**
- `TIMEZONE`: Your local timezone (e.g., "America/New_York", "America/Los_Angeles", "Europe/London")
  - Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
- `DB_PATH`: Database file path (default: /app/data/killswitch.db)

**Optional (only used for initial setup if database is empty):**
- `SWITCH_ALIAS`: Friendly name for the first device (default: "Default Switch")
- `SWITCH_IP`: Network switch IP address
- `SWITCH_USERNAME`: Switch admin username (default: "admin")
- `SWITCH_PASSWORD`: Switch admin password
- `SWITCH_PORT_ID`: Port number to control (default: 1)

**Note:** After initial setup, all device management is done through the web UI at `/config`. These environment variables are only used to create the first device on initial database creation.

### Managing Devices

Navigate to `http://localhost:9090/config` to:
- Add new switches/ports
- Edit existing device configurations
- Delete devices
- Set the default device
- Each device requires: alias (name), IP address, port number, username, and password

## Usage

### Device Selection
Use the dropdown at the top of the dashboard to select which device you want to control. All settings (schedules, temporary access, punishment mode) are device-specific.

### Manual Control
Click the toggle button to enable/disable the port immediately for the selected device.

### Weekly Schedules
Configure allowed internet hours for each day:
1. Select the device from the dropdown
2. Choose a day of week
3. Set start and end times (24-hour format)
4. Click "Add Schedule"
5. Internet will only be available during scheduled windows

Each device can have different schedules - configure them independently.

### Temporary Access
Grant temporary internet access that overrides schedules for the selected device:
- Click preset buttons (30min, 1hr, 2hr, 3hr)
- Access automatically revokes when time expires
- Click again to extend the current temporary access
- Use "Revoke Access" to cancel early

### Punishment Mode
Disable internet immediately until the next scheduled time window for the selected device:
- Click "Disable Until Next Schedule" to activate
- Internet will be disabled regardless of current schedule
- Automatically re-enables when the next schedule window starts
- Use "Cancel Punishment" to end early
- Requires at least one schedule to be configured

## Scheduling Behavior

Priority order for each device (highest to lowest):
1. **Punishment mode** - always disables, overrides everything
2. **Temporary access** - always enables, overrides schedules
3. **Weekly schedules** - internet allowed during defined windows
4. **Default** - internet enabled if no schedules exist

The scheduler checks every minute and automatically adjusts port state for all devices. Each device operates independently with its own schedules and overrides.

## API Endpoints

All control endpoints accept an optional `?device_id=N` query parameter. If not specified, the default device is used.

### Device Management
- `GET /api/devices` - List all devices (passwords excluded)
- `GET /api/devices/<id>` - Get specific device (includes password)
- `POST /api/devices` - Add device (body: `{"alias": "...", "ip": "...", "port_id": N, "username": "...", "password": "...", "is_default": false}`)
- `PUT /api/devices/<id>` - Update device (same body as POST)
- `DELETE /api/devices/<id>` - Delete device (cascades to schedules/access/punishment)

### Port Control
- `GET /api/port/state?device_id=N` - Get current port state
- `POST /api/port/toggle?device_id=N` - Toggle port state
- `POST /api/port/set?device_id=N` - Set port state (body: `{"enabled": true/false}`)

### Schedules
- `GET /api/schedules?device_id=N` - Get all schedules for device
- `POST /api/schedules?device_id=N` - Add schedule (body: `{"day_of_week": 0-6, "start_time": "HH:MM", "end_time": "HH:MM"}`)
- `DELETE /api/schedules/<id>` - Delete schedule

### Temporary Access
- `GET /api/temporary-access?device_id=N` - Get active temporary access
- `POST /api/temporary-access?device_id=N` - Grant access (body: `{"duration_minutes": N}`)
- `DELETE /api/temporary-access?device_id=N` - Revoke access

### Punishment Mode
- `GET /api/punishment-mode?device_id=N` - Get active punishment mode
- `POST /api/punishment-mode?device_id=N` - Activate punishment (disables until next schedule)
- `DELETE /api/punishment-mode?device_id=N` - Cancel punishment

### Status
- `GET /api/status?device_id=N` - Get comprehensive status for device

## Data Persistence

The SQLite database is stored in `./data/killswitch.db` and persists across container restarts. All device configurations, schedules, temporary access grants, and punishment mode settings are stored in this database.

## Architecture

- **Multi-device support**: Each switch/port combination is a separate device with independent settings
- **Device-specific scheduling**: Schedules, temporary access, and punishment mode are all per-device
- **Automatic synchronization**: Background scheduler runs every minute to sync all devices
- **Priority-based control**: Each device follows its own priority hierarchy (punishment > temporary > schedule > default)
- **Cascade deletion**: Deleting a device removes all associated schedules and settings
- **Protected operations**: Cannot delete the last device to ensure the system remains functional