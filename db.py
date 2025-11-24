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

        # Schedules table - stores weekly recurring schedules
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_of_week INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                UNIQUE(day_of_week, start_time, end_time)
            )
        """)

        # Temporary access table - stores one-time access grants
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS temporary_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                granted_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                active INTEGER DEFAULT 1
            )
        """)

        # Punishment mode table - stores forced disable until next schedule
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS punishment_mode (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                active INTEGER DEFAULT 1
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

def add_schedule(day_of_week, start_time, end_time):
    """
    Add a weekly schedule
    day_of_week: 0=Monday, 1=Tuesday, ..., 6=Sunday
    start_time: "HH:MM" format (e.g., "07:00")
    end_time: "HH:MM" format (e.g., "22:00")
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO schedules (day_of_week, start_time, end_time, enabled)
            VALUES (?, ?, ?, 1)
        """, (day_of_week, start_time, end_time))
        conn.commit()
        return cursor.lastrowid

def get_schedules():
    """Get all schedules"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedules WHERE enabled = 1 ORDER BY day_of_week, start_time")
        return [dict(row) for row in cursor.fetchall()]

def delete_schedule(schedule_id):
    """Delete a schedule by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()

def grant_temporary_access(duration_minutes):
    """
    Grant temporary access for a specified duration
    If temp access is already active, extends it by the additional duration
    Returns the expiration time
    """
    now = get_local_now()

    # Check if there's already active temporary access
    existing = get_active_temporary_access()

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
                INSERT INTO temporary_access (granted_at, expires_at, active)
                VALUES (?, ?, 1)
            """, (now.isoformat(), expires_at.isoformat()))
            conn.commit()
            return {
                "id": cursor.lastrowid,
                "granted_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "extended": False
            }

def get_active_temporary_access():
    """Get active temporary access grant (if any)"""
    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM temporary_access
            WHERE active = 1 AND expires_at > ?
            ORDER BY expires_at DESC
            LIMIT 1
        """, (now,))
        row = cursor.fetchone()
        return dict(row) if row else None

def cleanup_expired_temporary_access():
    """Mark expired temporary access grants as inactive"""
    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE temporary_access
            SET active = 0
            WHERE active = 1 AND expires_at <= ?
        """, (now,))
        conn.commit()

def revoke_temporary_access():
    """Revoke all active temporary access"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE temporary_access SET active = 0 WHERE active = 1")
        conn.commit()

def get_next_schedule_start():
    """
    Calculate when the next schedule window starts
    Returns datetime or None if no schedules
    """
    now = get_local_now()
    current_day = now.weekday()
    current_time = now.strftime("%H:%M")

    schedules = get_schedules()
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

def activate_punishment_mode():
    """
    Activate punishment mode - disables internet until next schedule starts
    """
    now = get_local_now()
    next_start = get_next_schedule_start()

    if not next_start:
        # No schedules, can't activate punishment mode
        return None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO punishment_mode (activated_at, expires_at, active)
            VALUES (?, ?, 1)
        """, (now.isoformat(), next_start.isoformat()))
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "activated_at": now.isoformat(),
            "expires_at": next_start.isoformat()
        }

def get_active_punishment_mode():
    """Get active punishment mode (if any)"""
    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM punishment_mode
            WHERE active = 1 AND expires_at > ?
            ORDER BY expires_at DESC
            LIMIT 1
        """, (now,))
        row = cursor.fetchone()
        return dict(row) if row else None

def cleanup_expired_punishment_mode():
    """Mark expired punishment mode as inactive"""
    now = get_local_now().isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE punishment_mode
            SET active = 0
            WHERE active = 1 AND expires_at <= ?
        """, (now,))
        conn.commit()

def revoke_punishment_mode():
    """Revoke active punishment mode"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE punishment_mode SET active = 0 WHERE active = 1")
        conn.commit()

def should_port_be_enabled():
    """
    Determine if the port should be enabled based on schedules and overrides
    Priority: punishment mode (highest) > temporary access > schedule > default (enabled)
    """
    # Check for active punishment mode first (highest priority - always disables)
    punishment = get_active_punishment_mode()
    if punishment:
        return False

    # Check for active temporary access (overrides schedule to enable)
    temp_access = get_active_temporary_access()
    if temp_access:
        return True

    # Check schedules using local time
    now = get_local_now()
    current_day = now.weekday()  # 0=Monday, 6=Sunday
    current_time = now.strftime("%H:%M")

    schedules = get_schedules()

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
