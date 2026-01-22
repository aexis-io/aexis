/**
 * AEXIS Visualizer - Node Editor Style
 * Implements Blender-like node graph with sockets and noodles.
 */



interface VisualizerConfig {
  bgColor: number;
  gridColor: number;
  node: {
    width: number;
    height: number;
    headerHeight: number;
    radius: number;
    color: number;
    headerColor: number;
    selectedBorder: number;
    socketRadius: number;
    socketColor: number;
  };
  noodle: {
    width: number;
    color: number;
    activeColor: number;
    curvature: number;
  };
  pod: {
    radius: number;
    color: number;
  };
}

interface StationNode {
  id: string;
  container: PIXI.Container;
  x: number;
  y: number;
  w: number;
  h: number;
  statsText: PIXI.Text;
  socketIn: { x: number; y: number; world: () => { x: number; y: number } };
  socketOut: { x: number; y: number; world: () => { x: number; y: number } };
  data: Record<string, unknown>;
}

interface Pod {
  id: string;
  gfx: PIXI.Graphics;
  x: number;
  y: number;
  currentStationId: string | null;
  isMoving: boolean;
  progress: number;
  targetData?: Record<string, unknown>;
  moveStartStation?: string;
  moveEndStation?: string;
  edge?: Edge;
}

interface Edge {
  from: string;
  to: string;
}

interface Vector2 {
  x: number;
  y: number;
}

class NetworkVisualizer {
  canvas: HTMLElement | null;
  app: PIXI.Application | null;
  stations: Map<string, StationNode>;
  pods: Map<string, Pod>;
  edges: Edge[];
  zoom: number;
  pan: Vector2;
  paused: boolean;
  isDragging: boolean;
  lastMouse: Vector2;
  draggedNode: StationNode | null;
  config: VisualizerConfig;
  viewport: PIXI.Container | null;
  gridLayer: PIXI.Graphics | null;
  noodleLayer: PIXI.Graphics | null;
  nodeLayer: PIXI.Container | null;
  podLayer: PIXI.Container | null;
  uiLayer: PIXI.Container | null;

  constructor(canvasId: string) {
    this.canvas = document.getElementById(canvasId);
    this.app = null;

    // Data Store
    this.stations = new Map();
    this.pods = new Map();
    this.edges = [];

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

    // Layers
    this.viewport = null;
    this.gridLayer = null;
    this.noodleLayer = null;
    this.nodeLayer = null;
    this.podLayer = null;
    this.uiLayer = null;

    this.init();
  }

  async init(): Promise<void> {
    this.app = new PIXI.Application({
      view: this.canvas as HTMLCanvasElement,
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
    this.uiLayer = new PIXI.Container();

    this.viewport.addChild(this.gridLayer);
    this.viewport.addChild(this.noodleLayer);
    this.viewport.addChild(this.nodeLayer);
    this.viewport.addChild(this.podLayer);
    this.app.stage.addChild(this.uiLayer);

    // Interaction
    this.setupInteraction();

    // Initial Layout draw
    this.drawGrid();

    // Tick
    this.app.ticker.add((delta: number) => this.animate(delta));

    // Handle Resize
    window.addEventListener('resize', () => {
      if (this.app) this.app.resize();
      this.drawGrid();
    });
    console.log('Visualizer initialized');
  }

  setupInteraction(): void {
    if (!this.app) return;

    this.app.stage.eventMode = 'static';
    this.app.stage.hitArea = this.app.screen;

    this.app.stage.on('pointerdown', this.onDragStart.bind(this));
    this.app.stage.on('pointerup', this.onDragEnd.bind(this));
    this.app.stage.on('pointerupoutside', this.onDragEnd.bind(this));
    this.app.stage.on('pointermove', this.onDragMove.bind(this));
    this.app.stage.on('wheel', this.onWheel.bind(this));

    this.canvas?.addEventListener('contextmenu', (e: Event) => {
      e.preventDefault();
      this.handleContextMenu(e as MouseEvent);
    });
  }

  handleContextMenu(e: MouseEvent): void {
    const mouseX = e.clientX;
    const mouseY = e.clientY;

    let targetNode: StationNode | null = null;
    for (const [, node] of this.stations) {
      const bounds = node.container.getBounds();
      if (mouseX >= bounds.x && mouseX <= bounds.x + bounds.width &&
        mouseY >= bounds.y && mouseY <= bounds.y + bounds.height) {
        targetNode = node;
        break;
      }
    }

    if (targetNode) {
      console.log(`Context menu for node ${targetNode.id}`);
    }
  }

  onWheel(e: WheelEvent): void {
    e.preventDefault();
    const zoomFactor = 1.1;
    const direction = e.deltaY > 0 ? 1 / zoomFactor : zoomFactor;

    const mouseX = (e as any).global?.x ?? e.clientX;
    const mouseY = (e as any).global?.y ?? e.clientY;

    const worldPos = this.toWorld(mouseX, mouseY);

    this.zoom *= direction;
    this.zoom = Math.max(0.1, Math.min(this.zoom, 5.0));

    this.pan.x = mouseX - worldPos.x * this.zoom;
    this.pan.y = mouseY - worldPos.y * this.zoom;

    this.updateViewport();
  }

  onDragStart(e: PIXI.FederatedPointerEvent): void {
    const mouseX = e.global.x;
    const mouseY = e.global.y;

    let hitNode: StationNode | null = null;
    for (const [, node] of this.stations) {
      const bounds = node.container.getBounds();
      if (mouseX >= bounds.x && mouseX <= bounds.x + bounds.width &&
        mouseY >= bounds.y && mouseY <= bounds.y + bounds.height) {
        hitNode = node;
        break;
      }
    }

    if (hitNode && e.button === 0) {
      this.isDragging = false;
      this.draggedNode = hitNode;
      (this.draggedNode.data as any).dragging = true;
    } else if (e.button === 1 || (e.button === 0 && !hitNode)) {
      this.isDragging = true;
    }

    this.lastMouse = { x: e.global.x, y: e.global.y };
  }

  onDragEnd(e: PIXI.FederatedPointerEvent): void {
    this.isDragging = false;
    if (this.draggedNode) {
      (this.draggedNode.data as any).dragging = false;
      this.draggedNode = null;
    }
  }

  onDragMove(e: PIXI.FederatedPointerEvent): void {
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
      this.drawNoodles();
    }
    this.lastMouse = { x: e.global.x, y: e.global.y };
  }

  updateViewport(): void {
    if (!this.viewport) return;
    this.viewport.scale.set(this.zoom);
    this.viewport.position.set(this.pan.x, this.pan.y);
    this.drawGrid();
  }

  toWorld(screenX: number, screenY: number): Vector2 {
    return {
      x: (screenX - this.pan.x) / this.zoom,
      y: (screenY - this.pan.y) / this.zoom
    };
  }

  drawGrid(): void {
    if (!this.gridLayer || !this.app) return;

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

    this.gridLayer.lineStyle(2, 0x444444, 1);
    this.gridLayer.moveTo(startX, 0);
    this.gridLayer.lineTo(endX, 0);
    this.gridLayer.moveTo(0, startY);
    this.gridLayer.lineTo(0, endY);
  }

  createStationNode(id: string, x: number, y: number, data?: Record<string, unknown>): void {
    if (!this.nodeLayer) return;

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
    bg.drawRoundedRect(0, 0, w, headH, this.config.node.radius);
    bg.drawRect(0, headH - 5, w, 5);
    bg.endFill();
    container.addChild(bg);

    // Header Text
    const titleStyle = new PIXI.TextStyle({
      fontFamily: 'Arial',
      fontSize: 13,
      fill: '#dddddd',
      fontWeight: 'bold'
    });
    const title = new PIXI.Text(id, titleStyle);
    title.x = 10;
    title.y = 5;
    container.addChild(title);

    // Sockets
    const socketIn = this.createSocket(0, h / 2, 0x55ff55);
    container.addChild(socketIn);

    const socketOut = this.createSocket(w, h / 2, 0xffaa00);
    container.addChild(socketOut);

    // Info Text (Stats)
    const statsStyle = new PIXI.TextStyle({
      fontFamily: 'Courier New',
      fontSize: 11,
      fill: '#aaaaaa'
    });
    const stats = new PIXI.Text("Q: 0 | Eff: 100%", statsStyle);
    stats.x = 10;
    stats.y = headH + 10;
    container.addChild(stats);

    this.nodeLayer.addChild(container);

    // Store
    this.stations.set(id, {
      id,
      container,
      x,
      y,
      w,
      h,
      statsText: stats,
      socketIn: {
        x: 0,
        y: h / 2,
        world: () => ({ x: container.x, y: container.y + h / 2 })
      },
      socketOut: {
        x: w,
        y: h / 2,
        world: () => ({ x: container.x + w, y: container.y + h / 2 })
      },
      data: data || {}
    });
  }

  createSocket(x: number, y: number, color: number): PIXI.Graphics {
    const gfx = new PIXI.Graphics();
    gfx.beginFill(this.config.node.socketColor);
    gfx.drawCircle(0, 0, this.config.node.socketRadius);
    gfx.endFill();

    gfx.beginFill(color);
    gfx.drawCircle(0, 0, this.config.node.socketRadius - 2);
    gfx.endFill();
    gfx.position.set(x, y);
    return gfx;
  }

  drawNoodles(): void {
    if (!this.noodleLayer) return;

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

  drawBezier(x1: number, y1: number, x2: number, y2: number, color: number): void {
    if (!this.noodleLayer) return;

    this.noodleLayer.lineStyle(this.config.noodle.width, color, 1);

    const dist = Math.abs(x2 - x1) * 0.5;
    const cp1x = x1 + dist;
    const cp1y = y1;
    const cp2x = x2 - dist;
    const cp2y = y2;

    this.noodleLayer.moveTo(x1, y1);
    this.noodleLayer.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x2, y2);
  }

  updateData(data: Record<string, unknown>): void {
    if ((data as any).stations) {
      if (this.stations.size === 0) {
        this.generateLayout((data as any).stations);
      }

      for (const [id, sData] of Object.entries((data as any).stations)) {
        const node = this.stations.get(id);
        if (node) {
          const q = ((sData as any).queues?.passengers?.waiting || 0);
          node.statsText.text = `Q: ${q} | Eff: 100%`;
          node.data  = sData as Record<string, unknown>;
        }
      }
    }

    if ((data as any).pods) {
      this.syncPods((data as any).pods);
    }
  }

  generateLayout(stationsData: Record<string, unknown>): void {
    const stationIds = Object.keys(stationsData);
    const count = stationIds.length;
    const radius = 400;
    const centerX = 0;
    const centerY = 0;

    // Create Nodes
    stationIds.forEach((id, i) => {
      const angle = (i / count) * Math.PI * 2;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;
      this.createStationNode(
        id,
        x - this.config.node.width / 2,
        y - this.config.node.height / 2,
        (stationsData as any)[id]
      );
    });

    // Create Edges from Data
    this.edges = [];
    stationIds.forEach(id => {
      const station = (stationsData as any)[id];
      if (station.connected_stations) {
        station.connected_stations.forEach((targetId: string) => {
          this.edges.push({ from: id, to: targetId });
        });
      }
    });

    this.centerView();
    this.drawNoodles();
  }

  syncPods(podsData: Record<string, unknown>): void {
    for (const [id, data] of Object.entries(podsData)) {
      let pod = this.pods.get(id);
      if (!pod) {
        pod = this.createPod(id);
        this.pods.set(id, pod);
      }
      pod.targetData = data as Record<string, unknown>;
    }
  }

  createPod(id: string): Pod {
    if (!this.podLayer) {
      throw new Error('Pod layer not initialized');
    }

    const gfx = new PIXI.Graphics();
    gfx.beginFill(this.config.pod.color);
    gfx.drawCircle(0, 0, this.config.pod.radius);
    gfx.endFill();
    this.podLayer.addChild(gfx);

    return {
      id,
      gfx,
      x: 0,
      y: 0,
      currentStationId: null,
      isMoving: false,
      progress: 0
    };
  }

  animate(delta: number): void {
    if (this.paused) return;

    this.pods.forEach(pod => {
      if (!pod.targetData) return;

      const targetLocId = (pod.targetData as any).location;

      // Initialization
      if (!pod.currentStationId) {
        pod.currentStationId = targetLocId;
        this.snapPodToStation(pod, targetLocId, 'in');
        return;
      }

      // Detect Move
      if (pod.currentStationId !== targetLocId && !pod.isMoving) {
        console.log(`Pod ${pod.id} moving ${pod.currentStationId} -> ${targetLocId}`);
        const edge = this.findEdge(pod.currentStationId, targetLocId);
        if (edge) {
          pod.isMoving = true;
          pod.moveStartStation = pod.currentStationId;
          pod.moveEndStation = targetLocId;
          pod.progress = 0;
          pod.edge = edge;
        } else {
          pod.currentStationId = targetLocId;
          this.snapPodToStation(pod, targetLocId, 'in');
        }
      }

      // Animate Move
      if (pod.isMoving) {
        const speed = 0.02 * delta;
        pod.progress += speed;

        if (pod.progress >= 1.0) {
          pod.isMoving = false;
          pod.progress = 0;
          pod.currentStationId = pod.moveEndStation || null;
          if (pod.currentStationId) {
            this.snapPodToStation(pod, pod.currentStationId, 'in');
          }
        } else {
          const fromNode = this.stations.get(pod.moveStartStation || '');
          const toNode = this.stations.get(pod.moveEndStation || '');
          if (fromNode && toNode) {
            const start = fromNode.socketOut.world();
            const end = toNode.socketIn.world();
            const pos = this.getBezierPoint(pod.progress, start.x, start.y, end.x, end.y);
            pod.gfx.x = pos.x;
            pod.gfx.y = pos.y;
          }
        }
      } else {
        if (pod.currentStationId) {
          this.snapPodToStation(pod, pod.currentStationId, 'in');
        }
      }
    });
  }

  findEdge(fromId: string, toId: string): Edge | undefined {
    return this.edges.find(e => e.from === fromId && e.to === toId);
  }

  snapPodToStation(pod: Pod, stationId: string, socketType: 'in' | 'out' = 'in'): void {
    const station = this.stations.get(stationId);
    if (station) {
      const pos = socketType === 'in' ? station.socketIn.world() : station.socketOut.world();
      pod.gfx.x = pos.x;
      pod.gfx.y = pos.y;
    }
  }

  getBezierPoint(t: number, x1: number, y1: number, x2: number, y2: number): Vector2 {
    const dist = Math.abs(x2 - x1) * 0.5;
    const cp1x = x1 + dist;
    const cp1y = y1;
    const cp2x = x2 - dist;
    const cp2y = y2;

    const mt = 1 - t;
    const mt2 = mt * mt;
    const mt3 = mt2 * mt;
    const t2 = t * t;
    const t3 = t2 * t;

    const x = mt3 * x1 + 3 * mt2 * t * cp1x + 3 * mt * t2 * cp2x + t3 * x2;
    const y = mt3 * y1 + 3 * mt2 * t * cp1y + 3 * mt * t2 * cp2y + t3 * y2;

    return { x, y };
  }

  centerView(): void {
    if (!this.app) return;
    this.pan.x = this.app.screen.width / 2;
    this.pan.y = this.app.screen.height / 2;
    this.updateViewport();
  }

  setPaused(p: boolean): void {
    this.paused = p;
  }

  resetView(): void {
    this.centerView();
    this.zoom = 1.0;
    this.updateViewport();
  }

  setZoom(z: number): void {
    this.zoom = z;
    this.updateViewport();
  }
}

export { NetworkVisualizer };
