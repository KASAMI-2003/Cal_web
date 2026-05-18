import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { pythonApi } from '../api/pythonApi';
import { getAuthState } from '../auth/authStore';

type VizKind = 'E' | 'nu_max' | 'vl';
type ScanMode = 'off' | 'sweep-T' | 'sweep-P' | 'sweep-comp';

interface VizWindow {
  id: string;
  kind: VizKind;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
  minimized: boolean;
  closed: boolean;
}

interface WindowColorConfig {
  auto: boolean;
  min: number | '';
  max: number | '';
}

interface WindowRenderContext {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  frameId: number;
  resizeObserver: ResizeObserver | null;
  baseRadius: number;
}

interface TwinCaps {
  T?: { detected?: boolean; min?: number; max?: number; n_unique?: number };
  P?: { detected?: boolean; min?: number; max?: number; n_unique?: number };
  composition?: { detected?: boolean; n?: number; labels?: string[] };
  note?: string;
  active_kind?: string;
}

interface TwinProps {
  bulk_modulus_GPa?: number;
  shear_modulus_GPa?: number;
  young_modulus_GPa?: number;
  volume_scale?: number;
  model?: string;
}

interface TwinSavedFile {
  id: string;
  filename: string;
  originalName?: string;
  kind?: string;
}

const DEFAULT_WINDOWS: VizWindow[] = [
  { id: 'win-E', kind: 'E', title: "(a) Young's modulus E", x: 12, y: 12, w: 520, h: 320, z: 3, minimized: false, closed: false },
  { id: 'win-nu', kind: 'nu_max', title: '(b) Max Poisson ν_max', x: 560, y: 12, w: 520, h: 320, z: 2, minimized: false, closed: false },
  { id: 'win-vl', kind: 'vl', title: '(c) Longitudinal v_l', x: 12, y: 350, w: 1068, h: 260, z: 1, minimized: false, closed: false },
];

const DEFAULT_COLOR_CONFIG: Record<string, WindowColorConfig> = {
  'win-E': { auto: true, min: '', max: '' },
  'win-nu': { auto: true, min: '', max: '' },
  'win-vl': { auto: true, min: '', max: '' },
};

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

function getSurfaceGrid(data: any, kind: VizKind): number[][] | null {
  const raw = kind === 'vl' ? (data?.vl ?? data?.v_l) : data?.[kind];
  if (!raw) return null;
  if (Array.isArray(raw) && Array.isArray(raw[0])) return raw as number[][];
  if (Array.isArray(raw.values) && Array.isArray(raw.values[0])) return raw.values as number[][];
  return null;
}

function getGridMinMax(data: any, kind: VizKind): { min: number; max: number } | null {
  const block = data?.[kind];
  const grid = getSurfaceGrid(data, kind);
  if (!grid || grid.length === 0 || !Array.isArray(grid[0])) {
    return null;
  }
  if (block && typeof block === 'object' && Number.isFinite(Number(block.min)) && Number.isFinite(Number(block.max))) {
    return { min: Number(block.min), max: Number(block.max) };
  }
  let min = Infinity;
  let max = -Infinity;
  for (const row of grid) {
    for (const raw of row) {
      const value = Number(raw);
      if (Number.isFinite(value)) {
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
  return { min, max };
}

function createSurfaceMesh(
  data: any,
  kind: VizKind,
  colorConf: WindowColorConfig,
  colorRangeOverride?: { min: number; max: number } | null,
): { mesh: THREE.Mesh | null; min: number; max: number } {
  const grid = getSurfaceGrid(data, kind);
  if (!grid || grid.length === 0 || !Array.isArray(grid[0])) {
    return { mesh: null, min: 0, max: 0 };
  }
  // 后端 values 形状与原网页一致：values[n_phi][n_theta]
  // 这里必须与 legacy twin_visual.js 相同参数化，避免 v_l 出现“方形/拉伸”伪影。
  const nPhi = grid.length;
  const nTheta = grid[0].length;
  if (nPhi < 2 || nTheta < 2) return { mesh: null, min: 0, max: 0 };

  const base = getGridMinMax(data, kind);
  if (!base) return { mesh: null, min: 0, max: 0 };

  const useManual = !colorConf.auto && colorConf.min !== '' && colorConf.max !== '' && Number(colorConf.max) > Number(colorConf.min);
  const useOverride =
    !!colorRangeOverride &&
    Number.isFinite(Number(colorRangeOverride.min)) &&
    Number.isFinite(Number(colorRangeOverride.max)) &&
    Number(colorRangeOverride.max) > Number(colorRangeOverride.min);
  const cMin = useManual ? Number(colorConf.min) : useOverride ? Number(colorRangeOverride!.min) : base.min;
  const cMax = useManual ? Number(colorConf.max) : useOverride ? Number(colorRangeOverride!.max) : base.max;
  const range = Math.max(1e-8, cMax - cMin);
  // 与原网页保持一致：半径直接取物理值，不做归一化放大。
  // 这样在各向同性时会自然显示为球形，不会引入额外形变。

  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];

  for (let i = 0; i < nPhi; i++) {
    const phi = (i / (nPhi - 1)) * Math.PI;
    for (let j = 0; j < nTheta; j++) {
      const theta = (j / (nTheta - 1)) * 2 * Math.PI;
      const value = Number(grid[i][j]) || 0;
      const t = clamp((value - cMin) / range, 0, 1);
      const radius = value;

      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);
      positions.push(x, y, z);

      const tBoost = clamp((t - 0.5) * 1.45 + 0.5, 0, 1);
      // high-contrast blue -> red
      colors.push(0.08 + tBoost * 0.92, 0.12 + (1 - tBoost) * 0.2, 1 - tBoost * 0.92);
    }
  }

  for (let i = 0; i < nPhi - 1; i++) {
    for (let j = 0; j < nTheta - 1; j++) {
      const a = i * nTheta + j;
      const b = i * nTheta + j + 1;
      const c = (i + 1) * nTheta + j;
      const d = (i + 1) * nTheta + j + 1;
      indices.push(a, c, b, b, c, d);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  const material = new THREE.MeshPhongMaterial({ vertexColors: true, shininess: 60, flatShading: false });
  return { mesh: new THREE.Mesh(geometry, material), min: cMin, max: cMax };
}

export function DigitalTwinPage() {
  const auth = getAuthState();
  const [temperature, setTemperature] = useState(300);
  const [pressure, setPressure] = useState(0);
  const [username, setUsername] = useState(auth.username || 'admin');
  const [selectedTwinFile, setSelectedTwinFile] = useState('');
  const [activeTwinFileId, setActiveTwinFileId] = useState('');
  const [compIndex, setCompIndex] = useState(0);
  const [configSwitching, setConfigSwitching] = useState(false);
  const [files, setFiles] = useState<TwinSavedFile[]>([]);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState('');
  const [status, setStatus] = useState('');
  const [metricsHtml, setMetricsHtml] = useState('加载中…');
  const [isComputing, setIsComputing] = useState(false);
  const [computeStage, setComputeStage] = useState<'idle' | 'metrics' | 'surface'>('idle');
  const [surfaceData, setSurfaceData] = useState<any>(null);
  const [surfaceLoading, setSurfaceLoading] = useState(false);
  const [twinCaps, setTwinCaps] = useState<TwinCaps | null>(null);

  const [windows, setWindows] = useState<VizWindow[]>(DEFAULT_WINDOWS);
  const [windowColor, setWindowColor] = useState<Record<string, WindowColorConfig>>(DEFAULT_COLOR_CONFIG);
  const [windowRange, setWindowRange] = useState<Record<string, { min: number; max: number }>>({});
  const [showDirections, setShowDirections] = useState<Record<string, boolean>>({
    'win-E': false,
    'win-nu': false,
    'win-vl': false,
  });

  const [scanMode, setScanMode] = useState<ScanMode>('off');
  const [scanInterval, setScanInterval] = useState(0.55);
  const [scanStepT, setScanStepT] = useState(40);
  const [scanStepP, setScanStepP] = useState(1);
  const [scanStepComp, setScanStepComp] = useState(1);
  const [scanPingPong, setScanPingPong] = useState(true);
  const [scanSpin, setScanSpin] = useState(true);
  const [scanHighRes, setScanHighRes] = useState(false);
  const [scanRunning, setScanRunning] = useState(false);

  const apiUsername = useMemo(() => {
    const fromAuth = (auth.username || '').trim();
    if (fromAuth) return fromAuth;
    return (username || '').trim();
  }, [auth.username, username]);

  const tDetected = twinCaps ? twinCaps.T?.detected !== false : true;
  const pDetected = twinCaps ? twinCaps.P?.detected !== false : true;
  const tMin = Number.isFinite(Number(twinCaps?.T?.min)) ? Number(twinCaps?.T?.min) : 273;
  const tMax = Number.isFinite(Number(twinCaps?.T?.max)) ? Number(twinCaps?.T?.max) : 1200;
  const pMin = Number.isFinite(Number(twinCaps?.P?.min)) ? Number(twinCaps?.P?.min) : 0;
  const pMax = Number.isFinite(Number(twinCaps?.P?.max)) ? Number(twinCaps?.P?.max) : 20;
  const compDetected = !!(twinCaps?.composition?.detected && (twinCaps?.composition?.n ?? 0) > 0);
  const compMax = Math.max(0, (twinCaps?.composition?.n ?? 1) - 1);
  const windowVisibilityKey = useMemo(
    () => windows.map((w) => `${w.id}:${w.closed ? 1 : 0}:${w.minimized ? 1 : 0}`).join('|'),
    [windows],
  );

  const canvasRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const desktopRef = useRef<HTMLDivElement | null>(null);
  const renderCtxRef = useRef<Record<string, WindowRenderContext | null>>({});
  const nextZRef = useRef(10);
  const surfaceRequestSeqRef = useRef(0);
  const autoRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scanTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scanBusyRef = useRef(false);
  const scanDirectionRef = useRef(1);
  const scanSpinRef = useRef(scanSpin);
  const scanRunningRef = useRef(scanRunning);
  const scanIntervalRef = useRef(scanInterval);
  const scanStepTRef = useRef(scanStepT);
  const scanStepPRef = useRef(scanStepP);
  const scanStepCompRef = useRef(scanStepComp);
  const scanPingPongRef = useRef(scanPingPong);
  const scanModeRef = useRef(scanMode);
  const scanAccumRangeRef = useRef<Record<string, { min: number; max: number }>>({});
  const metricsPrevRef = useRef<TwinProps | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const savedFileSelectRef = useRef<HTMLSelectElement | null>(null);

  const compLabels = useMemo(() => twinCaps?.composition?.labels ?? [], [twinCaps]);

  useEffect(() => {
    scanSpinRef.current = scanSpin;
  }, [scanSpin]);

  useEffect(() => {
    scanRunningRef.current = scanRunning;
  }, [scanRunning]);

  useEffect(() => {
    scanIntervalRef.current = scanInterval;
  }, [scanInterval]);

  useEffect(() => {
    scanStepTRef.current = scanStepT;
  }, [scanStepT]);

  useEffect(() => {
    scanStepPRef.current = scanStepP;
  }, [scanStepP]);

  useEffect(() => {
    scanStepCompRef.current = scanStepComp;
  }, [scanStepComp]);

  useEffect(() => {
    scanPingPongRef.current = scanPingPong;
  }, [scanPingPong]);

  useEffect(() => {
    scanModeRef.current = scanMode;
  }, [scanMode]);

  useEffect(() => {
    if (scanMode === 'off' && scanRunningRef.current) {
      stopScanAnimation();
    }
  }, [scanMode]);

  useEffect(() => {
    clearScanAccumLegend();
  }, [activeTwinFileId, compIndex]);

  function shouldUseScanAccumLegend() {
    return scanRunningRef.current && (scanMode === 'sweep-T' || scanMode === 'sweep-P');
  }

  function clearScanAccumLegend() {
    scanAccumRangeRef.current = {};
  }

  function bringWindowToFront(id: string) {
    nextZRef.current += 1;
    const nextZ = nextZRef.current;
    setWindows((prev) => prev.map((w) => (w.id === id ? { ...w, z: nextZ } : w)));
  }

  function updateScanAccumLegend(data: any) {
    (['win-E', 'win-nu', 'win-vl'] as const).forEach((id) => {
      const kind = id === 'win-E' ? 'E' : id === 'win-nu' ? 'nu_max' : 'vl';
      const mm = getGridMinMax(data, kind);
      if (!mm) return;
      const prev = scanAccumRangeRef.current[id];
      if (!prev) {
        scanAccumRangeRef.current[id] = { min: mm.min, max: mm.max };
      } else {
        scanAccumRangeRef.current[id] = { min: Math.min(prev.min, mm.min), max: Math.max(prev.max, mm.max) };
      }
    });
  }

  function disposeWindow(id: string) {
    const ctx = renderCtxRef.current[id];
    if (!ctx) return;
    cancelAnimationFrame(ctx.frameId);
    ctx.controls.dispose();
    ctx.renderer.dispose();
    if (ctx.resizeObserver) ctx.resizeObserver.disconnect();
    const mount = canvasRefs.current[id];
    if (mount) mount.innerHTML = '';
    renderCtxRef.current[id] = null;
  }

  function disposeAllWindows() {
    Object.keys(renderCtxRef.current).forEach((id) => disposeWindow(id));
  }

  function renderWindow(win: VizWindow, dataOverride?: any, opts?: { preserveView?: boolean }) {
    const mount = canvasRefs.current[win.id];
    const data = dataOverride ?? surfaceData;
    if (!mount || win.closed || win.minimized) return;

    const prevCtx = renderCtxRef.current[win.id];
    const prevPos = opts?.preserveView && prevCtx ? prevCtx.camera.position.clone() : null;
    const prevTarget = opts?.preserveView && prevCtx ? prevCtx.controls.target.clone() : null;

    disposeWindow(win.id);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0b1220');

    const camera = new THREE.PerspectiveCamera(55, Math.max(1, mount.clientWidth) / Math.max(1, mount.clientHeight), 0.1, 1000);
    camera.position.set(2.8, 2.2, 3.6);

    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(Math.max(1, mount.clientWidth), Math.max(1, mount.clientHeight));
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.65));
    const dir = new THREE.DirectionalLight(0xffffff, 0.9);
    dir.position.set(6, 12, 8);
    scene.add(dir);

    const conf = windowColor[win.id] ?? { auto: true, min: '', max: '' };
    const colorOverride = conf.auto && shouldUseScanAccumLegend() ? scanAccumRangeRef.current[win.id] ?? null : null;
    const { mesh, min, max } = createSurfaceMesh(data, win.kind, conf, colorOverride);
    let baseRadius = 1;
    if (mesh) {
      mesh.geometry.computeBoundingSphere();
      baseRadius = Math.max(1e-3, mesh.geometry.boundingSphere?.radius ?? 1);
      scene.add(mesh);
      setWindowRange((prev) => ({ ...prev, [win.id]: { min, max } }));
    } else {
      setWindowRange((prev) => ({ ...prev, [win.id]: { min: 0, max: 0 } }));
    }
    if (showDirections[win.id]) {
      const frameRadius = Math.max(1e-3, baseRadius);
      scene.add(new THREE.AxesHelper(frameRadius * 1.35));
      const frame = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(frameRadius * 2, frameRadius * 2, frameRadius * 2)),
        new THREE.LineBasicMaterial({ color: 0x7aa2ff }),
      );
      scene.add(frame);
    }

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = false;
    controls.autoRotateSpeed = 1.2;
    camera.near = Math.max(0.001, baseRadius / 200);
    camera.far = Math.max(1000, baseRadius * 120);
    camera.updateProjectionMatrix();
    if (!opts?.preserveView) {
      controls.target.set(0, 0, 0);
      camera.position.set(baseRadius * 2.2, baseRadius * 1.6, baseRadius * 2.2);
      controls.update();
    }
    if (prevPos && prevTarget) {
      camera.position.copy(prevPos);
      controls.target.copy(prevTarget);
      controls.update();
    }

    const animate = () => {
      controls.autoRotate = scanRunningRef.current && scanSpinRef.current;
      controls.update();
      renderer.render(scene, camera);
      const frameId = requestAnimationFrame(animate);
      const ctx = renderCtxRef.current[win.id];
      if (ctx) ctx.frameId = frameId;
    };
    const firstFrame = requestAnimationFrame(animate);

    const resizeObserver = new ResizeObserver(() => {
      const w = Math.max(1, mount.clientWidth);
      const h = Math.max(1, mount.clientHeight);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    resizeObserver.observe(mount);

    renderCtxRef.current[win.id] = {
      scene,
      camera,
      renderer,
      controls,
      frameId: firstFrame,
      resizeObserver,
      baseRadius,
    };
  }

  function rerenderVisibleWindows(dataOverride?: any, opts?: { preserveView?: boolean }) {
    windows.forEach((win) => {
      if (!win.closed && !win.minimized) {
        renderWindow(win, dataOverride, opts);
      }
    });
  }

  async function fetchSurface(params?: { t?: number; p?: number; fileId?: string; compIndex?: number; silent?: boolean; cacheBust?: number }) {
    const t = params?.t ?? temperature;
    const p = params?.p ?? pressure;
    const fileId = params?.fileId ?? activeTwinFileId;
    const compI = Math.max(0, Math.floor(params?.compIndex ?? compIndex));
    const requestSeq = ++surfaceRequestSeqRef.current;
    try {
      setSurfaceLoading(true);
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 60000);
      const useFastGrid = scanRunningRef.current && !scanHighRes;
      const grid = useFastGrid ? { n_phi: 22, n_theta: 32, n_chi: 22 } : { n_phi: 48, n_theta: 72, n_chi: 48 };
      const query = new URLSearchParams({
        T: String(t),
        P: String(p),
        username: apiUsername,
        twin_file: fileId || '',
        comp_index: String(compI),
        n_phi: String(grid.n_phi),
        n_theta: String(grid.n_theta),
        n_chi: String(grid.n_chi),
        high_res: useFastGrid ? '0' : '1',
        _ts: String(params?.cacheBust ?? Date.now()),
      }).toString();
      const response = await fetch(`${import.meta.env.VITE_PYTHON_API_ORIGIN || ''}/api/digital_twin/anisotropy_surface?${query}`, {
        method: 'GET',
        signal: controller.signal,
      });
      window.clearTimeout(timeoutId);
      if (!response.ok) throw new Error('获取曲面数据失败');
      const json = await response.json();
      if (!params?.silent) {
        if (requestSeq === surfaceRequestSeqRef.current) {
          setSurfaceData(json);
        }
      }
      if (!params?.silent) setStatus('已加载各向异性曲面数据');
      return json;
    } catch (error) {
      if (!params?.silent) {
        if (requestSeq === surfaceRequestSeqRef.current) {
          setSurfaceData(null);
        }
      }
      const msg = error instanceof DOMException && error.name === 'AbortError' ? '请求超时（60s）' : (error as Error).message;
      setStatus(`曲面加载失败: ${msg}`);
      return null;
    } finally {
      setSurfaceLoading(false);
    }
  }

  function formatDelta(prev?: number, cur?: number, digits = 2) {
    const p = Number(prev);
    const c = Number(cur);
    if (!Number.isFinite(p) || !Number.isFinite(c)) return '';
    const d = c - p;
    if (Math.abs(d) < 1e-8) return ' <span style="color:#9aa0a6">(→)</span>';
    const color = d > 0 ? '#81c995' : '#f28b82';
    const sign = d > 0 ? '+' : '';
    return ` <span style="color:${color};font-weight:600">${sign}${d.toFixed(digits)}</span>`;
  }

  function setMetricsFromProps(props: TwinProps, showDelta = false) {
    const prev = metricsPrevRef.current;
    const html = `
      <div><strong>B</strong> ${Number(props.bulk_modulus_GPa ?? NaN).toFixed(3)} GPa${showDelta && prev ? formatDelta(prev.bulk_modulus_GPa, props.bulk_modulus_GPa, 3) : ''}</div>
      <div><strong>G</strong> ${Number(props.shear_modulus_GPa ?? NaN).toFixed(3)} GPa${showDelta && prev ? formatDelta(prev.shear_modulus_GPa, props.shear_modulus_GPa, 3) : ''}</div>
      <div><strong>E</strong> ${Number(props.young_modulus_GPa ?? NaN).toFixed(3)} GPa${showDelta && prev ? formatDelta(prev.young_modulus_GPa, props.young_modulus_GPa, 3) : ''}</div>
      <div><strong>V/V0</strong> ${Number(props.volume_scale ?? NaN).toFixed(5)}${showDelta && prev ? formatDelta(prev.volume_scale, props.volume_scale, 5) : ''}</div>
      <div><strong>model</strong> <code>${String(props.model ?? '')}</code></div>
    `;
    setMetricsHtml(html);
    metricsPrevRef.current = props;
  }

  async function fetchTwinProperties(opts?: { showDelta?: boolean; fileId?: string; compIndex?: number; cacheBust?: number }) {
    try {
      setComputeStage('metrics');
      const query = new URLSearchParams({
        T: String(temperature),
        P: String(pressure),
        username: apiUsername,
        twin_file: (opts?.fileId ?? activeTwinFileId) || '',
        comp_index: String(Math.max(0, Math.floor(opts?.compIndex ?? compIndex))),
        _ts: String(opts?.cacheBust ?? Date.now()),
      }).toString();
      const response = await pythonApi.twinProperties(query);
      setMetricsFromProps(response as TwinProps, opts?.showDelta === true);
    } catch (error) {
      setMetricsHtml(`<span style="color:#f28b82">标量 API：${(error as Error).message}</span>`);
    } finally {
      setComputeStage('idle');
    }
  }

  async function probeTwinProperties() {
    try {
      await fetchTwinProperties();
      const latest = await fetchSurface();
      if (latest) rerenderVisibleWindows(latest);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function loadCapabilities(fileId?: string) {
    try {
      const query = new URLSearchParams({ username: apiUsername, twin_file: fileId ?? activeTwinFileId }).toString();
      const response = await pythonApi.twinCapabilities(query);
      const caps = response as TwinCaps;
      setTwinCaps(caps);
      if (caps.composition?.detected && (caps.composition.n ?? 0) > 0) {
        const maxComp = Math.max(0, (caps.composition.n ?? 1) - 1);
        setCompIndex((prev) => clamp(prev, 0, maxComp));
      } else {
        setCompIndex(0);
      }
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function loadFiles() {
    try {
      const response = await pythonApi.twinListDat(apiUsername);
      const rows = (response.files ?? []).map((item) => {
        const id = String(item.id ?? '');
        const filename = String(item.filename ?? item.original_name ?? item.id ?? '');
        return {
          id,
          filename,
          originalName: String(item.original_name ?? ''),
          kind: String(item.kind ?? ''),
        };
      });
      setFiles(rows);
      setStatus(`已加载 ${rows.length} 个文件`);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function activateAndRefresh(fileId: string) {
    try {
      stopScanAnimation();
      setConfigSwitching(true);
      surfaceRequestSeqRef.current += 1;
      setStatus(`正在切换配置并加载曲面: ${fileId || '默认 HTEM'} ...`);
      setSurfaceData(null);
      const response = await pythonApi.twinActivateDat({
        username: apiUsername,
        twin_file: fileId || undefined,
      });
      if (!response.success) {
        setStatus(`配置激活失败: ${response.message || '未知错误'}`);
        return;
      }
      setActiveTwinFileId(fileId || '');
      setSelectedTwinFile(fileId || '');
      setCompIndex(0);
      await loadCapabilities(fileId || '');
      setStatus(`配置已激活: ${response.twin_file || '默认 HTEM'}`);
      const ts = Date.now();
      await fetchTwinProperties({ fileId, compIndex: 0, cacheBust: ts });
      const latest = await fetchSurface({ fileId, compIndex: 0, cacheBust: ts });
      if (latest) {
        rerenderVisibleWindows(latest);
      } else {
        setStatus(`配置已激活，但曲面加载失败: ${fileId || '默认 HTEM'}`);
      }
    } catch (error) {
      setStatus(`配置激活失败: ${(error as Error).message}`);
    } finally {
      setConfigSwitching(false);
    }
  }

  async function resetToDefaultAndRefresh() {
    try {
      stopScanAnimation();
      setConfigSwitching(true);
      surfaceRequestSeqRef.current += 1;
      setStatus('正在恢复默认 HTEM 并加载曲面...');
      setSurfaceData(null);
      const response = await pythonApi.twinActivateDat({
        username: apiUsername,
        twin_file: undefined,
      });
      if (!response.success) {
        setStatus(`恢复默认失败: ${response.message || '未知错误'}`);
        return;
      }
      setSelectedTwinFile('');
      setActiveTwinFileId('');
      setCompIndex(0);
      await loadCapabilities('');
      setStatus('已恢复默认 HTEM（服务器配置）');
      const ts = Date.now();
      await fetchTwinProperties({ fileId: '', compIndex: 0, cacheBust: ts });
      const latest = await fetchSurface({ fileId: '', compIndex: 0, cacheBust: ts });
      if (latest) {
        rerenderVisibleWindows(latest);
      }
    } catch (error) {
      setStatus(`恢复默认失败: ${(error as Error).message}`);
    } finally {
      setConfigSwitching(false);
    }
  }

  async function handleUploadDat() {
    if (!uploadFile) {
      setUploadStatus('请选择 .dat 文件');
      return;
    }
    try {
      setUploadStatus('上传中...');
      const bytes = new Uint8Array(await uploadFile.arrayBuffer());
      let binary = '';
      bytes.forEach((b) => {
        binary += String.fromCharCode(b);
      });
      const response = await pythonApi.twinUploadDat({
        username: apiUsername,
        filename: uploadFile.name,
        content_base64: btoa(binary),
      });
      setUploadStatus(response.success ? '上传成功，请刷新文件列表' : response.message || '上传失败');
      if (response.success) await loadFiles();
    } catch (error) {
      setUploadStatus(`上传失败: ${(error as Error).message}`);
    }
  }

  async function handleUploadAndActivate(file: File) {
    if (!apiUsername) {
      setStatus('请先登录后上传 .dat 文件');
      return;
    }
    setUploadFile(file);
    setUploadStatus(`上传中: ${file.name}`);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      bytes.forEach((b) => {
        binary += String.fromCharCode(b);
      });
      const response = await pythonApi.twinUploadDat({
        username: apiUsername,
        filename: file.name,
        content_base64: btoa(binary),
      });
      if (!response.success || !response.id) {
        setUploadStatus(response.message || '上传失败');
        return;
      }
      setUploadStatus(`已上传并激活: ${file.name}`);
      await loadFiles();
      await activateAndRefresh(String(response.id));
    } catch (error) {
      setUploadStatus(`上传失败: ${(error as Error).message}`);
    }
  }

  function updateWindowColor(id: string, patch: Partial<WindowColorConfig>) {
    setWindowColor((prev) => ({ ...prev, [id]: { ...(prev[id] ?? { auto: true, min: '', max: '' }), ...patch } }));
  }

  function exportWindowPNG(id: string) {
    const ctx = renderCtxRef.current[id];
    if (!ctx) {
      setStatus('窗口尚未渲染，无法导出');
      return;
    }
    const link = document.createElement('a');
    link.download = `${id}.png`;
    link.href = ctx.renderer.domElement.toDataURL('image/png');
    link.click();
  }

  function exportAllVisibleWindows() {
    windows.filter((w) => !w.closed && !w.minimized).forEach((w) => exportWindowPNG(w.id));
  }

  function resetVisibleViews() {
    windows.forEach((w) => {
      if (w.closed || w.minimized) return;
      const ctx = renderCtxRef.current[w.id];
      if (!ctx) return;
      const r = Math.max(1e-3, ctx.baseRadius || 1);
      ctx.controls.target.set(0, 0, 0);
      ctx.camera.near = Math.max(0.001, r / 200);
      ctx.camera.far = Math.max(1000, r * 120);
      ctx.camera.updateProjectionMatrix();
      ctx.camera.position.set(r * 2.2, r * 1.6, r * 2.2);
      ctx.controls.target.set(0, 0, 0);
      ctx.controls.update();
    });
    setStatus('已重置可见窗口视角');
  }

  function stopScanAnimation() {
    if (scanTimerRef.current) {
      clearTimeout(scanTimerRef.current);
      scanTimerRef.current = null;
    }
    scanBusyRef.current = false;
    scanRunningRef.current = false;
    setScanRunning(false);
    clearScanAccumLegend();
    metricsPrevRef.current = null;
  }

  async function startScanAnimation() {
    if (scanMode === 'off') {
      setStatus('请先选择扫描模式');
      return;
    }
    stopScanAnimation();
    scanRunningRef.current = true;
    setScanRunning(true);

    let currentT = temperature;
    let currentP = pressure;
    let currentComp = Math.floor(compIndex);
    scanDirectionRef.current = 1;
    const boundTMin = tMin;
    const boundTMax = tMax;
    const boundPMin = pMin;
    const boundPMax = pMax;
    scanBusyRef.current = false;
    clearScanAccumLegend();

    if (scanMode === 'sweep-T') {
      currentP = pressure;
      currentT = boundTMin;
      setTemperature(Math.round(currentT));
      setPressure(Math.round(currentP * 10) / 10);
    } else if (scanMode === 'sweep-P') {
      currentT = temperature;
      currentP = boundPMin;
      setTemperature(Math.round(currentT));
      setPressure(Math.round(currentP * 10) / 10);
    } else if (scanMode === 'sweep-comp') {
      currentT = temperature;
      currentP = pressure;
      currentComp = 0;
      setTemperature(Math.round(currentT));
      setPressure(Math.round(currentP * 10) / 10);
      setCompIndex(0);
    }

    const stepOnce = async () => {
      if (!scanRunningRef.current) return;
      const mode = scanModeRef.current;
      const stepT = scanStepTRef.current;
      const stepP = scanStepPRef.current;
      const stepComp = scanStepCompRef.current;
      const pingPong = scanPingPongRef.current;
      if (scanBusyRef.current) {
        scanTimerRef.current = setTimeout(() => { void stepOnce(); }, 80);
        return;
      }
      scanBusyRef.current = true;
      let nextT = currentT;
      let nextP = currentP;
      let nextComp = currentComp;

      if (mode === 'sweep-T') {
        nextT += stepT * scanDirectionRef.current;
        if (nextT > boundTMax || nextT < boundTMin) {
          if (pingPong) {
            scanDirectionRef.current *= -1;
            nextT = clamp(nextT, boundTMin, boundTMax);
          } else {
            nextT = boundTMin;
          }
        }
      } else if (mode === 'sweep-P') {
        nextP += stepP * scanDirectionRef.current;
        if (nextP > boundPMax || nextP < boundPMin) {
          if (pingPong) {
            scanDirectionRef.current *= -1;
            nextP = clamp(nextP, boundPMin, boundPMax);
          } else {
            nextP = boundPMin;
          }
        }
      } else if (mode === 'sweep-comp') {
        const maxComp = Math.max(0, (twinCaps?.composition?.n ?? 1) - 1);
        if (maxComp <= 0) {
          scanBusyRef.current = false;
          return;
        }
        nextComp += stepComp * scanDirectionRef.current;
        if (nextComp > maxComp || nextComp < 0) {
          if (pingPong) {
            scanDirectionRef.current *= -1;
            nextComp = clamp(nextComp, 0, maxComp);
          } else {
            nextComp = 0;
          }
        }
      }

      const nextFileId = activeTwinFileId;
      try {
        await fetchTwinProperties({ showDelta: true });
        const latest = await fetchSurface({ t: nextT, p: nextP, fileId: nextFileId, compIndex: Math.floor(nextComp), silent: true });
        if (latest) {
          if (mode === 'sweep-T' || mode === 'sweep-P') {
            updateScanAccumLegend(latest);
          }
          currentT = nextT;
          currentP = nextP;
          currentComp = nextComp;
          setTemperature(Math.round(nextT));
          setPressure(Math.round(nextP * 10) / 10);
          if (mode === 'sweep-comp') {
            setCompIndex(Math.floor(nextComp));
          }
          rerenderVisibleWindows(latest, { preserveView: true });
        }
      } finally {
        scanBusyRef.current = false;
      }

      if (!scanRunningRef.current) return;
      const waitMs = Math.max(150, Math.round(Math.max(0.15, scanIntervalRef.current) * 1000));
      scanTimerRef.current = setTimeout(() => { void stepOnce(); }, waitMs);
    };

    scanTimerRef.current = setTimeout(() => { void stepOnce(); }, 0);
  }

  useEffect(() => {
    void loadFiles();
  }, []);

  useEffect(() => {
    if (scanRunningRef.current) return;
    if (configSwitching) return;
    if (autoRefreshTimerRef.current) {
      clearTimeout(autoRefreshTimerRef.current);
      autoRefreshTimerRef.current = null;
    }
    autoRefreshTimerRef.current = setTimeout(() => {
      void (async () => {
        setIsComputing(true);
        setStatus('正在计算显示参数…');
        await fetchTwinProperties();
        setComputeStage('surface');
        setStatus('正在计算并更新曲面图像…');
        const latest = await fetchSurface();
        if (latest) rerenderVisibleWindows(latest, { preserveView: true });
        setComputeStage('idle');
        setIsComputing(false);
        setStatus('参数与曲面已同步更新');
      })();
    }, 280);
    return () => {
      if (autoRefreshTimerRef.current) {
        clearTimeout(autoRefreshTimerRef.current);
        autoRefreshTimerRef.current = null;
      }
    };
  }, [temperature, pressure, compIndex, activeTwinFileId, scanHighRes, configSwitching]);

  useEffect(() => {
    if (auth.username && auth.username !== username) {
      setUsername(auth.username);
    }
  }, [auth.username]);

  useEffect(() => {
    windows.forEach((win) => {
      if (win.closed || win.minimized) {
        disposeWindow(win.id);
      }
    });
    rerenderVisibleWindows();
  }, [surfaceData, windowVisibilityKey, windowColor, showDirections, scanSpin]);

  useEffect(() => {
    const boot = async () => {
      // 首次进入强制恢复为默认 HTEM，会话不受之前上传文件激活影响
      await resetToDefaultAndRefresh();
      await loadCapabilities();
    };
    void boot();
  }, []);

  useEffect(() => {
    return () => {
      stopScanAnimation();
      disposeAllWindows();
      if (autoRefreshTimerRef.current) {
        clearTimeout(autoRefreshTimerRef.current);
        autoRefreshTimerRef.current = null;
      }
    };
  }, []);

  return (
    <section className="dt-page">
      <div className="dt-inner">
        <h2 className="dt-title">弹性各向异性数字孪生（HTEM SAM）</h2>
        <p className="dt-sub">
          支持<strong>默认 HTEM 单材料</strong>（T、P）与<strong>上传表</strong>（名义成分 + c_ij）。
          对齐原网页交互：拖拽缩放窗口、扫描动效、色标控制、窗口坞恢复与 PNG 导出。
        </p>

        <div className="dt-layout">
          <aside className="dt-panel">
            <p className="panel-back">
              <a href="/">← 返回首页</a>
              <span style={{ color: '#5f6368' }}> · </span>
              <a href="/visualization">可视化网页</a>
            </p>
            <h3>交互参数（工况输入）</h3>
            {isComputing || surfaceLoading || configSwitching ? (
              <div className="dt-compute-banner" role="status" aria-live="polite">
                <span className="dt-spinner" />
                <span>
                  {configSwitching
                    ? '正在切换数据配置…'
                    : computeStage === 'metrics'
                      ? '正在计算显示参数…'
                      : computeStage === 'surface' || surfaceLoading
                        ? '正在计算并更新曲面图像…'
                        : '正在处理…'}
                </span>
              </div>
            ) : null}
            <p className="status">
              右侧窗口支持拖动标题栏、右下角缩放、最小化、关闭；已关闭窗口可在窗口坞中恢复。
            </p>
            <label className={`field dt-dim-row ${tDetected ? '' : 'dt-dim-disabled'}`}>
              温度 T（K） <span className="value">{Math.round(temperature)}</span>
              {!tDetected ? <span className="dt-dim-na">未检测到 T</span> : null}
              <div className="dt-range-row">
                <input
                  type="range"
                  min={tMin}
                  max={tMax}
                  step={1}
                  value={temperature}
                  disabled={!tDetected}
                  onChange={(e) => {
                    stopScanAnimation();
                    setTemperature(Number(e.target.value));
                  }}
                />
                <input
                  type="number"
                  value={temperature}
                  min={tMin}
                  max={tMax}
                  disabled={!tDetected}
                  onChange={(e) => {
                    stopScanAnimation();
                    setTemperature(Number(e.target.value));
                  }}
                />
              </div>
            </label>
            <label className={`field dt-dim-row ${pDetected ? '' : 'dt-dim-disabled'}`}>
              压强 P（GPa） <span className="value">{Number(pressure.toFixed(2))}</span>
              {!pDetected ? <span className="dt-dim-na">未检测到 P</span> : null}
              <div className="dt-range-row">
                <input
                  type="range"
                  min={pMin}
                  max={pMax}
                  step={0.1}
                  value={pressure}
                  disabled={!pDetected}
                  onChange={(e) => {
                    stopScanAnimation();
                    setPressure(Number(e.target.value));
                  }}
                />
                <input
                  type="number"
                  value={pressure}
                  min={pMin}
                  max={pMax}
                  step={0.1}
                  disabled={!pDetected}
                  onChange={(e) => {
                    stopScanAnimation();
                    setPressure(Number(e.target.value));
                  }}
                />
              </div>
            </label>
            <label className={`field dt-dim-row ${compDetected ? '' : 'dt-dim-disabled'}`}>
              成分（行索引） <span className="value">{compIndex}</span>
              {compLabels[compIndex] ? <span className="value"> · {compLabels[compIndex]}</span> : null}
              {!compDetected ? <span className="dt-dim-na">未检测到成分</span> : null}
              <div className="dt-range-row">
                <input
                  type="range"
                  min={0}
                  max={compMax}
                  step={1}
                  value={compIndex}
                  disabled={!compDetected}
                  onChange={(e) => {
                    stopScanAnimation();
                    setCompIndex(Math.max(0, Math.floor(Number(e.target.value) || 0)));
                  }}
                />
                <input
                  type="number"
                  value={compIndex}
                  min={0}
                  max={compMax}
                  disabled={!compDetected}
                  onChange={(e) => {
                    stopScanAnimation();
                    setCompIndex(Math.max(0, Math.floor(Number(e.target.value) || 0)));
                  }}
                />
              </div>
            </label>
            <div className="row">
              <button className="btn" onClick={probeTwinProperties}>手动刷新（标量+曲面）</button>
            </div>
            {twinCaps?.note ? <p className="status">{twinCaps.note}</p> : null}

            <div className="dt-file-panel">
              <h3>输入数据（.dat）</h3>
              <p className="status" style={{ marginTop: 0 }}>
                登录后可拖入 .dat 或选择已保存文件。成分表激活离散成分轴；HTEM 温压表激活后会切换 SAM 输入。
              </p>
              <div
                className="dt-drop-zone"
                tabIndex={0}
                role="button"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const first = e.dataTransfer.files?.[0];
                  if (first) {
                    void handleUploadAndActivate(first);
                  }
                }}
              >
                拖放 .dat 到此处，或点击选择文件
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".dat,.txt"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleUploadAndActivate(file);
                  e.currentTarget.value = '';
                }}
              />
              <label className="field">
                用户名
                <input value={apiUsername} onChange={(e) => setUsername(e.target.value)} disabled={Boolean(auth.username)} />
              </label>
              <label className="field">
                已保存文件
                <select
                  ref={savedFileSelectRef}
                  value={selectedTwinFile}
                  onChange={(e) => {
                    const fileId = e.target.value;
                    setSelectedTwinFile(fileId);
                  }}
                  disabled={configSwitching}
                >
                  <option value="">— 默认 HTEM（服务器配置）—</option>
                  {files.map((item) => (
                    <option key={item.id || item.filename} value={item.id}>
                      {item.originalName || item.filename}{item.kind ? ` · ${item.kind}` : ''}
                    </option>
                  ))}
                </select>
              </label>
              <div className="row">
                <button className="btn secondary" onClick={loadFiles} disabled={configSwitching}>
                  刷新文件列表
                </button>
                <button
                  className="btn secondary"
                  onClick={() => {
                    const fileId = savedFileSelectRef.current?.value ?? selectedTwinFile;
                    void activateAndRefresh(fileId);
                  }}
                  disabled={configSwitching}
                >
                  使用所选文件
                </button>
                <button className="btn secondary" onClick={resetToDefaultAndRefresh} disabled={configSwitching}>恢复默认</button>
              </div>
              <p className="status">当前生效配置：{activeTwinFileId || '默认 HTEM（服务器配置）'}{configSwitching ? '（加载中）' : ''}</p>
              <div className="row">
                <input type="file" accept=".dat,.txt" onChange={(e) => setUploadFile(e.target.files?.[0] || null)} />
                <button className="btn" onClick={handleUploadDat} disabled={!uploadFile}>上传</button>
              </div>
              <p className="status">{uploadStatus}</p>
            </div>

            <div className="dt-scan">
              <h3>参数扫描动效（T / P / 成分）</h3>
              <p className="status" style={{ marginTop: 0 }}>
                仅当当前数据检测到对应维度变化时才可扫描。手动拖动滑块会停止扫描。
              </p>
              <label className="field">
                模式
                <select value={scanMode} onChange={(e) => setScanMode(e.target.value as ScanMode)}>
                  <option value="off">关闭</option>
                  <option value="sweep-T" disabled={twinCaps ? twinCaps.T?.detected === false : false}>扫描 T</option>
                  <option value="sweep-P" disabled={twinCaps ? twinCaps.P?.detected === false : false}>扫描 P</option>
                  <option
                    value="sweep-comp"
                    disabled={!(
                      twinCaps?.composition?.detected &&
                      (twinCaps?.composition?.n ?? 0) > 1
                    )}
                  >
                    扫描成分
                  </option>
                </select>
              </label>
              <div className="dt-scan-grid">
                <label className="field"><span>步进间隔（秒）</span><input type="number" min={0.15} step={0.05} value={scanInterval} onChange={(e) => setScanInterval(Number(e.target.value))} /></label>
                <label className="field"><span>T 步长</span><input type="number" value={scanStepT} onChange={(e) => setScanStepT(Number(e.target.value))} /></label>
                <label className="field"><span>P 步长</span><input type="number" value={scanStepP} onChange={(e) => setScanStepP(Number(e.target.value))} /></label>
                <label className="field"><span>成分步长</span><input type="number" value={scanStepComp} onChange={(e) => setScanStepComp(Number(e.target.value))} /></label>
              </div>
              <label className="dt-check"><input type="checkbox" checked={scanPingPong} onChange={(e) => setScanPingPong(e.target.checked)} />到端点后往返</label>
              <label className="dt-check"><input type="checkbox" checked={scanSpin} onChange={(e) => setScanSpin(e.target.checked)} />扫描时曲面自转</label>
              <label className="dt-check"><input type="checkbox" checked={scanHighRes} onChange={(e) => setScanHighRes(e.target.checked)} />高分辨率采样</label>
              <button
                className={`btn ${scanRunning ? 'danger' : ''}`}
                onClick={() => {
                  if (scanRunning) {
                    stopScanAnimation();
                    setStatus('已停止参数扫描');
                    return;
                  }
                  void startScanAnimation();
                }}
                disabled={!scanRunning && scanMode === 'off'}
              >
                {scanRunning ? '停止扫描' : '开始扫描'}
              </button>
            </div>

            <div className="metrics" dangerouslySetInnerHTML={{ __html: metricsHtml }} />
            <div id="status-bar">{status}</div>

            <div className="row">
              <button className="btn secondary" onClick={exportAllVisibleWindows}>导出全部曲面</button>
              <button className="btn secondary" onClick={resetVisibleViews}>重置视图</button>
            </div>
            <div className="dt-dock">
              <h4>已关闭窗口</h4>
              <div className="dt-dock-list">
                {windows.filter((w) => w.closed).length === 0 ? (
                  <span className="status">暂无</span>
                ) : (
                  windows
                    .filter((w) => w.closed)
                    .map((w) => (
                      <button
                        key={w.id}
                        className="dock-chip"
                        onClick={() => {
                          nextZRef.current += 1;
                          const nextZ = nextZRef.current;
                          setWindows((prev) => prev.map((x) => (x.id === w.id ? { ...x, closed: false, minimized: false, z: nextZ } : x)));
                        }}
                      >
                        ↩ {w.title}
                      </button>
                    ))
                )}
              </div>
            </div>
            <div className="dt-dock">
              <h4>已最小化窗口</h4>
              <div className="dt-dock-list">
                {windows.filter((w) => w.minimized && !w.closed).length === 0 ? (
                  <span className="status">暂无</span>
                ) : (
                  windows
                    .filter((w) => w.minimized && !w.closed)
                    .map((w) => (
                      <button
                        key={w.id}
                        className="dock-chip"
                        onClick={() => {
                          nextZRef.current += 1;
                          const nextZ = nextZRef.current;
                          setWindows((prev) => prev.map((x) => (x.id === w.id ? { ...x, minimized: false, z: nextZ } : x)));
                        }}
                      >
                        ▢ {w.title}
                      </button>
                    ))
                )}
              </div>
            </div>
          </aside>

          <div className="dt-main-viz">
            <div className="viz-desktop" ref={desktopRef}>
              {isComputing || surfaceLoading || configSwitching ? (
                <div className="dt-viz-loading-tag">
                  {configSwitching ? '配置切换中…' : '曲面刷新中…'}
                </div>
              ) : null}
              {[...windows].sort((a, b) => a.z - b.z).map((win) => {
                if (win.closed || win.minimized) return null;
                const conf = windowColor[win.id] ?? { auto: true, min: '', max: '' };
                const range = windowRange[win.id];
                return (
                  <div
                    key={win.id}
                    className="viz-window"
                    style={{ left: win.x, top: win.y, width: win.w, height: win.h, zIndex: win.z }}
                    onMouseDown={() => bringWindowToFront(win.id)}
                  >
                    <div
                      className="viz-window-head"
                      onMouseDown={(event) => {
                        bringWindowToFront(win.id);
                        const startX = event.clientX;
                        const startY = event.clientY;
                        const x0 = win.x;
                        const y0 = win.y;
                        const onMove = (moveEvent: MouseEvent) => {
                          const dx = moveEvent.clientX - startX;
                          const dy = moveEvent.clientY - startY;
                          const desktop = desktopRef.current;
                          const maxX = desktop ? Math.max(0, desktop.clientWidth - win.w) : Number.MAX_SAFE_INTEGER;
                          const maxY = desktop ? Math.max(0, desktop.clientHeight - win.h) : Number.MAX_SAFE_INTEGER;
                          const nx = clamp(x0 + dx, 0, maxX);
                          const ny = clamp(y0 + dy, 0, maxY);
                          setWindows((prev) => prev.map((w) => (w.id === win.id ? { ...w, x: nx, y: ny } : w)));
                        };
                        const onUp = () => {
                          document.removeEventListener('mousemove', onMove);
                          document.removeEventListener('mouseup', onUp);
                        };
                        document.addEventListener('mousemove', onMove);
                        document.addEventListener('mouseup', onUp);
                      }}
                    >
                      <span className="viz-window-title">{win.title}</span>
                      <div className="viz-window-actions">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setWindows((prev) => prev.map((w) => (w.id === win.id ? { ...w, minimized: true } : w)));
                          }}
                        >
                          −
                        </button>
                        <button
                          className={showDirections[win.id] ? 'viz-btn-active' : ''}
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowDirections((prev) => ({ ...prev, [win.id]: !prev[win.id] }));
                          }}
                          title="显示/隐藏晶向"
                        >
                          晶向
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            exportWindowPNG(win.id);
                          }}
                          title="导出 PNG"
                        >
                          ⤓
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setWindows((prev) => prev.map((w) => (w.id === win.id ? { ...w, closed: true } : w)));
                          }}
                        >
                          ×
                        </button>
                      </div>
                    </div>
                    <div className="viz-window-body">
                      <div className="surf-canvas-wrap" ref={(el) => { canvasRefs.current[win.id] = el; }} />
                      {!surfaceData ? (
                        <div
                          style={{
                            position: 'absolute',
                            left: 10,
                            top: 8,
                            fontSize: 12,
                            color: '#9aa0a6',
                            pointerEvents: 'none',
                          }}
                        >
                          {surfaceLoading || configSwitching ? '配置曲面加载中…' : '未获取到配置曲面数据'}
                        </div>
                      ) : null}
                      <div className="surf-color-legend">
                        <div className="legend-title">{win.kind} 色标</div>
                        <div className="legend-range">{range ? `${range.min.toFixed(3)} ~ ${range.max.toFixed(3)}` : '-'}</div>
                        <label className="dt-check"><input type="checkbox" checked={conf.auto} onChange={(e) => updateWindowColor(win.id, { auto: e.target.checked })} />自动</label>
                        <div className="row">
                          <input
                            type="number"
                            disabled={conf.auto}
                            value={conf.min}
                            placeholder="min"
                            onChange={(e) => updateWindowColor(win.id, { min: e.target.value === '' ? '' : Number(e.target.value) })}
                          />
                          <input
                            type="number"
                            disabled={conf.auto}
                            value={conf.max}
                            placeholder="max"
                            onChange={(e) => updateWindowColor(win.id, { max: e.target.value === '' ? '' : Number(e.target.value) })}
                          />
                          <button className="btn secondary" onClick={() => renderWindow(win)}>应用</button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
