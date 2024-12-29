document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("toggleButton");

    // Function to fetch the current port state
    const fetchPortState = async () => {
        try {
            const response = await fetch("/api/port/state");
            const data = await response.json();
            updateButtonState(data.enabled);
        } catch (error) {
            console.error("Error fetching port state:", error);
        }
    };

    // Function to toggle the port state
    const togglePort = async () => {
        try {
            const response = await fetch("/api/port/toggle", { method: "POST" });
            const data = await response.json();
            updateButtonState(data.enabled);
        } catch (error) {
            console.error("Error toggling port state:", error);
        }
    };

    // Update the button's appearance and text based on the port state
    const updateButtonState = (enabled) => {
        if (enabled) {
            button.textContent = "Enabled";
            button.className = "enabled";
        } else {
            button.textContent = "Disabled";
            button.className = "disabled";
        }
    };

    // Attach event listener to the button
    button.addEventListener("click", togglePort);

    // Fetch initial port state
    fetchPortState();
});
