let editingDeviceId = null;

// Load all devices
async function loadDevices() {
    try {
        const response = await fetch("/api/devices");
        const devices = await response.json();

        const listDiv = document.getElementById("deviceList");

        if (devices.length === 0) {
            listDiv.innerHTML = '<div class="empty-state">No devices configured</div>';
        } else {
            listDiv.innerHTML = devices.map(device => `
                <div class="device-item ${device.is_default ? 'default' : ''}">
                    <div class="device-info">
                        <div class="device-name">
                            ${device.alias}
                            ${device.is_default ? '<span class="device-badge">DEFAULT</span>' : ''}
                        </div>
                        <div class="device-details">
                            IP: ${device.ip} | Port: ${device.port_id} | Username: ${device.username}
                        </div>
                    </div>
                    <div class="device-actions">
                        <button class="btn btn-primary" onclick="editDevice(${device.id})">Edit</button>
                        <button class="btn btn-danger" onclick="deleteDevice(${device.id}, '${device.alias}')"
                                ${devices.length <= 1 ? 'disabled title="Cannot delete the last device"' : ''}>
                            Delete
                        </button>
                    </div>
                </div>
            `).join("");
        }
    } catch (error) {
        console.error("Error loading devices:", error);
        showError("Failed to load devices");
    }
}

// Show add device modal
function showAddModal() {
    editingDeviceId = null;
    document.getElementById("modalTitle").textContent = "Add Device";
    document.getElementById("deviceForm").reset();
    document.getElementById("deviceId").value = "";
    document.getElementById("errorMessage").style.display = "none";
    document.getElementById("deviceModal").classList.add("active");
}

// Edit existing device
async function editDevice(deviceId) {
    try {
        const response = await fetch(`/api/devices/${deviceId}`);
        if (!response.ok) {
            throw new Error("Failed to fetch device");
        }
        const device = await response.json();

        editingDeviceId = deviceId;
        document.getElementById("modalTitle").textContent = "Edit Device";
        document.getElementById("deviceId").value = deviceId;
        document.getElementById("alias").value = device.alias;
        document.getElementById("ip").value = device.ip;
        document.getElementById("portId").value = device.port_id;
        document.getElementById("username").value = device.username;
        document.getElementById("password").value = device.password;
        document.getElementById("isDefault").checked = device.is_default === 1;
        document.getElementById("errorMessage").style.display = "none";
        document.getElementById("deviceModal").classList.add("active");
    } catch (error) {
        console.error("Error loading device:", error);
        showError("Failed to load device details");
    }
}

// Save device (add or update)
async function saveDevice() {
    const deviceId = document.getElementById("deviceId").value;
    const data = {
        alias: document.getElementById("alias").value,
        ip: document.getElementById("ip").value,
        port_id: parseInt(document.getElementById("portId").value),
        username: document.getElementById("username").value,
        password: document.getElementById("password").value,
        is_default: document.getElementById("isDefault").checked
    };

    try {
        let response;
        if (deviceId) {
            // Update existing device
            response = await fetch(`/api/devices/${deviceId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data)
            });
        } else {
            // Add new device
            response = await fetch("/api/devices", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data)
            });
        }

        if (response.ok) {
            closeModal();
            await loadDevices();
        } else {
            const error = await response.json();
            showError(error.error || "Failed to save device");
        }
    } catch (error) {
        console.error("Error saving device:", error);
        showError("Failed to save device");
    }
}

// Delete device
async function deleteDevice(deviceId, alias) {
    if (!confirm(`Are you sure you want to delete "${alias}"?\n\nThis will also delete all schedules, temporary access grants, and punishment mode settings for this device.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: "DELETE"
        });

        if (response.ok) {
            await loadDevices();
        } else {
            const error = await response.json();
            alert("Error: " + (error.error || "Failed to delete device"));
        }
    } catch (error) {
        console.error("Error deleting device:", error);
        alert("Failed to delete device");
    }
}

// Close modal
function closeModal() {
    document.getElementById("deviceModal").classList.remove("active");
    document.getElementById("deviceForm").reset();
    editingDeviceId = null;
}

// Show error message
function showError(message) {
    const errorDiv = document.getElementById("errorMessage");
    errorDiv.textContent = message;
    errorDiv.style.display = "block";
}

// Close modal when clicking outside
document.getElementById("deviceModal").addEventListener("click", function(e) {
    if (e.target === this) {
        closeModal();
    }
});

// Load devices on page load
document.addEventListener("DOMContentLoaded", () => {
    loadDevices();
});
