// State
let socket = null;
let visualizer = null;
let reconnectInterval = null;
const MAX_EVENTS = 50;
const EFFICIENCY_HISTORY_LENGTH = 30;

// DOM Elements
const elements = {
    activePods: document.getElementById('active-pods'),
    operationalStations: document.getElementById('operational-stations'),
    pendingPassengers: document.getElementById('pending-passengers'),
    systemEfficiency: document.getElementById('system-efficiency'),
    eventStream: document.getElementById('event-stream'),
    connectionStatus: document.getElementById('connection-status'),
    statusText: document.getElementById('status-text'),
    zoomControl: document.getElementById('zoom-control'),
    zoomLevel: document.getElementById('zoom-level')
};

// Initialize
function init() {
    // Initialize Visualizer
    try {
        visualizer = new NetworkVisualizer('network-canvas');
        console.log("Visualizer initialized");
    } catch (e) {
        console.error("Visualizer setup failed:", e);
    }

    setupControls();
    connectWebSocket();
}

function setupControls() {
    if (elements.zoomControl) {
        elements.zoomControl.addEventListener('input', (e) => {
            const scale = parseFloat(e.target.value);
            if (visualizer) visualizer.setZoom(scale);
            if (elements.zoomLevel) elements.zoomLevel.textContent = Math.round(scale * 100) + '%';
        });
    }

    const pauseBtn = document.querySelector('button:nth-child(1)'); // "PAUSE SIM"
    const resetBtn = document.querySelector('button:nth-child(2)'); // "RESET VIEW"

    if (pauseBtn) {
        pauseBtn.addEventListener('click', () => {
            if (!visualizer) return;
            const isPaused = pauseBtn.textContent === "RESUME SIM";
            visualizer.setPaused(!isPaused);
            pauseBtn.textContent = isPaused ? "PAUSE SIM" : "RESUME SIM";
            pauseBtn.classList.toggle('bg-blue-600');
            pauseBtn.classList.toggle('bg-yellow-600');
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            if (visualizer) {
                visualizer.resetView();
                if (elements.zoomControl) elements.zoomControl.value = 1.0;
                if (elements.zoomLevel) elements.zoomLevel.textContent = "100%";
            }
        });
    }

    setupLoadGenerator();
}

function setupLoadGenerator() {
    const originSelect = document.getElementById('load-origin');
    const destSelect = document.getElementById('load-dest');
    const typeSelect = document.getElementById('load-type');
    const amountInput = document.getElementById('load-amount');
    const generateBtn = document.getElementById('btn-generate-load');

    if (generateBtn) {
        generateBtn.addEventListener('click', async () => {
            const origin = originSelect.value;
            const dest = destSelect.value;
            const type = typeSelect.value;
            const amount = parseInt(amountInput.value);

            if (!origin || !dest || origin === dest) {
                logEvent("Invalid Route or Missing Selection", "error");
                return;
            }

            try {
                const endpoint = type === 'passenger' ? '/api/manual/passenger' : '/api/manual/cargo';
                const payload = {
                    origin: origin,
                    destination: dest,
                    count: amount,
                    weight: amount * 100 // Approximation for cargo
                };

                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    logEvent(`${type.toUpperCase()} Request Sent: ${origin} -> ${dest}`, "success");
                } else {
                    logEvent("Request Failed", "error");
                }

            } catch (e) {
                logEvent(`Error: ${e.message}`, "error");
            }
        });
    }
}

// Helper to populate dropdowns once data arrives
let dropdownsPopulated = false;
function updateDropdowns(stations) {
    if (dropdownsPopulated || !stations) return;

    const originSelect = document.getElementById('load-origin');
    const destSelect = document.getElementById('load-dest');

    // Clear
    originSelect.innerHTML = '<option value="">Origin</option>';
    destSelect.innerHTML = '<option value="">Dest</option>';

    Object.keys(stations).sort().forEach(id => {
        const name = id.replace('station_', 'S'); // Short name
        originSelect.innerHTML += `<option value="${id}">${name}</option>`;
        destSelect.innerHTML += `<option value="${id}">${name}</option>`;
    });

    dropdownsPopulated = true;
}

// WebSocket Connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        updateStatus('Connected', 'online');
        if (reconnectInterval) {
            clearInterval(reconnectInterval);
            reconnectInterval = null;
        }
        elements.offlineOverlay.classList.add('hidden');
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleMessage(data);
        } catch (e) {
            console.error('Failed to parse message:', e);
        }
    };

    socket.onclose = () => {
        updateStatus('Disconnected', 'offline');
        elements.offlineOverlay.classList.remove('hidden');
        if (!reconnectInterval) {
            reconnectInterval = setInterval(connectWebSocket, 3000);
        }
    };

    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Message Handling
function handleMessage(payload) {
    switch (payload.type) {
        case 'system_state':
            updateMetrics(payload.data);
            break;
        case 'pod_decision':
            logEvent(`Pod ${payload.data.pod_id}: ${payload.data.action}`, 'info');
            // Optimistically update pod in visualizer if needed, though system_state handles positions
            break;
        case 'congestion_alert':
            logEvent(`Congestion at ${payload.data.station_id}`, 'warning');
            break;
        case 'error':
            logEvent(`System Error: ${payload.message}`, 'error');
            break;
    }
}

// UI Updates
function updateMetrics(data) {
    if (!data.metrics) return;

    const { metrics } = data;

    elements.activePods.textContent = metrics.active_pods || 0;
    elements.operationalStations.textContent = metrics.operational_stations || 0;
    elements.pendingPassengers.textContent = metrics.pending_passengers || 0;

    const efficiency = Math.round((metrics.system_efficiency || 0) * 100);
    elements.systemEfficiency.textContent = `${efficiency}%`;

    if (visualizer) {
        visualizer.updateData(data);
    }

    if (data.stations) {
        updateDropdowns(data.stations);
    }
}

function updateStatus(text, status) {
    const colors = {
        online: 'text-green-500',
        offline: 'text-red-500',
        warning: 'text-yellow-500'
    };

    elements.connectionStatus.className = `px-3 py-1 rounded bg-gray-800 text-sm font-bold ${colors[status] || 'text-gray-400'}`;
    elements.connectionStatus.textContent = text;
}

function logEvent(message, type = 'info') {
    const div = document.createElement('div');
    const timestamp = new Date().toLocaleTimeString();

    const colors = {
        info: 'text-blue-400',
        warning: 'text-yellow-500',
        error: 'text-red-500',
        success: 'text-green-500'
    };

    div.className = `mb-1 font-mono text-sm border-l-2 pl-2 border-gray-700 hover:bg-gray-800 transition-colors py-1`;
    div.innerHTML = `
        <span class="text-gray-500 text-xs mr-2">[${timestamp}]</span>
        <span class="${colors[type] || 'text-gray-300'}">${message}</span>
    `;

    elements.eventStream.insertBefore(div, elements.eventStream.firstChild);

    // Cleanup old events
    while (elements.eventStream.children.length > MAX_EVENTS) {
        elements.eventStream.removeChild(elements.eventStream.lastChild);
    }
}

// Start
document.addEventListener('DOMContentLoaded', init);
