import sqlite3
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from zoneinfo import ZoneInfo

DB_PATH = os.getenv("DB_PATH", "killswitch.db")
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

def get_local_now():
    """Get current time in configured timezone"""
    return datetime.now(ZoneInfo(TIMEZONE))

def get_default_device_id():
    """Get the default device ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM devices WHERE is_default = 1 LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else None

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize the database schema"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Devices table - stores switch configurations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                ip TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                port_id INTEGER NOT NULL,
                is_default INTEGER DEFAULT 0
            )
        """)

        # Check if we need to migrate existing data
        cursor.execute("SELECT COUNT(*) FROM devices")
        device_count = cursor.fetchone()[0]

        if device_count == 0:
            # First time setup - create default device from environment variables
            # This only happens on the very first run
            default_ip = os.getenv("SWITCH_IP")
            default_username = os.getenv("SWITCH_USERNAME", "admin")
            default_password = os.getenv("SWITCH_PASSWORD", "")
            default_port_id = int(os.getenv("SWITCH_PORT_ID", "1"))
            default_alias = os.getenv("SWITCH_ALIAS", "Default Switch")

            if default_ip:
                # Create default device from environment variables
                cursor.execute("""
                    INSERT INTO devices (alias, ip, username, password, port_id, is_default)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (default_alias, default_ip, default_username, default_password, default_port_id))
                print(f"Initial setup: Created device '{default_alias}' from environment variables")
            else:
                print("WARNING: No SWITCH_IP in environment and no devices in database.")
                print("Please configure devices via the web UI at /config")

        # Check if schedules table exists and needs migration (add device_id column)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'")
        schedules_exists = cursor.fetchone() is not None

        if schedules_exists:
            cursor.execute("PRAGMA table_info(schedules)")
            columns = [column[1] for column in cursor.fetchall()]
            needs_migration = 'device_id' not in columns
        else:
            needs_migration = False

        if schedules_exists and needs_migration:
            # Get default device id for migration
            default_device_id = get_default_device_id()

            # Rename old tables
            cursor.execute("ALTER TABLE schedules RENAME TO schedules_old")
            cursor.execute("ALTER TABLE temporary_access RENAME TO temporary_access_old")
            cursor.execute("ALTER TABLE punishment_mode RENAME TO punishment_mode_old")

            # Create new tables with device_id
            cursor.execute("""
                CREATE TABLE schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    UNIQUE(device_id, day_of_week, start_time, end_time)
                )
            """)

            cursor.execute("""
                CREATE TABLE temporary_access (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE punishment_mode (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    activated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                )
            """)

            # Migrate existing data if default device exists
            if default_device_id:
                cursor.execute(f"""
                    INSERT INTO schedules (device_id, day_of_week, start_time, end_time, enabled)
                    SELECT {default_device_id}, day_of_week, start_time, end_time, enabled
                    FROM schedules_old
                """)

                cursor.execute(f"""
                    INSERT INTO temporary_access (device_id, granted_at, expires_at, active)
                    SELECT {default_device_id}, granted_at, expires_at, active
                    FROM temporary_access_old
                """)

                cursor.execute(f"""
                    INSERT INTO punishment_mode (device_id, activated_at, expires_at, active)
                    SELECT {default_device_id}, activated_at, expires_at, active
                    FROM punishment_mode_old
                """)

            # Drop old tables
            cursor.execute("DROP TABLE schedules_old")
            cursor.execute("DROP TABLE temporary_access_old")
            cursor.execute("DROP TABLE punishment_mode_old")
        else:
            # Tables already have device_id, just ensure they exist with correct schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    UNIQUE(device_id, day_of_week, start_time, end_time)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temporary_access (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS punishment_mode (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    activated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                )
            """)

        # Settings table - stores app-level configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.commit()

def get_devices():
    """Get all devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY is_default DESC, alias")
        return [dict(row) for row in cursor.fetchall()]

def get_device(device_id):
    """Get a specific device by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def add_device(alias, ip, username, password, port_id, is_default=False):
    """Add a new device"""
    with get_db() as conn:
        cursor = conn.cursor()

        # If this is being set as default, unset other defaults
        if is_default:
            cursor.execute("UPDATE devices SET is_default = 0")

        cursor.execute("""
            INSERT INTO devices (alias, ip, username, password, port_id, is_default)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (alias, ip, username, password, port_id, 1 if is_default else 0))
        conn.commit()
        return cursor.lastrowid

def update_device(device_id, alias, ip, username, password, port_id, is_default=False):
    """Update an existing device"""
    with get_db() as conn:
        cursor = conn.cursor()

        # If this is being set as default, unset other defaults
        if is_default:
            cursor.execute("UPDATE devices SET is_default = 0 WHERE id != ?", (device_id,))

        cursor.execute("""
            UPDATE devices
            SET alias = ?, ip = ?, username = ?, password = ?, port_id = ?, is_default = ?
            WHERE id = ?
        """, (alias, ip, username, password, port_id, 1 if is_default else 0, device_id))
        conn.commit()

def delete_device(device_id):
    """Delete a device (and all associated data via CASCADE)"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if this is the default device
        cursor.execute("SELECT is_default FROM devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        if row and row[0] == 1:
            # If deleting the default, make another device the default
            cursor.execute("SELECT id FROM devices WHERE id != ? LIMIT 1", (device_id,))
            new_default = cursor.fetchone()
            if new_default:
                cursor.execute("UPDATE devices SET is_default = 1 WHERE id = ?", (new_default[0],))

        cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()

def add_schedule(day_of_week, start_time, end_time, device_id=None):
    """
    Add a weekly schedule
    day_of_week: 0=Monday, 1=Tuesday, ..., 6=Sunday
    start_time: "HH:MM" format (e.g., "07:00")
    end_time: "HH:MM" format (e.g., "22:00")
    device_id: Device ID (defaults to default device)
    """
    if device_id is None:
        device_id = get_default_device_id()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO schedules (device_id, day_of_week, start_time, end_time, enabled)
            VALUES (?, ?, ?, ?, 1)
        """, (device_id, day_of_week, start_time, end_time))
        conn.commit()
        return cursor.lastrowid

def get_schedules(device_id=None):
    """Get all schedules for a device"""
    if device_id is None:
        device_id = get_default_device_id()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM schedules
            WHERE device_id = ? AND enabled = 1
            ORDER BY day_of_week, start_time
        """, (device_id,))
        return [dict(row) for row in cursor.fetchall()]

def delete_schedule(schedule_id):
    """Delete a schedule by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()

def grant_temporary_access(duration_minutes, device_id=None):
    """
    Grant temporary access for a specified duration
    If temp access is already active, extends it by the additional duration
    Returns the expiration time
    """
    if device_id is None:
        device_id = get_default_device_id()

    now = get_local_now()

    # Check if there's already active temporary access
    existing = get_active_temporary_access(device_id)

    if existing:
        # Extend existing access by adding duration to current expiration
        current_expires = datetime.fromisoformat(existing['expires_at'])
        new_expires = current_expires + timedelta(minutes=duration_minutes)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE temporary_access
                SET expires_at = ?
                WHERE id = ?
            """, (new_expires.isoformat(), existing['id']))
            conn.commit()
            return {
                "id": existing['id'],
                "granted_at": existing['granted_at'],
                "expires_at": new_expires.isoformat(),
                "extended": True
            }
    else:
        # Create new temporary access
        expires_at = now + timedelta(minutes=duration_minutes)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO temporary_access (device_id, granted_at, expires_at, active)
                VALUES (?, ?, ?, 1)
            """, (device_id, now.isoformat(), expires_at.isoformat()))
            conn.commit()
            return {
                "id": cursor.lastrowid,
                "granted_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "extended": False
            }

def get_active_temporary_access(device_id=None):
    """Get active temporary access grant (if any)"""
    if device_id is None:
        device_id = get_default_device_id()

    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM temporary_access
            WHERE device_id = ? AND active = 1 AND expires_at > ?
            ORDER BY expires_at DESC
            LIMIT 1
        """, (device_id, now))
        row = cursor.fetchone()
        return dict(row) if row else None

def cleanup_expired_temporary_access(device_id=None):
    """Mark expired temporary access grants as inactive"""
    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        if device_id is None:
            # Cleanup for all devices
            cursor.execute("""
                UPDATE temporary_access
                SET active = 0
                WHERE active = 1 AND expires_at <= ?
            """, (now,))
        else:
            # Cleanup for specific device
            cursor.execute("""
                UPDATE temporary_access
                SET active = 0
                WHERE device_id = ? AND active = 1 AND expires_at <= ?
            """, (device_id, now))
        conn.commit()

def revoke_temporary_access(device_id=None):
    """Revoke active temporary access"""
    if device_id is None:
        device_id = get_default_device_id()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE temporary_access
            SET active = 0
            WHERE device_id = ? AND active = 1
        """, (device_id,))
        conn.commit()

def get_next_schedule_start(device_id=None):
    """
    Calculate when the next schedule window starts
    Returns datetime or None if no schedules
    """
    if device_id is None:
        device_id = get_default_device_id()

    now = get_local_now()
    current_day = now.weekday()
    current_time = now.strftime("%H:%M")

    schedules = get_schedules(device_id)
    if not schedules:
        return None

    # Look for next schedule starting today or in the next 7 days
    for day_offset in range(8):
        check_day = (current_day + day_offset) % 7
        day_schedules = [s for s in schedules if s['day_of_week'] == check_day]

        for schedule in sorted(day_schedules, key=lambda x: x['start_time']):
            # If checking today, only consider future times
            if day_offset == 0 and schedule['start_time'] <= current_time:
                continue

            # Calculate the datetime for this schedule start
            days_ahead = day_offset
            target_date = now.date() + timedelta(days=days_ahead)
            hour, minute = map(int, schedule['start_time'].split(':'))
            target_datetime = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                hour,
                minute,
                tzinfo=now.tzinfo
            )
            return target_datetime

    return None

def activate_punishment_mode(device_id=None):
    """
    Activate punishment mode - disables internet until next schedule starts
    """
    if device_id is None:
        device_id = get_default_device_id()

    now = get_local_now()
    next_start = get_next_schedule_start(device_id)

    if not next_start:
        # No schedules, can't activate punishment mode
        return None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO punishment_mode (device_id, activated_at, expires_at, active)
            VALUES (?, ?, ?, 1)
        """, (device_id, now.isoformat(), next_start.isoformat()))
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "activated_at": now.isoformat(),
            "expires_at": next_start.isoformat()
        }

def get_active_punishment_mode(device_id=None):
    """Get active punishment mode (if any)"""
    if device_id is None:
        device_id = get_default_device_id()

    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM punishment_mode
            WHERE device_id = ? AND active = 1 AND expires_at > ?
            ORDER BY expires_at DESC
            LIMIT 1
        """, (device_id, now))
        row = cursor.fetchone()
        return dict(row) if row else None

def cleanup_expired_punishment_mode(device_id=None):
    """Mark expired punishment mode as inactive"""
    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        if device_id is None:
            # Cleanup for all devices
            cursor.execute("""
                UPDATE punishment_mode
                SET active = 0
                WHERE active = 1 AND expires_at <= ?
            """, (now,))
        else:
            # Cleanup for specific device
            cursor.execute("""
                UPDATE punishment_mode
                SET active = 0
                WHERE device_id = ? AND active = 1 AND expires_at <= ?
            """, (device_id, now))
        conn.commit()

def revoke_punishment_mode(device_id=None):
    """Revoke active punishment mode"""
    if device_id is None:
        device_id = get_default_device_id()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE punishment_mode
            SET active = 0
            WHERE device_id = ? AND active = 1
        """, (device_id,))
        conn.commit()

def should_port_be_enabled(device_id=None):
    """
    Determine if the port should be enabled based on schedules and overrides
    Priority: punishment mode (highest) > temporary access > schedule > default (enabled)
    """
    if device_id is None:
        device_id = get_default_device_id()

    # Check for active punishment mode first (highest priority - always disables)
    punishment = get_active_punishment_mode(device_id)
    if punishment:
        return False

    # Check for active temporary access (overrides schedule to enable)
    temp_access = get_active_temporary_access(device_id)
    if temp_access:
        return True

    # Check schedules using local time
    now = get_local_now()
    current_day = now.weekday()  # 0=Monday, 6=Sunday
    current_time = now.strftime("%H:%M")

    schedules = get_schedules(device_id)

    # If no schedules, default to enabled
    if not schedules:
        return True

    # Check if current time falls within any schedule for today
    for schedule in schedules:
        if schedule['day_of_week'] == current_day:
            if schedule['start_time'] <= current_time <= schedule['end_time']:
                return True

    # No matching schedule found
    return False
