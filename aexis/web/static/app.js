
// State
let socket = null;
let chart = null;
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
    offlineOverlay: document.getElementById('offline-overlay')
};

// Initialize
function init() {
    initChart();
    connectWebSocket();
}

// Chart.js Setup
function initChart() {
    const ctx = document.getElementById('performance-chart').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array(EFFICIENCY_HISTORY_LENGTH).fill(''),
            datasets: [{
                label: 'System Efficiency',
                data: Array(EFFICIENCY_HISTORY_LENGTH).fill(0),
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                tension: 0.1,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    ticks: { color: '#9ca3af', callback: v => v + '%' }
                },
                x: {
                    grid: { display: false },
                    ticks: { display: false }
                }
            }
        }
    });
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

    // Update Chart
    const newData = chart.data.datasets[0].data;
    newData.shift();
    newData.push(efficiency);
    chart.update();
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
