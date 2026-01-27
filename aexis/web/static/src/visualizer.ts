interface Vector2 {
  x: number;
  y: number;
}

/**
 * Node: A topological endpoint. The ONLY place where connectivity exists.
 */
interface Node {
  id: string;
  x: number;
  y: number;
}

/**
 * PathSegment: Geometric primitive.
 */
interface PathSegment {
  start: Vector2;
  end: Vector2;
  length: number;  // Precomputed Euclidean distance
  tangent: Vector2; // Normalized direction vector (end - start)
}

/**
 * PathSpine: The authoritative simulation representation of a connection.
 * Composed of ordered segments forming a continuous polyline.
 */
interface PathSpine {
  id: string;
  startNode: Node;
  endNode: Node;
  segments: PathSegment[];
  totalLength: number; 
}

/**
 * Result of sampling a spine at a specific distance.
 */
interface SpineSample {
  position: Vector2;
  tangent: Vector2;
}

/**
 * Pod: An actor moving along a spine.
 */
interface Pod {
  id: string;
  gfx: PIXI.Graphics;
  spineId: string;
  distanceAlongPath: number; // The authoritative scalar position [0, totalLength]
  speed: number;             // Units per frame/delta
  data: Record<string, unknown>;
}

interface VisualizerConfig {
  bgColor: number;
  gridColor: number;
  spineColor: number;
  gridSize: number;
  layoutScale: number;
  tube: {
    width: number;
    glowWidths: number[];
    glowAlphas: number[];
    glowColor: number;
  };
  palette: number[];
}

interface LayoutSpine {
  id: string;
  points: Vector2[];
}

interface NetworkAdjacency {
  node_id: string;
  weight: number;
}

interface NetworkNode {
  id: string;
  label: string;
  coordinate: Vector2;
  adj: NetworkAdjacency[];
}

interface NetworkData {
  nodes: NetworkNode[];
}

class NetworkVisualizer {
  canvas: HTMLElement | null;
  app: PIXI.Application | null;
  zoom: number;
  pan: Vector2;
  config: VisualizerConfig;
  viewport: PIXI.Container | null;
  gridLayer: PIXI.Graphics | null;
  spineLayer: PIXI.Graphics | null;
  nodeLayer: PIXI.Graphics | null;
  podLayer: PIXI.Container | null;
  spines: Map<string, PathSpine>;
  nodes: Map<string, Node>;
  pods: Map<string, Pod>;

  constructor(canvasId: string) {
    this.canvas = document.getElementById(canvasId);
    this.app = null;

    // Viewport State
    this.zoom = 1.0;
    this.pan = { x: 0, y: 0 };

    // Config
    this.config = {
      bgColor: 0x00050a,
      gridColor: 0x005577,
      spineColor: 0x00fbff,
      gridSize: 100,

      layoutScale: 1,
      tube: {
        width: 1.5,
        glowWidths: [40, 20, 10, 5],
        glowAlphas: [0.05, 0.1, 0.2, 0.4],
        glowColor: 0x00fbff
      },
      palette: [
        0x00fbff, // Cyan
        0xff8800, // Orange
        0xffff00, // Yellow
        0xff0000, // Red
        0xff00ff  // Purple
      ]
    };

    // State
    this.spines = new Map();
    this.nodes = new Map();
    this.pods = new Map();
 
    // Layers
    this.viewport = null;
    this.gridLayer = null;
    this.spineLayer = null;
    this.nodeLayer = null;
    this.podLayer = null;

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
    this.viewport.addChild(this.gridLayer);

    this.spineLayer = new PIXI.Graphics();
    this.viewport.addChild(this.spineLayer);

    this.nodeLayer = new PIXI.Graphics();
    this.viewport.addChild(this.nodeLayer);

    this.podLayer = new PIXI.Container();
    this.viewport.addChild(this.podLayer);

    // Interaction
    this.setupInteraction();

    // Data Load
    await this.loadLayout();

    // Initial draw
    this.drawGrid();

    // Tick
    this.app.ticker.add((delta: number) => this.animate(delta));

    // Handle Resize
    window.addEventListener('resize', () => {
      if (this.app) this.app.resize();
      this.drawGrid();
      this.drawSpines();
    });
    
    console.log('Visualizer initialized');
  }

  setupInteraction(): void {
    if (!this.app) return;
    this.app.stage.eventMode = 'static';
    this.app.stage.hitArea = this.app.screen;

    this.app.stage.on('wheel', (e: WheelEvent) => {
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
    });

    let isPanDragging = false;
    let lastMouse = { x: 0, y: 0 };

    this.app.stage.on('pointerdown', (e: PIXI.FederatedPointerEvent) => {
        isPanDragging = true;
        lastMouse = { x: e.global.x, y: e.global.y };
    });
    this.app.stage.on('pointerup', () => isPanDragging = false);
    this.app.stage.on('pointermove', (e: PIXI.FederatedPointerEvent) => {
        if (isPanDragging) {
            this.pan.x += e.global.x - lastMouse.x;
            this.pan.y += e.global.y - lastMouse.y;
            lastMouse = { x: e.global.x, y: e.global.y };
            this.updateViewport();
        }
    });
  }

  centerView(): void {
    if (!this.app) return;
    this.pan.x = this.app.screen.width / 2;
    this.pan.y = this.app.screen.height / 2;
    this.updateViewport();
  }

  updateViewport(): void {
    if (!this.viewport) return;
    this.viewport.scale.set(this.zoom);
    this.viewport.position.set(this.pan.x, this.pan.y);
    this.drawGrid();
    this.drawSpines();
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
    const gs = this.config.gridSize;
    const startX = -this.pan.x / this.zoom;
    const startY = -this.pan.y / this.zoom;
    const endX = startX + this.app.screen.width / this.zoom;
    const endY = startY + this.app.screen.height / this.zoom;

    // Background Depth
    this.gridLayer.beginFill(0x001122, 0.05);
    this.gridLayer.drawRect(startX, startY, endX - startX, endY - startY);
    this.gridLayer.endFill();

    // Major Grid
    this.gridLayer.lineStyle(1, this.config.gridColor, 0.2);
    for (let x = Math.floor(startX / gs) * gs; x <= endX; x += gs) {
      this.gridLayer.moveTo(x, startY);
      this.gridLayer.lineTo(x, endY);
    }
    for (let y = Math.floor(startY / gs) * gs; y <= endY; y += gs) {
      this.gridLayer.moveTo(startX, y);
      this.gridLayer.lineTo(endX, y);
    }

    // Axis
    this.gridLayer.lineStyle(1, 0x00fbff, 0.1);
    this.gridLayer.moveTo(startX, 0);
    this.gridLayer.lineTo(endX, 0);
    this.gridLayer.moveTo(0, startY);
    this.gridLayer.lineTo(0, endY);
  }

  // Stubs for future implementation
  updateData(data: Record<string, unknown>): void {
    if ((data as any).pods) {
        this.syncPods((data as any).pods);
    }
  }

  syncPods(podsData: Record<string, any>): void {
    for (const [id, data] of Object.entries(podsData)) {
        let pod = this.pods.get(id);
        if (!pod) {
            pod = this.createPod(id, data);
            this.pods.set(id, pod);
        }
        pod.data = data;
        
        // Simple assignment for now, simulation will take over
        if (data.spine_id && pod.spineId !== data.spine_id) {
            pod.spineId = data.spine_id;
            pod.distanceAlongPath = data.distance ?? 0;
        }
    }
  }

  createPod(id: string, data: any): Pod {
    const gfx = new PIXI.Graphics();
    
    // Tiny TRON pod
    gfx.beginFill(0xffffff, 1);
    gfx.drawCircle(0, 0, 3);
    gfx.endFill();
    
    gfx.beginFill(0x00fbff, 0.4);
    gfx.drawCircle(0, 0, 6);
    gfx.endFill();

    if (this.podLayer) this.podLayer.addChild(gfx);

    return {
        id,
        gfx,
        spineId: data.spine_id || "",
        distanceAlongPath: data.distance || 0,
        speed: 1.0,
        data: data
    };
  }

  animate(delta: number): void {
    this.pods.forEach(pod => {
        const spine = this.spines.get(pod.spineId);
        if (!spine) return;

        // Authoritative Movement
        // Note: For now we move forward and loop back for visual feedback
        pod.distanceAlongPath += pod.speed * delta;
        if (pod.distanceAlongPath > spine.totalLength) {
            pod.distanceAlongPath = 0;
        }

        // authoritative sample
        const sample = this.sampleSpine(spine, pod.distanceAlongPath);
        
        // derived view update
        pod.gfx.position.set(sample.position.x, sample.position.y);
        pod.gfx.rotation = Math.atan2(sample.tangent.y, sample.tangent.x);
    });
  }

  async loadLayout(): Promise<void> {
    try {
      const response = await fetch('/static/network.json');
      const data = await response.json() as NetworkData;
      
      // Apply layout scale to coordinates if needed, or assume they are pre-scaled
      // For this network.json, coordinates look like -700, 800, so likely no scale needed or scale = 1
      if (this.config.layoutScale !== 1) {
          data.nodes.forEach(n => {
              n.coordinate.x *= this.config.layoutScale;
              n.coordinate.y *= this.config.layoutScale;
          });
      }

      this.generateLayout(data);
    } catch (e) {
      console.error('Failed to load network.json', e);
    }
  }

  generateLayout(data: NetworkData): void {
    this.spines.clear();
    this.nodes.clear();
    
    if (!data.nodes) return;

    // 1. Create Nodes
    data.nodes.forEach((n) => {
        this.nodes.set(n.id, {
            id: n.id,
            x: n.coordinate.x,
            y: n.coordinate.y
        });
    });

    // 2. Create Spines from Adjacency (Edges)
    const seenEdges = new Set<string>();

    data.nodes.forEach((sourceNode) => {
        if (!sourceNode.adj) return;

        const startNode = this.nodes.get(sourceNode.id);
        if (!startNode) return;

        sourceNode.adj.forEach((adj) => {
            const targetId = adj.node_id;
            const endNode = this.nodes.get(targetId);
            
            if (!endNode) return;

            // Simple deduplication: "minId-maxId"
            const edgeId = [sourceNode.id, targetId].sort().join('-');
            
            if (seenEdges.has(edgeId)) return;
            seenEdges.add(edgeId);

            // Generate geometry (Octilinear path between nodes)
            // Note: We currently just get a path between the two points.
            // If we want more complex routing, we'd need pathfinding.
            const pathPoints = this.getOctilinearPath(startNode.x, startNode.y, endNode.x, endNode.y);
            
            const spine = this.createSpine(pathPoints, edgeId, startNode, endNode);
            this.spines.set(edgeId, spine);
        });
    });
    
    // Inject Mock Pods
    this.pods.clear();
    if (this.podLayer) this.podLayer.removeChildren();
    
    const spineIds = Array.from(this.spines.keys());
    spineIds.forEach((sid, idx) => {
        // Create a few pods per spine for visual busyness
        if (Math.random() > 0.3) {
            const mockPod = this.createPod(`mock_${idx}`, { spine_id: sid });
            mockPod.speed = 1.0 + Math.random() * 2.0;
            this.pods.set(mockPod.id, mockPod);
        }
    });

    this.centerView();
    this.drawSpines();
    this.drawNodes();
  }

  setPaused(p: boolean): void {}
  resetView(): void {
    this.zoom = 1.0;
    this.pan = { x: this.app?.screen.width || 0 / 2, y: this.app?.screen.height || 0 / 2 };
    this.updateViewport();
  }

  /**
   * Factory to create a PathSpine from an ordered list of points.
   * Precomputes all segment lengths and tangents for O(1) sampling lookup.
   */
  createSpine(points: Vector2[], id: string, startNode: Node, endNode: Node): PathSpine {
    const segments: PathSegment[] = [];
    let totalLength = 0;

    for (let i = 0; i < points.length - 1; i++) {
      const start = points[i];
      const end = points[i + 1];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.sqrt(dx * dx + dy * dy);

      if (length > 0) {
        segments.push({
          start,
          end,
          length,
          tangent: { x: dx / length, y: dy / length }
        });
        totalLength += length;
      }
    }

    return { id, startNode, endNode, segments, totalLength };
  }

  /**
   * Generate path between two points. For now, just a straight line.
   * Can be extended for curved or multi-segment paths later.
   */
  getOctilinearPath(x1: number, y1: number, x2: number, y2: number): Vector2[] {
    // Simplified: just return start and end points for a straight line
    return [
      { x: x1, y: y1 },
      { x: x2, y: y2 }
    ];
  }

  /**
   * Core simulation sampler. Returns world position and tangent at dist scalar.
   */
  sampleSpine(spine: PathSpine, dist: number): SpineSample {
    if (spine.segments.length === 0) {
      return { position: { x: 0, y: 0 }, tangent: { x: 1, y: 0 } };
    }

    // Clamp distance to spine bounds
    const clampedDist = Math.max(0, Math.min(dist, spine.totalLength));
    let accumulatedDist = 0;

    for (const seg of spine.segments) {
      if (accumulatedDist + seg.length >= clampedDist) {
        const localDist = clampedDist - accumulatedDist;
        const t = localDist / seg.length;
        
        return {
          position: {
            x: seg.start.x + (seg.end.x - seg.start.x) * t,
            y: seg.start.y + (seg.end.y - seg.start.y) * t
          },
          tangent: seg.tangent
        };
      }
      accumulatedDist += seg.length;
    }

    // Fallback to end of last segment
    const last = spine.segments[spine.segments.length - 1];
    return { position: last.end, tangent: last.tangent };
  }

  /**
   * Renders high-fidelity TRON "tubes" derived strictly from the authoritative spines.
   */
  drawSpines(): void {
    if (!this.spineLayer) return;
    this.spineLayer.clear();

    let i = 0;
    for (const spine of this.spines.values()) {
      const color = this.config.palette[i % this.config.palette.length];
      this.drawDerivedStrokes(spine, color);
      i++;
    }
  }

  drawDerivedStrokes(spine: PathSpine, color: number): void {
    if (!this.spineLayer) return;

    // We can draw a single centered tube, or multiple parallel ones
    const offsets = [0]; // Just center for now, but we can add [-5, 5] for double lines
    
    offsets.forEach(offset => {
        // 1. Layered Glows
        this.config.tube.glowWidths.forEach((width, idx) => {
            this.spineLayer!.lineStyle(width, this.config.tube.glowColor, this.config.tube.glowAlphas[idx]);
            this.drawLayeredPath(spine, offset);
        });

        // 2. Core Brilliant Line
        this.spineLayer.lineStyle(this.config.tube.width, 0xffffff, 0.9);
        this.drawLayeredPath(spine, offset);

        // 3. Primary Color Inner Line
        this.spineLayer.lineStyle(this.config.tube.width - 1, color, 1);
        this.drawLayeredPath(spine, offset);
    });
  }

  drawLayeredPath(spine: PathSpine, offset: number): void {
    if (!this.spineLayer || spine.segments.length === 0) return;
    
    for (let i = 0; i < spine.segments.length; i++) {
        const seg = spine.segments[i];
        const normal = { x: -seg.tangent.y, y: seg.tangent.x };
        
        const startX = seg.start.x + normal.x * offset;
        const startY = seg.start.y + normal.y * offset;
        const endX = seg.end.x + normal.x * offset;
        const endY = seg.end.y + normal.y * offset;

        if (i === 0) {
            this.spineLayer.moveTo(startX, startY);
        }
        this.spineLayer.lineTo(endX, endY);
    }
  }

  /**
   * Renders topological nodes.
   */
  drawNodes(): void {
    if (!this.nodeLayer) return;
    this.nodeLayer.clear();
    
    // Simple glowing dot for nodes
    for (const node of this.nodes.values()) {
        this.nodeLayer.beginFill(0x00fbff, 0.3);
        this.nodeLayer.drawCircle(node.x, node.y, 4);
        this.nodeLayer.endFill();
        
        this.nodeLayer.beginFill(0xffffff, 1);
        this.nodeLayer.drawCircle(node.x, node.y, 1.5);
        this.nodeLayer.endFill();
    }
  }
}

export { NetworkVisualizer };
