/**
 * AEXIS Visualizer - Node Editor Style
 * Implements Blender-like node graph with sockets and noodles.
 */

class NetworkVisualizer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.app = null;

        // Data Store
        this.stations = new Map(); // id -> station object
        this.pods = new Map();     // id -> pod object
        this.edges = [];           // Array of {from, to, curveData}

        // Viewport State
        this.zoom = 1.0;
        this.pan = { x: 0, y: 0 };
        this.paused = false;
        this.isDragging = false;
        this.lastMouse = { x: 0, y: 0 };
        this.draggedNode = null;

        // Config
        this.config = {
            bgColor: 0x1a1a1a,
            gridColor: 0x2a2a2a,
            node: {
                width: 140,
                height: 80,
                headerHeight: 24,
                radius: 4,
                color: 0x333333,
                headerColor: 0x555555,
                selectedBorder: 0xffaa00,
                socketRadius: 5,
                socketColor: 0x888888
            },
            noodle: {
                width: 3,
                color: 0x888888,
                activeColor: 0xffaa00,
                curvature: 0.5
            },
            pod: {
                radius: 6,
                color: 0x00ff88
            }
        };

        this.init();
    }

    async init() {
        this.app = new PIXI.Application({
            view: this.canvas,
            resizeTo: window,
            antialias: true,
            backgroundColor: this.config.bgColor,
            resolution: window.devicePixelRatio || 1
        });

        // Setup Containers
        this.viewport = new PIXI.Container();
        this.app.stage.addChild(this.viewport);

        this.gridLayer = new PIXI.Graphics();
        this.noodleLayer = new PIXI.Graphics();
        this.nodeLayer = new PIXI.Container();
        this.podLayer = new PIXI.Container();
        this.uiLayer = new PIXI.Container(); // For context menus etc

        this.viewport.addChild(this.gridLayer);
        this.viewport.addChild(this.noodleLayer);
        this.viewport.addChild(this.nodeLayer);
        this.viewport.addChild(this.podLayer);
        this.app.stage.addChild(this.uiLayer); // UI stays screen-space if needed, but context menus likely track world

        // Interaction
        this.setupInteraction();

        // Initial Layout draw
        this.drawGrid();

        // Tick
        this.app.ticker.add((delta) => this.animate(delta));

        // Handle Resize
        window.addEventListener('resize', () => {
            this.app.resize();
            this.drawGrid();
        });
    }

    setupInteraction() {
        this.app.stage.eventMode = 'static';
        this.app.stage.hitArea = this.app.screen;

        this.app.stage.on('pointerdown', this.onDragStart.bind(this));
        this.app.stage.on('pointerup', this.onDragEnd.bind(this));
        this.app.stage.on('pointerupoutside', this.onDragEnd.bind(this));
        this.app.stage.on('pointermove', this.onDragMove.bind(this));
        this.app.stage.on('wheel', this.onWheel.bind(this));

        // Disable context menu on canvas to allow custom one
        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.handleContextMenu(e);
        });
    }

    handleContextMenu(e) {
        // Simple hit test for nodes
        const mouseX = e.clientX;
        const mouseY = e.clientY;

        // Convert screen to world
        const worldPos = this.toWorld(mouseX, mouseY);

        let targetNode = null;
        for (const [id, node] of this.stations) {
            const bounds = node.container.getBounds(); // Screen bounds
            if (mouseX >= bounds.x && mouseX <= bounds.x + bounds.width &&
                mouseY >= bounds.y && mouseY <= bounds.y + bounds.height) {
                targetNode = node;
                break;
            }
        }

        if (targetNode) {
            console.log(`Context menu for node ${targetNode.id}`);
            // Logic to show HTML context menu at (mouseX, mouseY) would go here
        }
    }

    onWheel(e) {
        e.preventDefault();
        const zoomFactor = 1.1;
        const direction = e.deltaY > 0 ? 1 / zoomFactor : zoomFactor;

        // Zoom towards mouse pointer
        const mouseX = e.global.x;
        const mouseY = e.global.y;

        const worldPos = this.toWorld(mouseX, mouseY);

        this.zoom *= direction;
        // Clamp zoom
        this.zoom = Math.max(0.1, Math.min(this.zoom, 5.0));

        this.pan.x = mouseX - worldPos.x * this.zoom;
        this.pan.y = mouseY - worldPos.y * this.zoom;

        this.updateViewport();
    }

    onDragStart(e) {
        // check hit on node first
        const mouseX = e.global.x;
        const mouseY = e.global.y;

        let hitNode = null;
        // Search in reverse draw order (topmost first)
        // Optimization: could use Pixi's interaction manager better, but custom loop gives fine control
        for (const [id, node] of this.stations) {
            const bounds = node.container.getBounds();
            if (mouseX >= bounds.x && mouseX <= bounds.x + bounds.width &&
                mouseY >= bounds.y && mouseY <= bounds.y + bounds.height) {
                hitNode = node;
                break;
            }
        }

        if (hitNode && e.button === 0) { // Left click node
            this.isDragging = false; // It's a node drag
            this.draggedNode = hitNode;
            this.draggedNode.data.dragging = true;
        } else if (e.button === 1 || (e.button === 0 && !hitNode)) { // Middle click or Left click bg
            this.isDragging = true;
        }

        this.lastMouse = { x: e.global.x, y: e.global.y };
    }

    onDragEnd(e) {
        this.isDragging = false;
        if (this.draggedNode) {
            this.draggedNode.data.dragging = false;
            this.draggedNode = null;
        }
    }

    onDragMove(e) {
        if (this.isDragging) {
            const dx = e.global.x - this.lastMouse.x;
            const dy = e.global.y - this.lastMouse.y;
            this.pan.x += dx;
            this.pan.y += dy;
            this.updateViewport();
        } else if (this.draggedNode) {
            const dx = (e.global.x - this.lastMouse.x) / this.zoom;
            const dy = (e.global.y - this.lastMouse.y) / this.zoom;
            this.draggedNode.x += dx;
            this.draggedNode.y += dy;
            this.draggedNode.container.position.set(this.draggedNode.x, this.draggedNode.y);
            this.drawNoodles(); // Redraw edges connected to this node
        }
        this.lastMouse = { x: e.global.x, y: e.global.y };
    }

    updateViewport() {
        this.viewport.scale.set(this.zoom);
        this.viewport.position.set(this.pan.x, this.pan.y);
        this.drawGrid(); // Re-draw grid to cover screen if needed (or shader based)
    }

    toWorld(screenX, screenY) {
        return {
            x: (screenX - this.pan.x) / this.zoom,
            y: (screenY - this.pan.y) / this.zoom
        };
    }

    // --- Rendering ---

    drawGrid() {
        this.gridLayer.clear();
        // Simple grid implementation
        // For production, use a TilingSprite or Shader
        const spacing = 100 * this.zoom;
        const offsetX = this.pan.x % spacing;
        const offsetY = this.pan.y % spacing;

        this.gridLayer.lineStyle(1, this.config.gridColor, 0.5);

        // Vertical lines
        for (let x = offsetX; x < this.app.screen.width; x += spacing) {
            this.gridLayer.moveTo(x, 0);
            this.gridLayer.lineTo(x, this.app.screen.height);
        }

        // Horizontal lines
        for (let y = offsetY; y < this.app.screen.height; y += spacing) {
            this.gridLayer.moveTo(0, y);
            this.gridLayer.lineTo(this.app.screen.width, y);
        }

        // Since grid layer is IN viewport, we need to counter-transform it or just draw large rect?
        // Actually, easiest is to draw world-space lines in the viewport container
        this.gridLayer.clear();
        this.gridLayer.lineStyle(2, this.config.gridColor, 0.2);

        const startX = -this.pan.x / this.zoom;
        const startY = -this.pan.y / this.zoom;
        const endX = startX + this.app.screen.width / this.zoom;
        const endY = startY + this.app.screen.height / this.zoom;
        const gridSize = 100;

        const firstGridX = Math.floor(startX / gridSize) * gridSize;
        const firstGridY = Math.floor(startY / gridSize) * gridSize;

        for (let x = firstGridX; x <= endX; x += gridSize) {
            this.gridLayer.moveTo(x, startY);
            this.gridLayer.lineTo(x, endY);
        }
        for (let y = firstGridY; y <= endY; y += gridSize) {
            this.gridLayer.moveTo(startX, y);
            this.gridLayer.lineTo(endX, y);
        }

        // Axis lines
        this.gridLayer.lineStyle(2, 0x444444, 1);
        this.gridLayer.moveTo(startX, 0); this.gridLayer.lineTo(endX, 0);
        this.gridLayer.moveTo(0, startY); this.gridLayer.lineTo(0, endY);
    }

    createStationNode(id, x, y, data) {
        const container = new PIXI.Container();
        container.position.set(x, y);

        const w = this.config.node.width;
        const h = this.config.node.height;
        const headH = this.config.node.headerHeight;

        // Shadow
        const shadow = new PIXI.Graphics();
        shadow.beginFill(0x000000, 0.3);
        shadow.drawRoundedRect(5, 5, w, h, this.config.node.radius);
        container.addChild(shadow);

        // Body
        const bg = new PIXI.Graphics();
        bg.beginFill(this.config.node.color);
        bg.drawRoundedRect(0, 0, w, h, this.config.node.radius);
        bg.endFill();

        // Header
        bg.beginFill(this.config.node.headerColor);
        bg.drawRoundedRect(0, 0, w, headH, this.config.node.radius); // Top corners rounded
        bg.drawRect(0, headH - 5, w, 5); // Rect to cover bottom corners of header
        bg.endFill();
        container.addChild(bg);

        // Header Text
        const titleStyle = new PIXI.TextStyle({
            fontFamily: 'Arial', fontSize: 13, fill: '#dddddd', fontWeight: 'bold'
        });
        const title = new PIXI.Text(id, titleStyle);
        title.x = 10;
        title.y = 5;
        container.addChild(title);

        // Sockets
        // In (Left)
        const socketIn = this.createSocket(0, h / 2, 0x55ff55);
        container.addChild(socketIn);

        // Out (Right)
        const socketOut = this.createSocket(w, h / 2, 0xffaa00);
        container.addChild(socketOut);

        // Info Text (Stats)
        const statsStyle = new PIXI.TextStyle({ fontFamily: 'Courier New', fontSize: 11, fill: '#aaaaaa' });
        const stats = new PIXI.Text("Q: 0 | Eff: 100%", statsStyle);
        stats.x = 10;
        stats.y = headH + 10;
        container.addChild(stats);

        this.nodeLayer.addChild(container);

        // Store
        this.stations.set(id, {
            id,
            container,
            x, y,
            w, h,
            statsText: stats,
            socketIn: { x: 0, y: h / 2, world: () => { return { x: container.x, y: container.y + h / 2 } } },
            socketOut: { x: w, y: h / 2, world: () => { return { x: container.x + w, y: container.y + h / 2 } } },
            data: data || {}
        });
    }

    createSocket(x, y, color) {
        const gfx = new PIXI.Graphics();
        gfx.beginFill(this.config.node.socketColor);
        gfx.drawCircle(0, 0, this.config.node.socketRadius);
        gfx.endFill();
        // Inner dot
        gfx.beginFill(color);
        gfx.drawCircle(0, 0, this.config.node.socketRadius - 2);
        gfx.endFill();
        gfx.position.set(x, y);
        return gfx;
    }

    drawNoodles() {
        this.noodleLayer.clear();

        for (const edge of this.edges) {
            const fromNode = this.stations.get(edge.from);
            const toNode = this.stations.get(edge.to);

            if (fromNode && toNode) {
                const start = fromNode.socketOut.world();
                const end = toNode.socketIn.world();

                this.drawBezier(start.x, start.y, end.x, end.y, this.config.noodle.color);
            }
        }
    }

    drawBezier(x1, y1, x2, y2, color) {
        this.noodleLayer.lineStyle(this.config.noodle.width, color, 1);

        const dist = Math.abs(x2 - x1) * 0.5;
        const cp1x = x1 + dist; // Control point 1 (right of start)
        const cp1y = y1;
        const cp2x = x2 - dist; // Control point 2 (left of end)
        const cp2y = y2;

        this.noodleLayer.moveTo(x1, y1);
        this.noodleLayer.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x2, y2);
    }

    // --- Data Sync ---

    updateData(data) {
        if (data.stations) {
            // First run?
            if (this.stations.size === 0) {
                this.generateLayout(data.stations);
            }

            // Update stats
            for (const [id, sData] of Object.entries(data.stations)) {
                const node = this.stations.get(id);
                if (node) {
                    const q = (sData.queues?.passengers?.waiting || 0);
                    node.statsText.text = `Q: ${q} | Eff: 100%`;
                    // Color header if congested?
                    node.data = sData;
                    // Update edges if dynamic topology change support needed (omitted for now)
                }
            }
        }

        if (data.pods) {
            this.syncPods(data.pods);
        }
    }

    generateLayout(stationsData) {
        const stationIds = Object.keys(stationsData);
        const count = stationIds.length;
        const radius = 400;
        const centerX = 0;
        const centerY = 0; // World center

        // Create Nodes
        stationIds.forEach((id, i) => {
            const angle = (i / count) * Math.PI * 2;
            const x = centerX + Math.cos(angle) * radius;
            const y = centerY + Math.sin(angle) * radius;

            this.createStationNode(id, x - this.config.node.width / 2, y - this.config.node.height / 2, stationsData[id]);
        });

        // Create Edges from Data
        this.edges = [];
        stationIds.forEach(id => {
            const station = stationsData[id];
            if (station.connected_stations) {
                station.connected_stations.forEach(targetId => {
                    // Avoid duplicate edges if bidirectional? No, draw arrows ideally.
                    // For now, simple dedupe or directional
                    // The backend sends all neighbors. 
                    this.edges.push({ from: id, to: targetId });
                });
            }
        });

        this.centerView();
        this.drawNoodles();
    }

    syncPods(podsData) {
        // Simplified pod sync to match noodle paths
        // For accurate path following, we need to know WHERE on the bezier they are
        // We'll create simple sprites for now that lerp between stations directly 
        // (but ideally should follow the bezier curve function)

        for (const [id, data] of Object.entries(podsData)) {
            let pod = this.pods.get(id);
            if (!pod) {
                pod = this.createPod(id);
                this.pods.set(id, pod);
            }
            pod.targetData = data;
        }
    }

    createPod(id) {
        const gfx = new PIXI.Graphics();
        gfx.beginFill(this.config.pod.color);
        gfx.drawCircle(0, 0, this.config.pod.radius);
        gfx.endFill();
        this.podLayer.addChild(gfx);
        return { id, gfx, x: 0, y: 0, currentStationId: null, isMoving: false, progress: 0 };
    }

    animate(delta) {
        if (this.paused) return;

        this.pods.forEach(pod => {
            if (!pod.targetData) return;

            // State Machine for Pod Animation
            // 1. Idle at Station
            // 2. Transitioning (Moving from A to B)

            const targetLocId = pod.targetData.location;

            // Initialization
            if (!pod.currentStationId) {
                pod.currentStationId = targetLocId;
                this.snapPodToStation(pod, targetLocId, 'in');
                return;
            }

            // Detect Move
            if (pod.currentStationId !== targetLocId && !pod.isMoving) {
                console.log(`Pod ${pod.id} moving ${pod.currentStationId} -> ${targetLocId}`);
                // Start Move
                const edge = this.findEdge(pod.currentStationId, targetLocId);
                if (edge) {
                    pod.isMoving = true;
                    pod.moveStartStation = pod.currentStationId;
                    pod.moveEndStation = targetLocId;
                    pod.progress = 0;
                    pod.edge = edge;
                } else {
                    // Jump if no edge found (teleport)
                    pod.currentStationId = targetLocId;
                    this.snapPodToStation(pod, targetLocId, 'in');
                }
            }

            // Animate Move
            if (pod.isMoving) {
                // Speed factor
                const speed = 0.02 * delta;
                pod.progress += speed;

                if (pod.progress >= 1.0) {
                    // Arrived
                    pod.isMoving = false;
                    pod.progress = 0;
                    pod.currentStationId = pod.moveEndStation;
                    this.snapPodToStation(pod, pod.currentStationId, 'in');
                } else {
                    // Interpolate along Bezier
                    const fromNode = this.stations.get(pod.moveStartStation);
                    const toNode = this.stations.get(pod.moveEndStation);
                    if (fromNode && toNode) {
                        const start = fromNode.socketOut.world();
                        const end = toNode.socketIn.world();
                        const pos = this.getBezierPoint(pod.progress, start.x, start.y, end.x, end.y);
                        pod.gfx.x = pos.x;
                        pod.gfx.y = pos.y;
                    }
                }
            } else {
                // Idle handling (maybe jitter or stay at socket)
                this.snapPodToStation(pod, pod.currentStationId, 'in');
            }
        });
    }

    findEdge(fromId, toId) {
        // Since edges array is simple {from, to}, find it
        // Note: Graph might be directed or undirected. Assuming directed for noodles.
        return this.edges.find(e => e.from === fromId && e.to === toId);
    }

    snapPodToStation(pod, stationId, socketType = 'in') {
        const station = this.stations.get(stationId);
        if (station) {
            // Snap to In socket by default
            const pos = socketType === 'in' ? station.socketIn.world() : station.socketOut.world();
            pod.gfx.x = pos.x;
            pod.gfx.y = pos.y;
        }
    }

    getBezierPoint(t, x1, y1, x2, y2) {
        // Cubic Bezier with control points at dist/2
        const dist = Math.abs(x2 - x1) * 0.5;
        const cp1x = x1 + dist;
        const cp1y = y1;
        const cp2x = x2 - dist;
        const cp2y = y2;

        // Formula: (1-t)^3*P0 + 3*(1-t)^2*t*P1 + 3*(1-t)*t^2*P2 + t^3*P3
        const mt = 1 - t;
        const mt2 = mt * mt;
        const mt3 = mt2 * mt;
        const t2 = t * t;
        const t3 = t2 * t;

        const x = mt3 * x1 + 3 * mt2 * t * cp1x + 3 * mt * t2 * cp2x + t3 * x2;
        const y = mt3 * y1 + 3 * mt2 * t * cp1y + 3 * mt * t2 * cp2y + t3 * y2;

        return { x, y };
    }

    centerView() {
        this.pan.x = this.app.screen.width / 2;
        this.pan.y = this.app.screen.height / 2;
        this.updateViewport();
    }

    setPaused(p) { this.paused = p; }
    resetView() { this.centerView(); this.zoom = 1.0; this.updateViewport(); }
    setZoom(z) { this.zoom = z; this.updateViewport(); }
}
