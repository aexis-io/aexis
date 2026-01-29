import { NetworkVisualizer } from './visualizer.js';


interface DOMElements {
  activePods: HTMLElement | null;
  operationalStations: HTMLElement | null;
  pendingPassengers: HTMLElement | null;
  systemEfficiency: HTMLElement | null;
  eventStream: HTMLElement | null;
  connectionStatus: HTMLElement | null;
  statusText: HTMLElement | null;
  zoomControl: HTMLInputElement | null;
  zoomLevel: HTMLElement | null;
  offlineOverlay?: HTMLElement | null;
}

interface SystemMetrics {
  active_pods?: number;
  operational_stations?: number;
  pending_passengers?: number;
  system_efficiency?: number;
}

interface UpdateMetricsPayload {
  metrics: SystemMetrics;
  stations?: Record<string, unknown>;
  pods?: Record<string, unknown>;
}

interface WebSocketMessage {
  type: string;
  data?: Record<string, unknown>;
  message?: string;
}

type LogEventType = 'info' | 'warning' | 'error' | 'success';
type StatusType = 'online' | 'offline' | 'warning';

let socket: WebSocket | null = null;
let visualizer: NetworkVisualizer | null = null;
let reconnectInterval: number | null = null;
const MAX_EVENTS = 50;

const elements: DOMElements = {
  activePods: document.getElementById('active-pods'),
  operationalStations: document.getElementById('operational-stations'),
  pendingPassengers: document.getElementById('pending-passengers'),
  systemEfficiency: document.getElementById('system-efficiency'),
  eventStream: document.getElementById('event-stream'),
  connectionStatus: document.getElementById('connection-status'),
  statusText: document.getElementById('status-text'),
  zoomControl: document.getElementById('zoom-control') as HTMLInputElement,
  zoomLevel: document.getElementById('zoom-level'),
  offlineOverlay: document.getElementById('offline-overlay')
};

function init(): void {
  try {
    visualizer = new NetworkVisualizer('network-canvas');
  } catch (e) {
    console.error("Visualizer setup failed:", e);
  }

  // setupControls();
  connectWebSocket();
}

function setupControls(): void {
  if (elements.zoomControl) {
    elements.zoomControl.addEventListener('input', (e: Event) => {
      const target = e.target as HTMLInputElement;
      const scale = parseFloat(target.value);
      // if (visualizer) {
      //   visualizer.setZoom(scale);
      // }
      if (elements.zoomLevel) {
        elements.zoomLevel.textContent = Math.round(scale * 100) + '%';
      }
    });
  }

  const pauseBtn = document.querySelector('button:nth-child(1)') as HTMLButtonElement;
  const resetBtn = document.querySelector('button:nth-child(2)') as HTMLButtonElement;

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
      if (!visualizer) return;
      visualizer.resetView();
      if (elements.zoomControl) {
        elements.zoomControl.value = '1.0';
      }
      if (elements.zoomLevel) {
        elements.zoomLevel.textContent = "100%";
      }
    });
  }

  setupLoadGenerator();
}

function setupLoadGenerator(): void {
  const originSelect = document.getElementById('load-origin') as HTMLSelectElement;
  const destSelect = document.getElementById('load-dest') as HTMLSelectElement;
  const typeSelect = document.getElementById('load-type') as HTMLSelectElement;
  const amountInput = document.getElementById('load-amount') as HTMLInputElement;
  const generateBtn = document.getElementById('btn-generate-load') as HTMLButtonElement;

  if (generateBtn) {
    generateBtn.addEventListener('click', async () => {
      const origin = originSelect?.value || '';
      const dest = destSelect?.value || '';
      const type = typeSelect?.value || 'passenger';
      const amount = parseInt(amountInput?.value || '0', 10);

      if (!origin || !dest || origin === dest) {
        logEvent("Invalid Route or Missing Selection", "error");
        return;
      }

      try {
        const endpoint = type === 'passenger'
          ? '/api/manual/passenger'
          : '/api/manual/cargo';

        const payload = {
          origin,
          destination: dest,
          count: amount,
          weight: amount * 100
        };

        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (response.ok) {
          logEvent(
            `${type.toUpperCase()} Request Sent: ${origin} -> ${dest}`,
            "success"
          );
        } else {
          logEvent("Request Failed", "error");
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Unknown error';
        logEvent(`Error: ${errorMsg}`, "error");
      }
    });
  }
}

// --- Dropdown Management ---

let dropdownsPopulated = false;

function updateDropdowns(stations: Record<string, unknown>): void {
  if (dropdownsPopulated || !stations) return;

  const originSelect = document.getElementById('load-origin') as HTMLSelectElement;
  const destSelect = document.getElementById('load-dest') as HTMLSelectElement;

  if (!originSelect || !destSelect) return;

  originSelect.innerHTML = '<option value="">Origin</option>';
  destSelect.innerHTML = '<option value="">Dest</option>';

  Object.keys(stations)
    .sort()
    .forEach(id => {
      const name = id.replace('station_', 'S');
      const originOption = document.createElement('option');
      originOption.value = id;
      originOption.textContent = name;
      originSelect.appendChild(originOption);

      const destOption = document.createElement('option');
      destOption.value = id;
      destOption.textContent = name;
      destSelect.appendChild(destOption);
    });

  dropdownsPopulated = true;
}

// --- WebSocket Connection ---

function connectWebSocket(): void {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    updateStatus('Connected', 'online');
    if (reconnectInterval !== null) {
      clearInterval(reconnectInterval);
      reconnectInterval = null;
    }
    if (elements.offlineOverlay) {
      elements.offlineOverlay.classList.add('hidden');
    }
  };

  socket.onmessage = (event: MessageEvent) => {
    try {
      const data: WebSocketMessage = JSON.parse(event.data);
      handleMessage(data);
    } catch (e) {
      console.error('Failed to parse message:', e);
    }
  };

  socket.onclose = () => {
    updateStatus('Disconnected', 'offline');
    if (elements.offlineOverlay) {
      elements.offlineOverlay.classList.remove('hidden');
    }
    if (reconnectInterval === null) {
      reconnectInterval = window.setInterval(connectWebSocket, 3000);
    }
  };

  socket.onerror = (error: Event) => {
    console.error('WebSocket error:', error);
  };
}

// --- Message Handling ---

function handleMessage(payload: WebSocketMessage): void {
  switch (payload.type) {
    case 'system_state':
      updateMetrics(payload.data as unknown as UpdateMetricsPayload);
      break;

    case 'event':
      // Forward real-time events to visualizer
      if (visualizer && payload.data) {
        const channel = (payload as any).channel || '';
        console.log("channel: ", channel)
        console.log('event_payload: ', payload)
        visualizer.handleEvent(channel, payload.data);
      }
      break;

    case 'pod_decision':
      if (payload.data) {
        logEvent(
          `Pod ${(payload.data as any).pod_id}: ${(payload.data as any).action}`,
          'info'
        );
      }
      break;

    case 'congestion_alert':
      if (payload.data) {
        logEvent(`Congestion at ${(payload.data as any).station_id}`, 'warning');
      }
      break;

    case 'error':
      logEvent(`System Error: ${payload.message || 'Unknown error'}`, 'error');
      break;
  }
}

// --- UI Updates ---

function updateMetrics(data: UpdateMetricsPayload): void {
  if (!data.metrics) return;

  const { metrics } = data;

  if (elements.activePods) {
    elements.activePods.textContent = String(metrics.active_pods || 0);
  }
  if (elements.operationalStations) {
    elements.operationalStations.textContent = String(metrics.operational_stations || 0);
  }
  if (elements.pendingPassengers) {
    elements.pendingPassengers.textContent = String(metrics.pending_passengers || 0);
  }

  const efficiency = Math.round((metrics.system_efficiency || 0) * 100);
  if (elements.systemEfficiency) {
    elements.systemEfficiency.textContent = `${efficiency}%`;
  }

  if (visualizer) {
    visualizer.updateData(data as unknown as Record<string, unknown>);
  }

  if (data.stations) {
    updateDropdowns(data.stations);
  }
}

function updateStatus(text: string, status: StatusType): void {
  const colorMap: Record<StatusType, string> = {
    online: 'text-green-500',
    offline: 'text-red-500',
    warning: 'text-yellow-500'
  };

  if (elements.connectionStatus) {
    const colorClass = colorMap[status] || 'text-gray-400';
    elements.connectionStatus.className = `px-3 py-1 rounded bg-gray-800 text-sm font-bold ${colorClass}`;
    elements.connectionStatus.textContent = text;
  }
}

function logEvent(message: string, type: LogEventType = 'info'): void {
  const div = document.createElement('div');
  const timestamp = new Date().toLocaleTimeString();

  const colorMap: Record<LogEventType, string> = {
    info: 'text-blue-400',
    warning: 'text-yellow-500',
    error: 'text-red-500',
    success: 'text-green-500'
  };

  div.className = `mb-1 font-mono text-sm border-l-2 pl-2 border-gray-700 hover:bg-gray-800 transition-colors py-1`;
  const colorClass = colorMap[type] || 'text-gray-300';
  div.innerHTML = `
        <span class="text-gray-500 text-xs mr-2">[${timestamp}]</span>
        <span class="${colorClass}">${message}</span>
    `;

  if (elements.eventStream) {
    elements.eventStream.insertBefore(div, elements.eventStream.firstChild);

    while (elements.eventStream.children.length > MAX_EVENTS) {
      const last = elements.eventStream.lastChild;
      if (last) {
        elements.eventStream.removeChild(last);
      }
    }
  }
}

// --- Startup ---

document.addEventListener('DOMContentLoaded', init);
