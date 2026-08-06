import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";

const ENTITY_PALETTE = [
  "#22c55e",
  "#38bdf8",
  "#f472b6",
  "#facc15",
  "#a78bfa",
  "#fb923c",
  "#34d399",
  "#f87171",
];

const LINK_COLORS = {
  defines: "#71717a",
  imports: "#facc15",
  used_in: "#2dd4bf",
  uses: "#22c55e",
};

const PITCH_LIMIT = Math.PI / 2 - 0.01;
const LOOK_SENSITIVITY = 0.005;
const THRUST_SPEED = 350;
const THRUST_DECAY = 0.3;
const FIT_MARGIN = 1.15;
const DRAG_THRESHOLD = 6;
const ORBIT_DEFAULT_DIST = 200;

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function hashString(s) {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function nodeColor(node) {
  if (node.kind === "file") return "#e4e4e7";
  return ENTITY_PALETTE[hashString(node.file || "") % ENTITY_PALETTE.length];
}

function nodeRadius(node) {
  return node.kind === "file" ? 10 : 2 + (node.label?.length || 4) * 0.11;
}

function makeLabelSprite(text, color, height) {
  const canvas = document.createElement("canvas");
  const fontPx = 28;
  const ctx = canvas.getContext("2d");
  ctx.font = `bold ${fontPx}px monospace`;
  const textW = ctx.measureText(text).width;
  const pad = 14;
  canvas.width = Math.ceil(textW + pad * 2);
  canvas.height = Math.ceil(fontPx + pad);
  const c = canvas.getContext("2d");
  c.font = `bold ${fontPx}px monospace`;
  c.fillStyle = color;
  c.textBaseline = "middle";
  c.fillText(text, pad, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false })
  );
  const aspect = canvas.width / canvas.height;
  sprite.scale.set(aspect * height, height, 1);
  return sprite;
}

export default function ForceGraph3DView({ graph, selectedId, onSelect }) {
  const fgRef = useRef();
  const controlsRef = useRef(null);
  const containerRef = useRef(null);
  const draggingRef = useRef(false);
  const rafRef = useRef(0);
  const lastTargetRef = useRef(new THREE.Vector3());

  const [mode, setMode] = useState("fly");
  const modeRef = useRef(mode);
  modeRef.current = mode;

  const lookRef = useRef({ yaw: 0, pitch: 0 });
  const flyRafRef = useRef(0);
  const lastTimeRef = useRef(0);
  const velRef = useRef(new THREE.Vector3());
  const turnDragRef = useRef(null);
  const pressRef = useRef(null);
  const dragNodeRef = useRef(null);
  const nodeDragRef = useRef(false);
  const homeRef = useRef(null);
  const centroidRef = useRef(null);
  const maxDistRef = useRef(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [size, setSize] = useState({ width: 0, height: 0 });

  const graphData = useMemo(
    () => ({
      nodes: graph?.nodes ?? [],
      links: (graph?.edges ?? []).map((e) => ({
        source: e.source,
        target: e.target,
        type: e.type,
      })),
    }),
    [graph]
  );

  const nodeObject = useMemo(
    () => (node) => {
      const radius = nodeRadius(node);
      const selected = node.id === selectedId;
      const baseColor = nodeColor(node);
      const group = new THREE.Group();
      group.add(
        new THREE.Mesh(
          new THREE.SphereGeometry(radius, 20, 20),
          new THREE.MeshBasicMaterial({
            color: selected ? "#ffffff" : baseColor,
            transparent: true,
            opacity: selected ? 1 : 0.92,
          })
        )
      );
      const labelHeight = radius * 0.8;
      const sprite = makeLabelSprite(
        node.label,
        selected ? "#ffffff" : "#cbd5e1",
        labelHeight
      );
      sprite.position.y = radius + labelHeight * 0.6;
      group.add(sprite);
      return group;
    },
    [selectedId]
  );

  function applyModeToControls() {
    const controls = controlsRef.current;
    if (!controls) return;
    if (modeRef.current === "fly") {
      controls.enabled = false;
      return;
    }
    controls.enabled = true;
    const camera = fgRef.current?.camera?.();
    if (camera) {
      const dir = new THREE.Vector3();
      camera.getWorldDirection(dir);
      const dist = clamp(
        camera.position.distanceTo(lastTargetRef.current) || ORBIT_DEFAULT_DIST,
        50,
        4000
      );
      const target = camera.position
        .clone()
        .addScaledVector(dir, dist);
      controls.target.copy(target);
      lastTargetRef.current.copy(target);
    }
  }

  function onKeyDown(e) {
    if (e.code !== "Space" && e.code !== "KeyR") return;
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target.isContentEditable) {
      return;
    }
    e.preventDefault();
    if (e.code === "Space") {
      setMode((m) => (m === "fly" ? "orbit" : "fly"));
    } else {
      resetNavigation();
    }
  }

  function pickNodeAt(e) {
    const el = containerRef.current;
    const camera = fgRef.current?.camera?.();
    const nodes = graphData.nodes;
    if (!el || !camera || !nodes.length) return null;
    const rect = el.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -(((e.clientY - rect.top) / rect.height) * 2 - 1)
    );
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, camera);
    let best = null;
    let bestAlong = Infinity;
    for (const node of nodes) {
      if (!Number.isFinite(node.x) || !Number.isFinite(node.y) || !Number.isFinite(node.z)) continue;
      const center = new THREE.Vector3(node.x, node.y, node.z);
      const radius = nodeRadius(node);
      if (raycaster.ray.distanceSqToPoint(center) > radius * radius) continue;
      const along = center.sub(raycaster.ray.origin).dot(raycaster.ray.direction);
      if (along < bestAlong) {
        bestAlong = along;
        best = node;
      }
    }
    return best;
  }

  function onPointerMove(e) {
    if (modeRef.current !== "fly") return;
    if (turnDragRef.current) {
      const drag = turnDragRef.current;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      drag.x = e.clientX;
      drag.y = e.clientY;
      const look = lookRef.current;
      look.yaw -= dx * LOOK_SENSITIVITY;
      look.pitch = clamp(look.pitch - dy * LOOK_SENSITIVITY, -PITCH_LIMIT, PITCH_LIMIT);
      return;
    }
    const press = pressRef.current;
    if (!press) return;
    if (dragNodeRef.current) {
      moveDraggedNode(e);
      return;
    }
    const dist = Math.hypot(e.clientX - press.x, e.clientY - press.y);
    if (dist > DRAG_THRESHOLD) {
      press.dragged = true;
      if (press.node) {
        startNodeDrag(press.node);
        moveDraggedNode(e);
      }
    }
  }

  function startNodeDrag(node) {
    dragNodeRef.current = node;
    nodeDragRef.current = true;
    node.fx = node.x;
    node.fy = node.y;
    node.fz = node.z;
    fgRef.current?.d3ReheatSimulation?.();
  }

  function moveDraggedNode(e) {
    const node = dragNodeRef.current;
    const camera = fgRef.current?.camera?.();
    const el = containerRef.current;
    if (!node || !camera || !el) return;
    const rect = el.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -(((e.clientY - rect.top) / rect.height) * 2 - 1)
    );
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, camera);
    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    const plane = new THREE.Plane();
    plane.setFromNormalAndCoplanarPoint(forward, new THREE.Vector3(node.x, node.y, node.z));
    const point = new THREE.Vector3();
    if (raycaster.ray.intersectPlane(plane, point)) {
      node.fx = node.x = point.x;
      node.fy = node.y = point.y;
      node.fz = node.z = point.z;
    }
  }

  function finishNodeDrag() {
    const node = dragNodeRef.current;
    if (node) {
      delete node.fx;
      delete node.fy;
      delete node.fz;
    }
    dragNodeRef.current = null;
    nodeDragRef.current = false;
    fgRef.current?.d3ReheatSimulation?.();
  }

  function onPointerDown(e) {
    if (modeRef.current !== "fly") return;
    const el = containerRef.current;
    if (!el) return;
    if (e.button === 0) {
      pressRef.current = {
        x: e.clientX,
        y: e.clientY,
        node: pickNodeAt(e),
        pointerId: e.pointerId,
      };
      dragNodeRef.current = null;
      el.setPointerCapture?.(e.pointerId);
    } else if (e.button === 2) {
      turnDragRef.current = { x: e.clientX, y: e.clientY };
      el.setPointerCapture?.(e.pointerId);
    }
  }

  function onPointerUp(e) {
    const el = containerRef.current;
    el?.releasePointerCapture?.(e.pointerId);
    if (e.button === 2) {
      turnDragRef.current = null;
      return;
    }
    if (e.button !== 0) return;
    if (dragNodeRef.current) {
      finishNodeDrag();
    } else if (pressRef.current && !pressRef.current.dragged) {
      const press = pressRef.current;
      onSelectRef.current(press.node || null);
    }
    pressRef.current = null;
  }

  function onPointerCancel() {
    turnDragRef.current = null;
    pressRef.current = null;
    if (dragNodeRef.current) finishNodeDrag();
  }

  function onContextMenu(e) {
    if (modeRef.current !== "fly") return;
    e.preventDefault();
  }

  function onWheel(e) {
    if (modeRef.current !== "fly") return;
    e.preventDefault();
    const camera = fgRef.current?.camera?.();
    if (!camera) return;
    const dir = new THREE.Vector3();
    camera.getWorldDirection(dir);
    const sign = e.deltaY < 0 ? 1 : -1;
    velRef.current.copy(dir).multiplyScalar(sign * THRUST_SPEED);
  }

  function updateFly(dt) {
    const camera = fgRef.current?.camera?.();
    if (!camera) return;
    const vel = velRef.current;

    vel.multiplyScalar(Math.exp(-dt / THRUST_DECAY));
    if (!nodeDragRef.current) {
      camera.position.addScaledVector(vel, dt);
    }

    const centroid = centroidRef.current;
    const maxDist = maxDistRef.current;
    if (centroid && maxDist) {
      const off = new THREE.Vector3().subVectors(camera.position, centroid);
      const len = off.length();
      if (len > maxDist) {
        camera.position.copy(centroid).addScaledVector(off.normalize(), maxDist);
      }
    }

    const { yaw, pitch } = lookRef.current;
    camera.quaternion.setFromEuler(new THREE.Euler(pitch, yaw, 0, "YXZ"));
  }

  function fitToGraph() {
    const camera = fgRef.current?.camera?.();
    const nodes = graphData.nodes;
    if (!camera || !nodes.length) return;
    const centroid = new THREE.Vector3();
    let count = 0;
    for (const n of nodes) {
      if (Number.isFinite(n.x) && Number.isFinite(n.y) && Number.isFinite(n.z)) {
        centroid.x += n.x;
        centroid.y += n.y;
        centroid.z += n.z;
        count += 1;
      }
    }
    if (!count) return;
    centroid.multiplyScalar(1 / count);
    let radius = 0;
    for (const n of nodes) {
      if (!Number.isFinite(n.x)) continue;
      radius = Math.max(
        radius,
        Math.hypot(n.x - centroid.x, n.y - centroid.y, n.z - centroid.z)
      );
    }
    const fovRad = (camera.fov * Math.PI) / 180;
    const maxDist = Math.max((radius / Math.tan(fovRad / 2)) * FIT_MARGIN, 50);
    const position = centroid.clone().add(new THREE.Vector3(0, 0, maxDist));
    camera.position.copy(position);
    camera.lookAt(centroid);
    const euler = new THREE.Euler(0, 0, 0, "YXZ");
    euler.setFromQuaternion(camera.quaternion);
    lookRef.current = { yaw: euler.y, pitch: euler.x };
    homeRef.current = {
      position: position.clone(),
      quaternion: camera.quaternion.clone(),
      target: centroid.clone(),
    };
    centroidRef.current = centroid;
    maxDistRef.current = maxDist;
    const controls = controlsRef.current;
    if (controls) controls.maxDistance = maxDist;
  }

  function resetNavigation() {
    const home = homeRef.current;
    const camera = fgRef.current?.camera?.();
    if (!home || !camera) return;
    camera.position.copy(home.position);
    camera.quaternion.copy(home.quaternion);
    const controls = controlsRef.current;
    if (controls) {
      controls.target.copy(home.target);
      if (maxDistRef.current) controls.maxDistance = maxDistRef.current;
    }
    const euler = new THREE.Euler(0, 0, 0, "YXZ");
    euler.setFromQuaternion(home.quaternion);
    lookRef.current = { yaw: euler.y, pitch: euler.x };
  }

  useEffect(() => {
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ width, height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!graphData.nodes.length) return undefined;
    const timer = setTimeout(() => {
      fitToGraph();
    }, 1200);
    return () => clearTimeout(timer);
  }, [graph]);

  useEffect(() => {
    let attempts = 0;
    const timer = setInterval(() => {
      const controls = fgRef.current?.controls?.();
      if (controls && "zoomToCursor" in controls) {
        controls.zoomToCursor = true;
        clearInterval(timer);

        controlsRef.current = controls;
        const onStart = () => {
          draggingRef.current = true;
        };
        const onEnd = () => {
          draggingRef.current = false;
        };
        controls.addEventListener("start", onStart);
        controls.addEventListener("end", onEnd);

        const raycaster = new THREE.Raycaster();
        const ndc = new THREE.Vector2(0, 0);
        const normal = new THREE.Vector3();
        const plane = new THREE.Plane();
        const point = new THREE.Vector3();

        const updatePivot = () => {
          if (modeRef.current === "orbit" && !draggingRef.current) {
            const fg = fgRef.current;
            const ctrls = controlsRef.current;
            if (fg && ctrls) {
              const camera = fg.camera();
              if (camera) {
                raycaster.setFromCamera(ndc, camera);
                camera.getWorldDirection(normal);
                plane.setFromNormalAndCoplanarPoint(normal, ctrls.target);
                if (raycaster.ray.intersectPlane(plane, point)) {
                  ctrls.target.copy(point);
                  lastTargetRef.current.copy(point);
                }
              }
            }
          }
          rafRef.current = requestAnimationFrame(updatePivot);
        };
        updatePivot();

        applyModeToControls();
        if (maxDistRef.current) controls.maxDistance = maxDistRef.current;

        return () => {
          controls.removeEventListener("start", onStart);
          controls.removeEventListener("end", onEnd);
          cancelAnimationFrame(rafRef.current);
          controlsRef.current = null;
        };
      } else if (++attempts > 40) {
        clearInterval(timer);
      }
    }, 100);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (mode !== "fly") {
      applyModeToControls();
      return undefined;
    }

    const camera = fgRef.current?.camera?.();
    if (camera) {
      const euler = new THREE.Euler(0, 0, 0, "YXZ");
      euler.setFromQuaternion(camera.quaternion);
      lookRef.current = { yaw: euler.y, pitch: euler.x };
    }
    velRef.current.set(0, 0, 0);
    applyModeToControls();

    const el = containerRef.current;
    if (el) {
      el.addEventListener("pointermove", onPointerMove);
      el.addEventListener("pointerdown", onPointerDown);
      el.addEventListener("pointerup", onPointerUp);
      el.addEventListener("pointercancel", onPointerCancel);
      el.addEventListener("contextmenu", onContextMenu);
      el.addEventListener("wheel", onWheel, { passive: false });
    }
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerCancel);

    lastTimeRef.current = performance.now();
    const tick = (now) => {
      const dt = clamp((now - lastTimeRef.current) / 1000, 0.001, 0.05);
      lastTimeRef.current = now;
      updateFly(dt);
      flyRafRef.current = requestAnimationFrame(tick);
    };
    flyRafRef.current = requestAnimationFrame(tick);

    return () => {
      if (el) {
        el.removeEventListener("pointermove", onPointerMove);
        el.removeEventListener("pointerdown", onPointerDown);
        el.removeEventListener("pointerup", onPointerUp);
        el.removeEventListener("pointercancel", onPointerCancel);
        el.removeEventListener("contextmenu", onContextMenu);
        el.removeEventListener("wheel", onWheel);
      }
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerCancel);
      cancelAnimationFrame(flyRafRef.current);
      velRef.current.set(0, 0, 0);
      turnDragRef.current = null;
      pressRef.current = null;
      if (dragNodeRef.current) finishNodeDrag();
    };
  }, [mode]);

  return (
    <div ref={containerRef} className="absolute inset-0">
      <ForceGraph3D
        ref={fgRef}
        graphData={graphData}
        width={size.width || undefined}
        height={size.height || undefined}
        backgroundColor="#0c0c0c"
        nodeThreeObject={nodeObject}
        linkColor={(l) => LINK_COLORS[l.type] || "#22c55e"}
        linkWidth={1.2}
        onNodeClick={(node) => node && onSelect(node)}
        onBackgroundClick={() => onSelect(null)}
        showNavInfo={false}
        enableNodeDrag={false}
        enablePointerInteraction={mode === "orbit"}
        controlType="orbit"
      />

      {mode === "fly" && (
        <div className="pointer-events-none absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2">
          <div className="relative h-4 w-4">
            <span className="absolute left-1/2 top-0 h-4 w-px -translate-x-1/2 bg-primary/70" />
            <span className="absolute left-0 top-1/2 h-px w-4 -translate-y-1/2 bg-primary/70" />
            <span className="absolute left-1/2 top-1/2 h-1 w-1 -translate-x-1/2 -translate-y-1/2 bg-primary" />
          </div>
        </div>
      )}

      <div className="absolute top-2 right-2 z-10 flex flex-col items-end gap-2 select-none">
        <div className="join">
          <button
            type="button"
            className={`btn btn-xs join-item font-mono uppercase ${
              mode === "fly" ? "btn-primary" : "btn-outline"
            }`}
            onClick={() => setMode("fly")}
          >
            Fly
          </button>
          <button
            type="button"
            className={`btn btn-xs join-item font-mono uppercase ${
              mode === "orbit" ? "btn-primary" : "btn-outline"
            }`}
            onClick={() => setMode("orbit")}
          >
            Orbit
          </button>
        </div>

        <button
          type="button"
          className="btn btn-xs btn-outline font-mono uppercase"
          onClick={resetNavigation}
        >
          Reset
        </button>

        <div className="border-2 border-base-300 bg-base-200 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-base-content/70">
          {mode === "fly" ? (
            <span>R-drag turn · scroll move · click node · drag node · R reset · space mode</span>
          ) : (
            <span>Drag rotate · wheel zoom · R reset · space mode</span>
          )}
        </div>
      </div>
    </div>
  );
}
