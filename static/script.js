const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// Update current time display
function updateCurrentTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { hour12: false });
    const dayString = dayNames[now.getDay() === 0 ? 6 : now.getDay() - 1]; // Adjust: JS Sunday=0, we want Monday=0
    document.getElementById("currentTime").textContent = `${dayString} ${timeString}`;
}

// Function to fetch the current port state
async function fetchPortState() {
    try {
        const response = await fetch("/api/port/state");
        const data = await response.json();
        updateButtonState(data.enabled);
    } catch (error) {
        console.error("Error fetching port state:", error);
    }
}

// Update the button's appearance and text based on the port state
function updateButtonState(enabled) {
    const button = document.getElementById("toggleButton");
    if (enabled) {
        button.textContent = "Enabled";
        button.className = "enabled";
    } else {
        button.textContent = "Disabled";
        button.className = "disabled";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("toggleButton");

    // Function to toggle the port state
    const togglePort = async () => {
        try {
            const response = await fetch("/api/port/toggle", { method: "POST" });
            const data = await response.json();
            updateButtonState(data.enabled);
            await fetchStatus();
        } catch (error) {
            console.error("Error toggling port state:", error);
        }
    };

    // Attach event listener to the button
    button.addEventListener("click", togglePort);

    // Fetch initial state
    fetchPortState();
    fetchStatus();
    fetchSchedules();
    fetchTempAccess();
    fetchPunishment();
    updateCurrentTime();

    // Update time every second
    setInterval(updateCurrentTime, 1000);

    // Auto-refresh status every 10 seconds
    setInterval(() => {
        fetchStatus();
        fetchTempAccess();
        fetchPunishment();
    }, 10000);
});

// Fetch comprehensive status
async function fetchStatus() {
    try {
        const response = await fetch("/api/status");
        const data = await response.json();

        document.getElementById("portStatus").textContent = data.port_state.enabled ? "Enabled" : "Disabled";
        document.getElementById("shouldBeEnabled").textContent = data.should_be_enabled ? "Yes" : "No";
        document.getElementById("scheduleCount").textContent = data.schedules_count;
    } catch (error) {
        console.error("Error fetching status:", error);
    }
}

// Temporary Access Functions
async function grantTempAccess(minutes) {
    try {
        const response = await fetch("/api/temporary-access", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ duration_minutes: minutes })
        });

        if (response.ok) {
            await fetchTempAccess();
            await fetchStatus();
        } else {
            const error = await response.json();
            alert("Error: " + error.error);
        }
    } catch (error) {
        console.error("Error granting temporary access:", error);
    }
}

async function revokeTempAccess() {
    try {
        const response = await fetch("/api/temporary-access", { method: "DELETE" });

        if (response.ok) {
            await fetchTempAccess();
            await fetchStatus();
        }
    } catch (error) {
        console.error("Error revoking temporary access:", error);
    }
}

async function fetchTempAccess() {
    try {
        const response = await fetch("/api/temporary-access");
        const data = await response.json();

        const statusDiv = document.getElementById("tempAccessStatus");

        if (data && data.expires_at) {
            const expiresAt = new Date(data.expires_at);
            const now = new Date();
            const minutesLeft = Math.round((expiresAt - now) / 60000);

            statusDiv.style.display = "block";
            statusDiv.innerHTML = `<strong>Active:</strong> Temporary access expires in ${minutesLeft} minutes (${expiresAt.toLocaleTimeString()})`;
        } else {
            statusDiv.style.display = "none";
        }
    } catch (error) {
        console.error("Error fetching temporary access:", error);
    }
}

// Schedule Management Functions
async function addSchedule() {
    const dayOfWeek = parseInt(document.getElementById("dayOfWeek").value);
    const startTime = document.getElementById("startTime").value;
    const endTime = document.getElementById("endTime").value;

    try {
        const response = await fetch("/api/schedules", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                day_of_week: dayOfWeek,
                start_time: startTime,
                end_time: endTime
            })
        });

        if (response.ok) {
            await fetchSchedules();
            await fetchStatus();
        } else {
            const error = await response.json();
            alert("Error: " + error.error);
        }
    } catch (error) {
        console.error("Error adding schedule:", error);
    }
}

async function deleteSchedule(scheduleId) {
    if (!confirm("Are you sure you want to delete this schedule?")) {
        return;
    }

    try {
        const response = await fetch(`/api/schedules/${scheduleId}`, { method: "DELETE" });

        if (response.ok) {
            await fetchSchedules();
            await fetchStatus();
        }
    } catch (error) {
        console.error("Error deleting schedule:", error);
    }
}

async function fetchSchedules() {
    try {
        const response = await fetch("/api/schedules");
        const schedules = await response.json();

        const listDiv = document.getElementById("scheduleList");

        if (schedules.length === 0) {
            listDiv.innerHTML = '<div class="empty-state">No schedules configured</div>';
        } else {
            listDiv.innerHTML = schedules.map(s => `
                <div class="schedule-item">
                    <span><strong>${dayNames[s.day_of_week]}</strong>: ${s.start_time} - ${s.end_time}</span>
                    <button onclick="deleteSchedule(${s.id})">Delete</button>
                </div>
            `).join("");
        }
    } catch (error) {
        console.error("Error fetching schedules:", error);
    }
}

// Punishment Mode Functions
async function activatePunishment() {
    if (!confirm("This will disable internet until the next scheduled time. Continue?")) {
        return;
    }

    try {
        const response = await fetch("/api/punishment-mode", { method: "POST" });

        if (response.ok) {
            await fetchPunishment();
            await fetchStatus();
            await fetchPortState();  // Update the main toggle button
        } else {
            const error = await response.json();
            alert("Error: " + error.error);
        }
    } catch (error) {
        console.error("Error activating punishment mode:", error);
    }
}

async function revokePunishment() {
    try {
        const response = await fetch("/api/punishment-mode", { method: "DELETE" });

        if (response.ok) {
            await fetchPunishment();
            await fetchStatus();
            await fetchPortState();  // Update the main toggle button
        }
    } catch (error) {
        console.error("Error revoking punishment mode:", error);
    }
}

async function fetchPunishment() {
    try {
        const response = await fetch("/api/punishment-mode");
        const data = await response.json();

        const statusDiv = document.getElementById("punishmentStatus");

        if (data && data.expires_at) {
            const expiresAt = new Date(data.expires_at);
            statusDiv.style.display = "block";
            statusDiv.innerHTML = `<strong>ACTIVE:</strong> Internet disabled until next schedule at ${expiresAt.toLocaleString()}`;
        } else {
            statusDiv.style.display = "none";
        }
    } catch (error) {
        console.error("Error fetching punishment mode:", error);
    }
}
