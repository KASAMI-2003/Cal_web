import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Terminal } from 'xterm';
import { FitAddon } from '@xterm/addon-fit';
import 'xterm/css/xterm.css';
import { pythonApi } from '../api/pythonApi';
import { openTerminalSocket } from '../ws/terminalWs';
import { getAuthState } from '../auth/authStore';
import { PERIODIC_ELEMENTS } from '../data/periodicTable';
import type { DataInputApplication } from '../types/contracts';

const VALID_ELEMENT_SYMBOLS = new Set(PERIODIC_ELEMENTS.map((element) => element.symbol));

type TerminalState = 'idle' | 'connecting' | 'connected' | 'closed' | 'error';
type SearchKind = 'elements' | 'materials';
type VizTab = 'elements' | 'detail' | 'terminal' | 'input';
type SourceFilter = 'all' | 'local' | 'mp';

interface SearchCardItem {
  id: string;
  kind: SearchKind;
  title: string;
  subtitle?: string;
  tag: string;
  fields: Array<{ key: string; value: string }>;
}

interface InputKvRow {
  id: string;
  key: string;
  value: string;
}

interface MaterialOption {
  id: string;
  title: string;
  sourceType: 'local' | 'mp';
  tag: string;
  kind: SearchKind;
  data: Record<string, unknown>;
}

interface LatticeRenderData {
  positions: number[][];
  connections: number[][];
  elements: string[];
  latticeConst: number;
}

interface TerminalServerProfile {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  password?: string;
}

type ReachabilityStatus = 'checking' | 'online' | 'offline';

interface RemoteEntry {
  name: string;
  kind: 'd' | 'f';
  size: number;
}

interface TerminalSessionTab {
  id: string;
  serverId?: string;
  name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  output: string;
  cwd: string;
  entries: RemoteEntry[];
  selectedName: string;
  state: TerminalState;
}

interface UploadQueueItem {
  id: string;
  name: string;
  size: number;
  progress: number;
  status: 'queued' | 'uploading' | 'done' | 'failed';
  message?: string;
}

interface GridPosition {
  row: number;
  col: number;
}

type ElementCategory =
  | 'alkali'
  | 'alkaline-earth'
  | 'transition'
  | 'post-transition'
  | 'metalloid'
  | 'nonmetal'
  | 'halogen'
  | 'noble-gas'
  | 'lanthanide'
  | 'actinide'
  | 'unknown';

function getElementGridPosition(atomicNumber: number): GridPosition {
  if (atomicNumber === 1) return { row: 1, col: 1 };
  if (atomicNumber === 2) return { row: 1, col: 18 };
  if (atomicNumber >= 3 && atomicNumber <= 10) {
    const colMap = [1, 2, 13, 14, 15, 16, 17, 18];
    return { row: 2, col: colMap[atomicNumber - 3] };
  }
  if (atomicNumber >= 11 && atomicNumber <= 18) {
    const colMap = [1, 2, 13, 14, 15, 16, 17, 18];
    return { row: 3, col: colMap[atomicNumber - 11] };
  }
  if (atomicNumber >= 19 && atomicNumber <= 36) {
    return { row: 4, col: atomicNumber - 18 };
  }
  if (atomicNumber >= 37 && atomicNumber <= 54) {
    return { row: 5, col: atomicNumber - 36 };
  }
  if (atomicNumber >= 55 && atomicNumber <= 56) {
    return { row: 6, col: atomicNumber - 54 };
  }
  if (atomicNumber >= 57 && atomicNumber <= 71) {
    return { row: 8, col: atomicNumber - 53 };
  }
  if (atomicNumber >= 72 && atomicNumber <= 86) {
    return { row: 6, col: atomicNumber - 68 };
  }
  if (atomicNumber >= 87 && atomicNumber <= 88) {
    return { row: 7, col: atomicNumber - 86 };
  }
  if (atomicNumber >= 89 && atomicNumber <= 103) {
    return { row: 9, col: atomicNumber - 85 };
  }
  return { row: 7, col: atomicNumber - 100 };
}

function getElementCategory(atomicNumber: number, symbol: string): ElementCategory {
  const alkali = new Set([3, 11, 19, 37, 55, 87]);
  const alkalineEarth = new Set([4, 12, 20, 38, 56, 88]);
  const nonmetals = new Set([1, 6, 7, 8, 15, 16, 34]);
  const metalloids = new Set([5, 14, 32, 33, 51, 52, 84]);
  const halogens = new Set([9, 17, 35, 53, 85, 117]);
  const nobleGases = new Set([2, 10, 18, 36, 54, 86, 118]);
  const postTransition = new Set([13, 31, 49, 50, 81, 82, 83, 113, 114, 115, 116]);
  const unknown = new Set(['Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt', 'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc', 'Lv', 'Ts', 'Og']);
  if (atomicNumber >= 57 && atomicNumber <= 71) return 'lanthanide';
  if (atomicNumber >= 89 && atomicNumber <= 103) return 'actinide';
  if (alkali.has(atomicNumber)) return 'alkali';
  if (alkalineEarth.has(atomicNumber)) return 'alkaline-earth';
  if (halogens.has(atomicNumber)) return 'halogen';
  if (nobleGases.has(atomicNumber)) return 'noble-gas';
  if (nonmetals.has(atomicNumber)) return 'nonmetal';
  if (metalloids.has(atomicNumber)) return 'metalloid';
  if (postTransition.has(atomicNumber)) return 'post-transition';
  if (unknown.has(symbol)) return 'unknown';
  return 'transition';
}

function extractSymbolsFromFormula(formulaText: string): string[] {
  const matches = formulaText.match(/[A-Z][a-z]?/g) ?? [];
  return Array.from(new Set(matches.filter((symbol) => VALID_ELEMENT_SYMBOLS.has(symbol))));
}

function normalizeLocalMaterialId(rawId: string | number | undefined, fallback = 'item'): string {
  const text = String(rawId ?? '').trim();
  if (!text || text === 'db-meta') {
    return 'db-meta';
  }
  const core = text.replace(/^(dbm?-)/i, '');
  if (/^\d+$/.test(core)) {
    return `db-${core}`;
  }
  if (text.startsWith('db-')) {
    return text;
  }
  return `db-${core || fallback}`;
}

function formatMaterialDisplayId(option: MaterialOption): string {
  if (option.sourceType === 'mp') {
    return normalizeMpApiId(option.id);
  }
  const raw = option.data.id ?? option.id;
  return normalizeLocalMaterialId(String(raw ?? option.id));
}

function getCandidateElementSet(option: MaterialOption): Set<string> {
  const data = option.data;
  const set = new Set<string>();

  if (data.u_at_pct != null && Number(data.u_at_pct) > 0) {
    set.add('U');
  }
  if (data.nb_at_pct != null && Number(data.nb_at_pct) > 0) {
    set.add('Nb');
  }

  const formulaKeys = ['化学式', 'formula_pretty', 'db_formula', 'material_name', 'formula', '元素', 'element', '当前查询'];
  formulaKeys.forEach((key) => {
    const value = data[key];
    if (value !== null && value !== undefined) {
      extractSymbolsFromFormula(String(value)).forEach((symbol) => set.add(symbol));
    }
  });

  const elementsField = data.elements ?? data.元素;
  if (typeof elementsField === 'string' && elementsField.trim()) {
    elementsField
      .trim()
      .split(/\s+/)
      .forEach((item) => {
        const sym = item.trim();
        if (VALID_ELEMENT_SYMBOLS.has(sym)) {
          set.add(sym);
        }
      });
  } else if (Array.isArray(elementsField)) {
    elementsField.forEach((item) => {
      if (typeof item === 'string') {
        extractSymbolsFromFormula(item).forEach((symbol) => set.add(symbol));
      }
    });
  }

  if (set.size === 0) {
    extractSymbolsFromFormula(option.title).forEach((symbol) => set.add(symbol));
  }
  return set;
}

function matchesSelectedSymbols(option: MaterialOption, selectedSymbols: string[]): boolean {
  if (selectedSymbols.length === 0) {
    return true;
  }
  const selectedSet = new Set(selectedSymbols);
  const candidateSet = getCandidateElementSet(option);
  if (candidateSet.size === 0) {
    return false;
  }
  if (candidateSet.size !== selectedSet.size) {
    return false;
  }
  return Array.from(selectedSet).every((symbol) => candidateSet.has(symbol));
}

function parseFloatLike(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const matched = String(value).match(/-?\d+(\.\d+)?/);
  if (!matched) return null;
  const num = Number(matched[0]);
  return Number.isFinite(num) ? num : null;
}

function parseLatticeAxes(data: Record<string, unknown>): { a: number | null; b: number | null; c: number | null } {
  const fromA = parseFloatLike(data.晶格常数a ?? data['晶格常数a']);
  const fromB = parseFloatLike(data.晶格常数b ?? data['晶格常数b']);
  const fromC = parseFloatLike(data.晶格常数c ?? data['晶格常数c']);
  if (fromA && fromB && fromC) {
    return { a: fromA, b: fromB, c: fromC };
  }
  const raw = String(data.晶格常数 ?? data.晶格参数 ?? '').trim();
  const explicit = raw.match(/a=([\d.]+)\s*b=([\d.]+)\s*c=([\d.]+)/i);
  if (explicit) {
    return { a: Number(explicit[1]), b: Number(explicit[2]), c: Number(explicit[3]) };
  }
  const nums = raw.match(/[\d.]+/g);
  if (!nums || nums.length === 0) return { a: null, b: null, c: null };
  if (nums.length === 1) {
    const one = Number(nums[0]);
    return { a: one, b: one, c: one };
  }
  return {
    a: Number(nums[0]),
    b: Number(nums[1] ?? nums[0]),
    c: Number(nums[2] ?? nums[1] ?? nums[0]),
  };
}

function inferLatticeType(structure: string): 'fcc' | 'bcc' | 'hcp' {
  const lower = structure.toLowerCase();
  if (lower.includes('body') || lower.includes('体心')) return 'bcc';
  if (lower.includes('hex') || lower.includes('六方')) return 'hcp';
  return 'fcc';
}

function parseMpApiMaterials(lines: string[] | undefined): MaterialOption[] {
  if (!lines || lines.length === 0) return [];
  const parsed: Array<Record<string, unknown>> = [];
  let current: Record<string, unknown> | null = null;
  const positions: number[][] = [];
  const connections: number[][] = [];
  for (const raw of lines) {
    const line = String(raw ?? '').trim();
    if (!line) continue;
    if (line.startsWith('Material ID: ')) {
      if (current) {
        current.positions = positions.slice();
        current.connections = connections.slice();
        parsed.push(current);
      }
      current = {
        id: line.replace('Material ID: ', '').trim(),
        source: 'Materials Project',
        data_source: 'Materials Project',
      };
      positions.length = 0;
      connections.length = 0;
      continue;
    }
    if (!current || !line.includes(':')) continue;
    const splitAt = line.indexOf(':');
    const key = line.slice(0, splitAt).trim();
    const value = line.slice(splitAt + 1).trim();
    if (/^原子\d+$/.test(key)) {
      const m = value.match(/\[([\d.-]+),\s*([\d.-]+),\s*([\d.-]+)\]/);
      if (m) positions.push([Number(m[1]), Number(m[2]), Number(m[3])]);
      continue;
    }
    if (key === '连接') {
      const m = value.match(/\[(\d+),\s*(\d+)\]/);
      if (m) connections.push([Number(m[1]), Number(m[2])]);
      continue;
    }
    current[key] = value;
  }
  if (current) {
    current.positions = positions.slice();
    current.connections = connections.slice();
    parsed.push(current);
  }
  return parsed.map((data, idx) => {
    const row = data as Record<string, unknown>;
    const rawId = String(row.id ?? `material-${idx}`).trim();
    const canonicalId = rawId.startsWith('mp-') ? rawId : `mp-${rawId}`;
    const enriched: Record<string, unknown> = { ...row, id: canonicalId };
    const title = String(enriched.化学式 ?? enriched.formula_pretty ?? canonicalId);
    return {
      id: canonicalId,
      title,
      sourceType: 'mp' as const,
      tag: 'MP',
      kind: 'materials' as const,
      data: enriched,
    };
  });
}

/** MP 列表 id 统一为 mp-xxxx（兼容历史重复前缀 mp-mp-） */
function normalizeMpApiId(id: string): string {
  let x = id.trim();
  while (x.startsWith('mp-mp-')) {
    x = x.slice(3);
  }
  if (!x.startsWith('mp-')) {
    x = `mp-${x}`;
  }
  return x;
}

function formatMaterialElementsSummary(data: Record<string, unknown>): string {
  const elField = data.元素 ?? data.elements;
  if (typeof elField === 'string' && elField.trim()) {
    return elField
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .join(', ');
  }
  if (Array.isArray(elField)) {
    return elField.map(String).join(', ');
  }
  const formula = String(data.化学式 ?? data.formula_pretty ?? data.db_formula ?? '').trim();
  if (formula) {
    return extractSymbolsFromFormula(formula).sort().join(', ');
  }
  return '';
}

function getMaterialFormulaPretty(option: MaterialOption): string {
  const data = option.data;
  return String(data.化学式 ?? data.formula_pretty ?? data.db_formula ?? option.title ?? '').trim();
}

/** 下拉框一行展示：元素 · 化学式 · mp-id / db-id */
function buildMaterialPickerLabel(option: MaterialOption): string {
  const formula = getMaterialFormulaPretty(option);
  const elems = formatMaterialElementsSummary(option.data);
  const idPart = formatMaterialDisplayId(option);
  const elemSeg = elems ? `[${elems}] ` : '';
  const formulaSeg = formula || option.title || '—';
  return `${elemSeg}${formulaSeg} · ${idPart}`;
}

function materialMatchesPickerQuery(option: MaterialOption, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const idTokens =
    option.sourceType === 'mp'
      ? [option.id, normalizeMpApiId(option.id)]
      : [option.id, formatMaterialDisplayId(option)];
  const hay = [
    ...idTokens,
    getMaterialFormulaPretty(option),
    option.title,
    option.tag,
    formatMaterialElementsSummary(option.data),
  ]
    .join(' ')
    .toLowerCase();
  return hay.includes(q);
}

function buildSearchCardSubtitle(option: MaterialOption): string {
  const elems = formatMaterialElementsSummary(option.data);
  const formula = getMaterialFormulaPretty(option);
  const idPart = formatMaterialDisplayId(option);
  const parts: string[] = [];
  if (elems) parts.push(`元素 ${elems}`);
  if (formula) parts.push(`化学式 ${formula}`);
  parts.push(`ID ${idPart}`);
  return parts.join(' · ');
}

const TERMINAL_SERVERS_KEY = 'viz_terminal_servers_v1';
const DEFAULT_TERMINAL_SERVER: TerminalServerProfile = {
  id: 'default-local',
  name: '默认服务器',
  host: '127.0.0.1',
  port: 22,
  username: 'admin',
  password: '',
};

function readSavedTerminalServers(): TerminalServerProfile[] {
  try {
    const raw = localStorage.getItem(TERMINAL_SERVERS_KEY);
    if (!raw) return [DEFAULT_TERMINAL_SERVER];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [DEFAULT_TERMINAL_SERVER];
    const list = parsed
      .map((item) => item as Partial<TerminalServerProfile>)
      .filter((item) => item.host && item.username && Number(item.port) > 0)
      .map((item) => ({
        id: String(item.id ?? crypto.randomUUID()),
        name: String(item.name ?? `${item.username}@${item.host}`),
        host: String(item.host),
        port: Number(item.port),
        username: String(item.username),
        password: String(item.password ?? ''),
      }));
    return list.length > 0 ? list : [DEFAULT_TERMINAL_SERVER];
  } catch {
    return [DEFAULT_TERMINAL_SERVER];
  }
}

function joinPosixPath(base: string, name: string): string {
  if (!base || base === '/') {
    return `/${name}`.replace(/\/+/g, '/');
  }
  return `${base.replace(/\/+$/, '')}/${name}`.replace(/\/+/g, '/');
}

function getParentPosixPath(path: string): string {
  const normalized = path.replace(/\/+$/, '') || '/';
  if (normalized === '/') return '/';
  const idx = normalized.lastIndexOf('/');
  if (idx <= 0) return '/';
  return normalized.slice(0, idx);
}

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size < 0) return '-';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function preventBrowserStealingTerminalKeys(ev: KeyboardEvent): boolean {
  if (ev.type !== 'keydown') return true;
  const k = ev.key;
  if (k === 'Tab') {
    ev.preventDefault();
    return true;
  }
  if (k === 'Unidentified') return true;
  if (k.startsWith('Arrow') || k === 'PageUp' || k === 'PageDown' || k === 'Home' || k === 'End') {
    ev.preventDefault();
    return true;
  }
  if (ev.ctrlKey && !ev.altKey && !ev.metaKey && k.length === 1) {
    const lower = k.toLowerCase();
    if (lower === 'v') return true;
    if (lower === 'c') {
      ev.preventDefault();
      return true;
    }
    const browserUi = new Set([
      'a', 'b', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u', 'w', 'x', 'y', 'z',
    ]);
    if (browserUi.has(lower)) {
      ev.preventDefault();
      return true;
    }
  }
  if (ev.ctrlKey && (k === 'F5' || k === 'F12')) {
    ev.preventDefault();
    return true;
  }
  return true;
}

export function VisualizationPage() {
  const auth = getAuthState();
  const [activeTab, setActiveTab] = useState<VizTab>('elements');
  const [elementKeyword, setElementKeyword] = useState('');
  const [droppedSymbols, setDroppedSymbols] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');
  const [materialPickerQuery, setMaterialPickerQuery] = useState('');
  const [materialOptions, setMaterialOptions] = useState<MaterialOption[]>([]);
  const [selectedMaterialId, setSelectedMaterialId] = useState('');
  const [host, setHost] = useState('127.0.0.1');
  const [port, setPort] = useState(22);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [terminalState, setTerminalState] = useState<TerminalState>('idle');
  const [terminalOutput, setTerminalOutput] = useState('');
  const [searchCards, setSearchCards] = useState<SearchCardItem[]>([]);
  const [searchEmptyText, setSearchEmptyText] = useState('');
  const [inputRows, setInputRows] = useState<InputKvRow[]>([{ id: crypto.randomUUID(), key: '', value: '' }]);
  const [submitStatus, setSubmitStatus] = useState('');
  const [myApplications, setMyApplications] = useState<DataInputApplication[]>([]);
  const [loadingApplications, setLoadingApplications] = useState(false);
  const [status, setStatus] = useState('');
  const [sidebarLattice, setSidebarLattice] = useState<LatticeRenderData | null>(null);
  const [sidebarLatticeStatus, setSidebarLatticeStatus] = useState('');
  const sidebarLatticeRef = useRef<HTMLDivElement | null>(null);
  const [servers, setServers] = useState<TerminalServerProfile[]>(() => readSavedTerminalServers());
  const [selectedServerId, setSelectedServerId] = useState<string>(() => readSavedTerminalServers()[0]?.id ?? DEFAULT_TERMINAL_SERVER.id);
  const [serverReachability, setServerReachability] = useState<Record<string, { status: ReachabilityStatus; label: string }>>({});
  const [newServerName, setNewServerName] = useState('');
  const [newServerHost, setNewServerHost] = useState('');
  const [newServerPort, setNewServerPort] = useState(22);
  const [newServerUsername, setNewServerUsername] = useState('');
  const [newServerPassword, setNewServerPassword] = useState('');
  const [transferStatus, setTransferStatus] = useState('');
  const [remoteCwd, setRemoteCwd] = useState('~');
  const [remoteEntries, setRemoteEntries] = useState<RemoteEntry[]>([]);
  const [selectedRemoteName, setSelectedRemoteName] = useState('');
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [terminalSessions, setTerminalSessions] = useState<TerminalSessionTab[]>([
    {
      id: 'session-1',
      name: '终端 1',
      host: '127.0.0.1',
      port: 22,
      username: 'admin',
      password: '',
      output: '',
      cwd: '~',
      entries: [],
      selectedName: '',
      state: 'idle',
    },
  ]);
  const [activeTerminalSessionId, setActiveTerminalSessionId] = useState('session-1');
  const [uploadQueue, setUploadQueue] = useState<UploadQueueItem[]>([]);
  const terminalOutputRef = useRef('');
  const downloadCaptureRef = useRef<{ active: boolean; remotePath: string; buffer: string }>({
    active: false,
    remotePath: '',
    buffer: '',
  });
  const terminalMountRef = useRef<HTMLDivElement | null>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const terminalAuthOkRef = useRef(false);
  const terminalTextEncoderRef = useRef(new TextEncoder());
  const reconnectTimerRef = useRef<number | null>(null);
  const wsOpenTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const manualDisconnectRef = useRef(false);
  const suppressReconnectRef = useRef(false);
  const fsCaptureRef = useRef<{ active: boolean; payload: string }>({ active: false, payload: '' });
  const lastTabRef = useRef<VizTab>('elements');

  const elementFormula = useMemo(() => {
    if (droppedSymbols.length === 0) {
      return '';
    }
    const countMap = new Map<string, number>();
    droppedSymbols.forEach((symbol) => {
      countMap.set(symbol, (countMap.get(symbol) ?? 0) + 1);
    });
    return Array.from(countMap.entries())
      .map(([symbol, count]) => (count > 1 ? `${count}${symbol}` : symbol))
      .join('-');
  }, [droppedSymbols]);

  const filteredElements = useMemo(() => {
    const key = elementKeyword.trim().toLowerCase();
    if (!key) {
      return PERIODIC_ELEMENTS;
    }
    return PERIODIC_ELEMENTS.filter((element) => {
      return (
        element.symbol.toLowerCase().includes(key) ||
        element.name.toLowerCase().includes(key) ||
        String(element.number).includes(key)
      );
    });
  }, [elementKeyword]);

  const elementBySymbol = useMemo(() => {
    const table = new Map<string, (typeof PERIODIC_ELEMENTS)[number]>();
    PERIODIC_ELEMENTS.forEach((item) => table.set(item.symbol, item));
    return table;
  }, []);

  const filteredSymbolSet = useMemo(() => new Set(filteredElements.map((item) => item.symbol)), [filteredElements]);

  const filteredMaterials = useMemo(() => {
    if (sourceFilter === 'all') {
      return materialOptions;
    }
    return materialOptions.filter((item) => item.sourceType === sourceFilter);
  }, [materialOptions, sourceFilter]);

  const pickerMaterials = useMemo(() => {
    const q = materialPickerQuery.trim().toLowerCase();
    let list = q ? filteredMaterials.filter((opt) => materialMatchesPickerQuery(opt, q)) : filteredMaterials;
    const selId = selectedMaterialId;
    if (selId && !list.some((o) => o.id === selId)) {
      const sel = filteredMaterials.find((o) => o.id === selId);
      if (sel) {
        list = [sel, ...list];
      }
    }
    return list;
  }, [filteredMaterials, materialPickerQuery, selectedMaterialId]);

  const visibleSearchCards = useMemo(() => {
    const q = materialPickerQuery.trim().toLowerCase();
    if (!q) return searchCards;
    return searchCards.filter((card) => {
      const hay = `${card.title} ${card.subtitle ?? ''} ${card.tag} ${card.id}`.toLowerCase();
      return hay.includes(q);
    });
  }, [searchCards, materialPickerQuery]);

  const selectedMaterial = useMemo(
    () => filteredMaterials.find((item) => item.id === selectedMaterialId),
    [filteredMaterials, selectedMaterialId],
  );

  const selectedMaterialFields = useMemo(() => {
    if (!selectedMaterial) {
      return [];
    }
    return Object.entries(selectedMaterial.data)
      .filter(([, value]) => value !== null && value !== undefined && String(value) !== '')
      .filter(([, value]) => typeof value !== 'object')
      .map(([key, value]) => ({ key, value: String(value) }));
  }, [selectedMaterial]);

  const selectedCoreMetrics = useMemo(() => {
    if (!selectedMaterial) {
      return null;
    }
    const data = selectedMaterial.data;
    const axes = parseLatticeAxes(data);
    const latticeText =
      axes.a && axes.b && axes.c
        ? `a=${axes.a.toFixed(3)} b=${axes.b.toFixed(3)} c=${axes.c.toFixed(3)}`
        : String(data.晶格常数 ?? data.晶格参数 ?? 'NONE DATA');
    const structure = String(data.晶体结构 ?? 'NONE DATA');
    const c11 = String(data.弹性刚度常数C11 ?? 'NONE DATA');
    const c12 = String(data.弹性刚度常数C12 ?? data.C12 ?? 'NONE DATA');
    const young = String(data['杨氏模量E-H'] ?? 'NONE DATA');
    const source = String(data.source ?? data.data_source ?? selectedMaterial.tag);
    const listingId = selectedMaterial.sourceType === 'mp' ? normalizeMpApiId(selectedMaterial.id) : selectedMaterial.id;
    const formulaPretty = getMaterialFormulaPretty(selectedMaterial);
    const elementsSummary = formatMaterialElementsSummary(data);
    return {
      latticeText,
      structure,
      c11,
      c12,
      young,
      source,
      listingId,
      formulaPretty,
      elementsSummary,
    };
  }, [selectedMaterial]);

  const canSend = terminalState === 'connected' && ws?.readyState === WebSocket.OPEN;

  const selectedServer = useMemo(
    () => servers.find((item) => item.id === selectedServerId) ?? servers[0] ?? DEFAULT_TERMINAL_SERVER,
    [servers, selectedServerId],
  );

  const terminalConnectionMode = useMemo(
    () => (import.meta.env.VITE_TERMINAL_CONNECTION_MODE || 'bridge').toLowerCase(),
    [],
  );

  function wsSendTerminalPayload(targetWs: WebSocket | null | undefined, payload: string) {
    if (!targetWs || targetWs.readyState !== WebSocket.OPEN || !terminalAuthOkRef.current) return;
    targetWs.send(terminalTextEncoderRef.current.encode(payload));
  }
  function sendTerminalResize(targetWs: WebSocket) {
    if (targetWs.readyState !== WebSocket.OPEN) return;
    const dims = fitAddonRef.current?.proposeDimensions();
    const shellRect = terminalMountRef.current?.getBoundingClientRect();
    if (!dims) return;
    targetWs.send(
      JSON.stringify({
        type: 'resize',
        cols: dims.cols,
        rows: dims.rows,
        widthPx: Math.max(1, Math.round(shellRect?.width ?? 640)),
        heightPx: Math.max(1, Math.round(shellRect?.height ?? 320)),
      }),
    );
  }

  function clearReconnectTimer() {
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }

  function clearWsOpenTimeout() {
    if (wsOpenTimeoutRef.current != null) {
      window.clearTimeout(wsOpenTimeoutRef.current);
      wsOpenTimeoutRef.current = null;
    }
  }

  function scheduleReconnect() {
    clearReconnectTimer();
    const delay = Math.min(15000, 1000 * 2 ** reconnectAttemptRef.current);
    reconnectAttemptRef.current += 1;
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      if (!manualDisconnectRef.current) {
        void connectTerminal();
      }
    }, delay);
    xtermRef.current?.writeln(`\r\n\x1b[33m连接中断，${Math.round(delay / 1000)} 秒后重连...\x1b[0m`);
  }

  async function probeServerRealtime(profile: TerminalServerProfile): Promise<{ online: boolean; label: string }> {
    if (terminalConnectionMode === 'bridge') {
      try {
        const bridgeResp = await fetch('/api/ssh/ping', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            host: profile.host,
            port: profile.port,
            username: profile.username,
            password: profile.password || '',
          }),
        });
        if (bridgeResp.ok) {
          const j = (await bridgeResp.json()) as { reachable?: boolean; sshHandshake?: boolean };
          if (j.sshHandshake) return { online: true, label: '在线(SSH)' };
          if (j.reachable) return { online: false, label: '端口可达' };
        }
      } catch {
        // fallback below
      }
    }
    try {
      const r = await pythonApi.terminalReachable({ host: profile.host, port: profile.port, timeout: 2.5 });
      return r.reachable ? { online: true, label: '在线' } : { online: false, label: `离线(${r.code ?? '不可达'})` };
    } catch {
      return { online: false, label: '离线(异常)' };
    }
  }

  useEffect(() => {
    return () => {
      clearReconnectTimer();
      clearWsOpenTimeout();
      if (ws && ws.readyState === WebSocket.OPEN) {
        suppressReconnectRef.current = true;
        ws.close(1000, 'page-unmount');
      }
    };
  }, [ws]);

  useEffect(() => {
    localStorage.setItem(TERMINAL_SERVERS_KEY, JSON.stringify(servers));
  }, [servers]);

  useEffect(() => {
    setHost(selectedServer.host);
    setPort(selectedServer.port);
    setUsername(selectedServer.username);
    setPassword(selectedServer.password ?? '');
  }, [selectedServer]);

  useEffect(() => {
    const checkAll = async () => {
      const next: Record<string, { status: ReachabilityStatus; label: string }> = {};
      await Promise.all(
        servers.map(async (server) => {
          const rt = await probeServerRealtime(server);
          next[server.id] = rt.online ? { status: 'online', label: rt.label } : { status: 'offline', label: rt.label };
        }),
      );
      setServerReachability(next);
    };
    setServerReachability((prev) => {
      const patch = { ...prev };
      servers.forEach((s) => {
        if (!patch[s.id]) patch[s.id] = { status: 'checking', label: '检测中' };
      });
      return patch;
    });
    void checkAll();
    const timer = window.setInterval(() => {
      void checkAll();
    }, 6000);
    return () => window.clearInterval(timer);
  }, [servers]);

  useEffect(() => {
    terminalOutputRef.current = terminalOutput;
  }, [terminalOutput]);

  useEffect(() => {
    wsRef.current = ws;
  }, [ws]);

  useEffect(() => {
    setTerminalSessions((prev) =>
      prev.map((item) =>
        item.id === activeTerminalSessionId
          ? {
              ...item,
              host,
              port,
              username,
              password,
              cwd: remoteCwd,
              entries: remoteEntries,
              selectedName: selectedRemoteName,
              state: terminalState,
            }
          : item,
      ),
    );
  }, [activeTerminalSessionId, host, port, username, password, remoteCwd, remoteEntries, selectedRemoteName, terminalState]);

  useEffect(() => {
    if (!terminalMountRef.current || xtermRef.current) {
      return;
    }
    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Consolas, "JetBrains Mono", "Courier New", monospace',
      theme: {
        background: '#000000',
        foreground: '#e6edf3',
        cursor: '#58a6ff',
      },
      scrollback: 4000,
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.attachCustomKeyEventHandler(preventBrowserStealingTerminalKeys);
    terminal.open(terminalMountRef.current);
    fitAddon.fit();
    terminal.writeln('终端已就绪，点击连接后可直接输入命令。');
    terminal.onData((data) => {
      const currentWs = wsRef.current;
      if (currentWs && currentWs.readyState === WebSocket.OPEN && terminalAuthOkRef.current) {
        currentWs.send(terminalTextEncoderRef.current.encode(data));
      }
    });
    xtermRef.current = terminal;
    fitAddonRef.current = fitAddon;
    const onResize = () => fitAddon.fit();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      terminal.dispose();
      xtermRef.current = null;
      fitAddonRef.current = null;
    };
  }, [activeTab]);

  function focusTerminalSoon() {
    window.setTimeout(() => {
      xtermRef.current?.focus();
    }, 80);
  }

  function createTerminalNow() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      setStatus('终端已创建并连接');
      focusTerminalSoon();
      return;
    }
    void connectTerminal();
  }

  useEffect(() => {
    const prev = lastTabRef.current;
    if (activeTab === 'terminal' && prev !== 'terminal') {
      createTerminalNow();
      focusTerminalSoon();
    }
    lastTabRef.current = activeTab;
  }, [activeTab]);

  useEffect(() => {
    if (!canSend || !ws) return;
    const timer = window.setInterval(() => {
      if (document.hidden && ws.readyState === WebSocket.OPEN && terminalAuthOkRef.current) {
        wsSendTerminalPayload(ws, 'printf ""\n');
      }
    }, 45000);
    return () => window.clearInterval(timer);
  }, [canSend, ws]);

  useEffect(() => {
    const reconnectOnFocus = () => {
      if (manualDisconnectRef.current) return;
      const currentWs = wsRef.current;
      if (!currentWs || currentWs.readyState === WebSocket.CLOSING || currentWs.readyState === WebSocket.CLOSED) {
        if (!reconnectTimerRef.current) {
          void connectTerminal();
        }
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') reconnectOnFocus();
    };
    window.addEventListener('focus', reconnectOnFocus);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('focus', reconnectOnFocus);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  useEffect(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const onResize = () => {
      sendTerminalResize(ws);
    };
    const timer = window.setTimeout(onResize, 160);
    window.addEventListener('resize', onResize);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('resize', onResize);
    };
  }, [ws]);

  useEffect(() => {
    if (!auth.username) {
      setMyApplications([]);
      return;
    }
    void loadMyApplications();
  }, [auth.username]);

  useEffect(() => {
    if (!elementFormula) {
      setMaterialOptions([]);
      setSelectedMaterialId('');
      setSidebarLattice(null);
      return;
    }
    void fetchBarMaterials();
  }, [elementFormula]);

  useEffect(() => {
    setSidebarLattice(null);
    setSidebarLatticeStatus('');
  }, [selectedMaterialId]);

  useEffect(() => {
    const mount = sidebarLatticeRef.current;
    if (!mount || !sidebarLattice) {
      return;
    }
    mount.innerHTML = '';
    const width = Math.max(220, Math.floor(mount.clientWidth || 260));
    const height = 220;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#f8fbff');
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.set(4, 4, 4);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    mount.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const light = new THREE.DirectionalLight(0xffffff, 0.9);
    light.position.set(6, 8, 6);
    scene.add(light);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));

    const elementColors: Record<string, number> = {
      H: 0xffffff,
      C: 0x909090,
      N: 0x3050f8,
      O: 0xff0d0d,
      F: 0x90e050,
      Cl: 0x1ff01f,
      Nb: 0x73c2c9,
      U: 0x008fff,
      default: 0x00a5e5,
    };
    const sphereGeometry = new THREE.SphereGeometry(Math.max(sidebarLattice.latticeConst * 0.12, 0.16), 22, 22);
    const vectors = sidebarLattice.positions.map((pos) => new THREE.Vector3(pos[0], pos[1], pos[2]));
    const center = vectors.reduce((sum, v) => sum.add(v), new THREE.Vector3()).divideScalar(Math.max(vectors.length, 1));

    vectors.forEach((point, idx) => {
      const symbol = sidebarLattice.elements[idx] ?? 'default';
      const material = new THREE.MeshPhongMaterial({ color: elementColors[symbol] ?? elementColors.default, shininess: 90 });
      const atom = new THREE.Mesh(sphereGeometry, material);
      atom.position.copy(point);
      scene.add(atom);
    });

    sidebarLattice.connections.forEach(([a, b]) => {
      if (!vectors[a] || !vectors[b]) return;
      const geometry = new THREE.BufferGeometry().setFromPoints([vectors[a], vectors[b]]);
      const bond = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x64748b }));
      scene.add(bond);
    });

    const box = new THREE.Box3().setFromPoints(vectors);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z, 1);
    camera.position.set(center.x + maxDim * 1.8, center.y + maxDim * 1.4, center.z + maxDim * 1.8);
    controls.target.copy(center);
    controls.update();

    let frameId = 0;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();
    return () => {
      cancelAnimationFrame(frameId);
      controls.dispose();
      renderer.dispose();
      mount.innerHTML = '';
    };
  }, [sidebarLattice]);

  async function checkReachable() {
    const rt = await probeServerRealtime({
      id: 'temp',
      name: 'current',
      host,
      port,
      username,
      password,
    });
    setStatus(`连通性检查：${rt.label}`);
  }

  async function connectTerminal() {
    if (ws?.readyState === WebSocket.OPEN && terminalAuthOkRef.current) {
      setStatus('终端已连接，无需重复连接');
      return;
    }
    if (ws?.readyState === WebSocket.CONNECTING) {
      setStatus('终端通道正在连接中，请稍候…');
      return;
    }
    try {
      manualDisconnectRef.current = false;
      clearReconnectTimer();
      clearWsOpenTimeout();
      terminalAuthOkRef.current = false;
      setTerminalState('connecting');
      setStatus('正在建立终端连接...');
      xtermRef.current?.writeln(`\r\n[连接] ${host}:${port} as ${username} ...`);
      xtermRef.current?.writeln('[本地] 正在连接浏览器 → 本机终端服务（WebSocket）…');
      const socket = await openTerminalSocket();

      wsOpenTimeoutRef.current = window.setTimeout(() => {
        wsOpenTimeoutRef.current = null;
        if (socket.readyState === WebSocket.OPEN) return;
        xtermRef.current?.writeln(
          '\r\n\x1b[31m[超时] 本机终端 WebSocket 长时间无法连通。\x1b[0m\r\n请检查：① 是否已启动 pyserver.py；② Python 终端 WS 端口是否与前端一致（默认 \x1b[33m8765\x1b[0m，可用环境变量 \x1b[33mTERMINAL_WS_PORT\x1b[0m）；③ 若 pyserver 因端口占用改用其它端口，需同步修改 frontend/vite.config.ts 中的 terminalWsPort 并重启 \x1b[33mnpm run dev\x1b[0m。',
        );
        try {
          socket.close();
        } catch {
          /* ignore */
        }
        terminalAuthOkRef.current = false;
        setWs(null);
        setTerminalState('error');
        setStatus('终端 WebSocket 连接超时（本机通道）');
      }, 12000);

      socket.onopen = () => {
        clearWsOpenTimeout();
        reconnectAttemptRef.current = 0;
        xtermRef.current?.writeln('[本地] WebSocket 已接通，正在通过 SSH 登录远程主机（若网络慢可能需约 25 秒）…');
        const dims = fitAddonRef.current?.proposeDimensions() ?? { cols: 80, rows: 24 };
        socket.send(
          JSON.stringify({
            type: 'auth',
            host,
            port,
            username,
            password,
            cols: dims.cols,
            rows: dims.rows,
            widthPx: Math.max(1, Math.round(terminalMountRef.current?.getBoundingClientRect().width ?? 640)),
            heightPx: Math.max(1, Math.round(terminalMountRef.current?.getBoundingClientRect().height ?? 320)),
            term: 'xterm-256color',
            cwd: remoteCwd || '',
          }),
        );
        setStatus('正在验证 SSH...');
        fitAddonRef.current?.fit();
      };
      socket.onmessage = (ev) => {
        if (typeof ev.data === 'string') {
          try {
            const msg = JSON.parse(ev.data) as { type?: string; message?: string };
            if (msg.type === 'auth-error') {
              xtermRef.current?.writeln(`\r\n\x1b[31m${msg.message || '连接失败'}\x1b[0m`);
              setTerminalState('error');
              setStatus(msg.message || '终端认证失败');
              terminalAuthOkRef.current = false;
              try {
                socket.close();
              } catch {
                /* ignore */
              }
              return;
            }
            if (msg.type === 'auth-ok') {
              terminalAuthOkRef.current = true;
              setTerminalState('connected');
              setStatus('终端已连接');
              fitAddonRef.current?.fit();
              sendTerminalResize(socket);
              window.setTimeout(() => requestRemoteList('.'), 240);
            }
          } catch {
            /* 非 JSON 控制帧忽略 */
          }
          return;
        }
        const buf = ev.data instanceof ArrayBuffer ? new Uint8Array(ev.data) : new Uint8Array();
        const text = new TextDecoder('utf-8', { fatal: false }).decode(buf);
        handleTerminalChunk(text);
      };
      socket.onclose = (event) => {
        clearWsOpenTimeout();
        terminalAuthOkRef.current = false;
        setWs(null);
        setTerminalState('closed');
        setStatus('终端连接已关闭');
        xtermRef.current?.writeln('\r\n[连接已关闭]');
        const closedByAction =
          suppressReconnectRef.current ||
          manualDisconnectRef.current ||
          ['manual-disconnect', 'switch-session', 'remove-session', 'page-unmount'].includes(event.reason);
        suppressReconnectRef.current = false;
        if (!closedByAction) scheduleReconnect();
      };
      socket.onerror = () => {
        clearWsOpenTimeout();
        terminalAuthOkRef.current = false;
        setWs(null);
        setTerminalState('error');
        setStatus('终端连接异常');
        xtermRef.current?.writeln('\r\n[连接异常]');
      };
      setWs(socket);
      window.setTimeout(() => {
        if (socket.readyState === WebSocket.OPEN && terminalAuthOkRef.current) {
          sendTerminalResize(socket);
        }
      }, 420);
    } catch (error) {
      setTerminalState('error');
      const message = (error as Error).message || '连接失败';
      if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(message)) {
        setStatus('无法连接到后端服务，请先确认 pyserver.py 正在运行且监听 3569 端口');
      } else {
        setStatus(message);
      }
    }
  }

  function disconnectTerminal() {
    if (!ws) {
      setStatus('当前没有活动连接');
      return;
    }
    manualDisconnectRef.current = true;
    clearReconnectTimer();
    clearWsOpenTimeout();
    suppressReconnectRef.current = true;
    terminalAuthOkRef.current = false;
    ws.close(1000, 'manual-disconnect');
    setWs(null);
    setTerminalState('closed');
  }

  function saveCurrentSessionSnapshot(patch?: Partial<TerminalSessionTab>) {
    setTerminalSessions((prev) =>
      prev.map((item) =>
        item.id === activeTerminalSessionId
          ? {
              ...item,
              host,
              port,
              username,
              password,
              output: terminalOutput,
              cwd: remoteCwd,
              entries: remoteEntries,
              selectedName: selectedRemoteName,
              state: terminalState,
              ...(patch ?? {}),
            }
          : item,
      ),
    );
  }

  function switchTerminalSession(nextId: string) {
    if (nextId === activeTerminalSessionId) return;
    saveCurrentSessionSnapshot();
    if (ws && ws.readyState === WebSocket.OPEN) {
      suppressReconnectRef.current = true;
      ws.close(1000, 'switch-session');
      setWs(null);
    }
    const next = terminalSessions.find((item) => item.id === nextId);
    if (!next) return;
    const nextState = next.state === 'connected' ? 'idle' : next.state;
    setActiveTerminalSessionId(nextId);
    setHost(next.host);
    setPort(next.port);
    setUsername(next.username);
    setPassword(next.password);
    setTerminalOutput(next.output || '');
    setRemoteCwd(next.cwd || '~');
    setRemoteEntries(next.entries || []);
    setSelectedRemoteName(next.selectedName || '');
    setTerminalState(nextState || 'idle');
    xtermRef.current?.clear();
    if (next.output) {
      xtermRef.current?.write(next.output);
    }
    setStatus(`已切换到 ${next.name}`);
  }

  function createTerminalSession(server?: TerminalServerProfile, autoConnect = false) {
    const preset = server
      ? {
          name: server.name,
          host: server.host,
          port: server.port,
          username: server.username,
          password: server.password ?? '',
          serverId: server.id,
        }
      : {
          name: '',
          host,
          port,
          username,
          password,
          serverId: undefined as string | undefined,
        };
    const id = `session-${Date.now()}`;
    const index = terminalSessions.length + 1;
    const item: TerminalSessionTab = {
      id,
      serverId: preset.serverId,
      name: preset.name || `终端 ${index}`,
      host: preset.host,
      port: preset.port,
      username: preset.username,
      password: preset.password,
      output: '',
      cwd: '~',
      entries: [],
      selectedName: '',
      state: 'idle',
    };
    saveCurrentSessionSnapshot();
    if (ws && ws.readyState === WebSocket.OPEN) {
      suppressReconnectRef.current = true;
      ws.close(1000, 'switch-session');
      setWs(null);
    }
    setTerminalSessions((prev) => [...prev, item]);
    setActiveTerminalSessionId(id);
    setHost(preset.host);
    setPort(preset.port);
    setUsername(preset.username);
    setPassword(preset.password);
    setTerminalOutput(item.output);
    setRemoteCwd('~');
    setRemoteEntries([]);
    setSelectedRemoteName('');
    setTerminalState('idle');
    xtermRef.current?.clear();
    if (activeTab !== 'terminal') {
      setActiveTab('terminal');
    }
    if (autoConnect) {
      window.setTimeout(() => {
        void connectTerminal();
      }, 120);
    }
  }

  function selectServerAndOpenTerminal(server: TerminalServerProfile) {
    setSelectedServerId(server.id);
    createTerminalSession(server, true);
  }

  function removeTerminalSession(id: string) {
    if (terminalSessions.length <= 1) {
      setStatus('至少保留一个终端会话');
      return;
    }
    const nextList = terminalSessions.filter((item) => item.id !== id);
    setTerminalSessions(nextList);
    if (activeTerminalSessionId === id) {
      const next = nextList[0];
      const nextState = next.state === 'connected' ? 'idle' : next.state;
      if (ws && ws.readyState === WebSocket.OPEN) {
        suppressReconnectRef.current = true;
        ws.close(1000, 'remove-session');
        setWs(null);
      }
      setActiveTerminalSessionId(next.id);
      setHost(next.host);
      setPort(next.port);
      setUsername(next.username);
      setPassword(next.password);
      setTerminalOutput(next.output || '');
      setRemoteCwd(next.cwd || '~');
      setRemoteEntries(next.entries || []);
      setSelectedRemoteName(next.selectedName || '');
      setTerminalState(nextState || 'idle');
      xtermRef.current?.clear();
      if (next.output) xtermRef.current?.write(next.output);
    }
  }

  function handleTerminalChunk(chunk: string) {
    let displayChunk = chunk;
    const fsCapture = fsCaptureRef.current;
    const fsBegin = '__FS_BEGIN__';
    const fsEnd = '__FS_END__';

    if (!fsCapture.active) {
      const beginIdx = displayChunk.indexOf(fsBegin);
      if (beginIdx >= 0) {
        fsCapture.active = true;
        fsCapture.payload = '';
        const afterBegin = displayChunk.slice(beginIdx + fsBegin.length);
        displayChunk = displayChunk.slice(0, beginIdx);
        const endIdx = afterBegin.indexOf(fsEnd);
        if (endIdx >= 0) {
          fsCapture.payload += afterBegin.slice(0, endIdx);
          parseAndApplyRemoteList(fsCapture.payload);
          fsCapture.active = false;
          fsCapture.payload = '';
          displayChunk += afterBegin.slice(endIdx + fsEnd.length);
        } else {
          fsCapture.payload += afterBegin;
        }
      }
    } else {
      const endIdx = displayChunk.indexOf(fsEnd);
      if (endIdx >= 0) {
        fsCapture.payload += displayChunk.slice(0, endIdx);
        parseAndApplyRemoteList(fsCapture.payload);
        fsCapture.active = false;
        fsCapture.payload = '';
        displayChunk = displayChunk.slice(endIdx + fsEnd.length);
      } else {
        fsCapture.payload += displayChunk;
        displayChunk = '';
      }
    }

    const markerBegin = '__FILE_DOWNLOAD_BEGIN__';
    const markerEnd = '__FILE_DOWNLOAD_END__';
    const capture = downloadCaptureRef.current;
    if (!capture.active) {
      const beginIdx = displayChunk.indexOf(markerBegin);
      if (beginIdx >= 0) {
        capture.active = true;
        capture.buffer = '';
        const afterBegin = displayChunk.slice(beginIdx + markerBegin.length);
        displayChunk = displayChunk.slice(0, beginIdx);
        const endIdx = afterBegin.indexOf(markerEnd);
        if (endIdx >= 0) {
          capture.buffer += afterBegin.slice(0, endIdx);
          finalizeDownloadCapture();
          displayChunk += afterBegin.slice(endIdx + markerEnd.length);
        } else {
          capture.buffer += afterBegin;
        }
      }
    } else {
      const endIdx = displayChunk.indexOf(markerEnd);
      if (endIdx >= 0) {
        capture.buffer += displayChunk.slice(0, endIdx);
        finalizeDownloadCapture();
        displayChunk = displayChunk.slice(endIdx + markerEnd.length);
      } else {
        capture.buffer += displayChunk;
        displayChunk = '';
      }
    }
    const terminal = xtermRef.current;
    if (terminal && displayChunk) {
      terminal.write(displayChunk);
    }
    if (displayChunk) {
      setTerminalOutput((prev) => `${prev}${displayChunk}`);
      setTerminalSessions((prev) =>
        prev.map((item) => (item.id === activeTerminalSessionId ? { ...item, output: `${item.output}${displayChunk}` } : item)),
      );
    }
  }

  function parseAndApplyRemoteList(payload: string) {
    const lines = payload
      .split(/\r?\n/)
      .map((line) => line.trimEnd())
      .filter((line) => line.trim() !== '');
    const cwdLine = lines.find((line) => line.startsWith('__FS_CWD__'));
    const cwd = cwdLine ? cwdLine.replace('__FS_CWD__', '').trim() : remoteCwd;
    const entries: RemoteEntry[] = lines
      .filter((line) => line.startsWith('__FS_ITEM__'))
      .map((line) => line.replace('__FS_ITEM__', ''))
      .map((line) => {
        const [kind, sizeText, ...nameParts] = line.split('\t');
        return {
          kind: kind === 'd' ? 'd' : 'f',
          size: Number(sizeText) || 0,
          name: nameParts.join('\t'),
        } as RemoteEntry;
      })
      .filter((item) => item.name && item.name !== '.' && item.name !== '..')
      .sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === 'd' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
    setRemoteCwd(cwd || '/');
    setRemoteEntries(entries);
    setSelectedRemoteName('');
    setTerminalSessions((prev) =>
      prev.map((item) =>
        item.id === activeTerminalSessionId ? { ...item, cwd: cwd || '/', entries, selectedName: '' } : item,
      ),
    );
  }

  function requestRemoteList(targetPath?: string) {
    if (!canSend || !ws) {
      setTransferStatus('请先连接终端');
      return;
    }
    const path = (targetPath ?? remoteCwd).replace(/"/g, '\\"');
    const cmd =
      `__TSX_TARGET="${path}"\n` +
      `if [ -n "$__TSX_TARGET" ] && [ -d "$__TSX_TARGET" ]; then cd "$__TSX_TARGET"; fi\n` +
      `echo __FS_BEGIN__\n` +
      `printf "__FS_CWD__%s\\n" "$PWD"\n` +
      `for n in .* *; do [ "$n" = "." ] && continue; [ "$n" = ".." ] && continue; [ ! -e "$n" ] && continue; ` +
      `if [ -d "$n" ]; then k="d"; else k="f"; fi; s=$(stat -c %s -- "$n" 2>/dev/null || echo 0); ` +
      `printf "__FS_ITEM__%s\\t%s\\t%s\\n" "$k" "$s" "$n"; done\n` +
      `echo __FS_END__\n`;
    wsSendTerminalPayload(ws, cmd);
  }

  function deleteRemoteEntry(entry: RemoteEntry) {
    if (!canSend || !ws) {
      setTransferStatus('请先连接终端');
      return;
    }
    const target = joinPosixPath(remoteCwd, entry.name);
    const ok = window.confirm(`确定删除「${target}」${entry.kind === 'd' ? '及其目录内容' : ''}？`);
    if (!ok) return;
    const cmd =
      entry.kind === 'd'
        ? `rm -rf "${target.replace(/"/g, '\\"')}"\n`
        : `rm -f "${target.replace(/"/g, '\\"')}"\n`;
    wsSendTerminalPayload(ws, cmd);
    setTransferStatus(`已请求删除：${target}`);
    setSelectedRemoteName('');
    window.setTimeout(() => requestRemoteList(remoteCwd), 400);
  }

  async function copyRemotePathToClipboard(entry: RemoteEntry) {
    const target = joinPosixPath(remoteCwd, entry.name);
    try {
      await navigator.clipboard.writeText(target);
      setTransferStatus(`已复制路径：${target}`);
    } catch {
      setTransferStatus('复制路径失败');
    }
  }

  function mkdirRemoteFolder() {
    if (!canSend || !ws) {
      setTransferStatus('请先连接终端');
      return;
    }
    const raw = window.prompt('新建文件夹名称（在当前远程路径下）', '');
    if (raw == null || !raw.trim()) return;
    const safe = raw.trim().replace(/"/g, '\\"');
    const target = joinPosixPath(remoteCwd, safe);
    wsSendTerminalPayload(ws, `mkdir -p "${target}"\n`);
    setTransferStatus(`已请求创建目录：${target}`);
    window.setTimeout(() => requestRemoteList(remoteCwd), 400);
  }

  function finalizeDownloadCapture() {
    const capture = downloadCaptureRef.current;
    capture.active = false;
    const base64Text = capture.buffer.replace(/\s+/g, '');
    capture.buffer = '';
    if (!base64Text) {
      setTransferStatus('下载失败：未捕获到文件内容');
      return;
    }
    try {
      const bytes = Uint8Array.from(atob(base64Text), (c) => c.charCodeAt(0));
      const blob = new Blob([bytes]);
      const fileName = capture.remotePath.split('/').pop() || 'download.bin';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setTransferStatus(`下载完成：${fileName}`);
    } catch {
      setTransferStatus('下载失败：文件解码异常');
    }
  }

  function addServerProfile() {
    if (!newServerHost.trim() || !newServerUsername.trim()) {
      setStatus('请填写服务器主机与用户名');
      return;
    }
    const server: TerminalServerProfile = {
      id: crypto.randomUUID(),
      name: newServerName.trim() || `${newServerUsername}@${newServerHost}`,
      host: newServerHost.trim(),
      port: Number(newServerPort) || 22,
      username: newServerUsername.trim(),
      password: newServerPassword,
    };
    setServers((prev) => [...prev, server]);
    setSelectedServerId(server.id);
    setNewServerName('');
    setNewServerHost('');
    setNewServerPort(22);
    setNewServerUsername('');
    setNewServerPassword('');
  }

  function updateCurrentServerProfile() {
    if (!selectedServer) return;
    setServers((prev) =>
      prev.map((item) =>
        item.id === selectedServer.id
          ? {
              ...item,
              host: host.trim(),
              port,
              username: username.trim(),
              password,
            }
          : item,
      ),
    );
    setStatus('服务器配置已更新');
  }

  function deleteCurrentServerProfile() {
    if (servers.length <= 1) {
      setStatus('至少保留一个服务器');
      return;
    }
    const next = servers.filter((item) => item.id !== selectedServer.id);
    setServers(next);
    setSelectedServerId(next[0].id);
  }

  async function uploadFileToRemote(file: File) {
    if (!canSend || !ws) {
      setTransferStatus('请先连接终端');
      return;
    }
    if (file.size > 256 * 1024) {
      setTransferStatus('文件过大（>256KB），建议通过独立 SFTP 工具传输');
      return;
    }
    const queueId = crypto.randomUUID();
    setUploadQueue((prev) => [...prev, { id: queueId, name: file.name, size: file.size, progress: 0, status: 'queued' }]);
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = '';
    setUploadQueue((prev) => prev.map((item) => (item.id === queueId ? { ...item, status: 'uploading' } : item)));
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
      if (i % Math.max(1024, Math.floor(bytes.length / 40)) === 0 || i === bytes.length - 1) {
        const progress = Math.round(((i + 1) / bytes.length) * 100);
        setUploadQueue((prev) => prev.map((item) => (item.id === queueId ? { ...item, progress } : item)));
      }
    }
    const b64 = btoa(binary);
    const remotePath = joinPosixPath(remoteCwd || '/tmp', file.name);
    const cmd = `cat <<'__TSX_UPLOAD_B64__' | base64 -d > "${remotePath}"\n${b64}\n__TSX_UPLOAD_B64__\nls -lh "${remotePath}"\n`;
    wsSendTerminalPayload(ws, cmd);
    setTransferStatus(`上传中：${file.name} -> ${remotePath}`);
    setUploadQueue((prev) =>
      prev.map((item) =>
        item.id === queueId ? { ...item, progress: 100, status: 'done', message: `已上传到 ${remotePath}` } : item,
      ),
    );
    setTimeout(() => requestRemoteList(remoteCwd), 320);
  }

  function requestDownloadFromRemote(remotePath: string) {
    if (!canSend || !ws) {
      setTransferStatus('请先连接终端');
      return;
    }
    downloadCaptureRef.current = { active: false, remotePath, buffer: '' };
    const safePath = remotePath.replace(/"/g, '\\"');
    const cmd =
      `echo __FILE_DOWNLOAD_BEGIN__\n` +
      `if [ -f "${safePath}" ]; then base64 "${safePath}"; else echo ""; fi\n` +
      `echo __FILE_DOWNLOAD_END__\n`;
    wsSendTerminalPayload(ws, cmd);
    setTransferStatus(`下载请求已发送：${remotePath}`);
  }

  async function generateSidebarLattice() {
    if (!selectedMaterial) {
      setSidebarLatticeStatus('请先选择数据');
      return;
    }
    const data = selectedMaterial.data;
    const positions = Array.isArray(data.positions) ? (data.positions as unknown[]) : [];
    const connections = Array.isArray(data.connections) ? (data.connections as unknown[]) : [];
    const parsedPositions = positions
      .map((row) => (Array.isArray(row) ? row.map((v) => Number(v)) : []))
      .filter((row) => row.length === 3 && row.every((v) => Number.isFinite(v))) as number[][];
    const parsedConnections = connections
      .map((row) => (Array.isArray(row) ? row.map((v) => Number(v)) : []))
      .filter((row) => row.length === 2 && row.every((v) => Number.isFinite(v))) as number[][];
    const formulaSymbols =
      String(data.化学式 ?? data.formula_pretty ?? data.db_formula ?? selectedMaterial.title)
        .match(/[A-Z][a-z]?/g)
        ?.filter(Boolean) ?? ['default'];
    const axes = parseLatticeAxes(data);
    const latticeConst = axes.a ?? axes.b ?? axes.c ?? 3.5;

    if (parsedPositions.length > 0) {
      setSidebarLattice({
        positions: parsedPositions,
        connections: parsedConnections,
        latticeConst,
        elements: parsedPositions.map((_, idx) => formulaSymbols[idx % formulaSymbols.length] ?? 'default'),
      });
      setSidebarLatticeStatus('已使用材料原始结构数据绘制');
      return;
    }

    try {
      const structure = String(data.晶体结构 ?? '');
      const latticeType = inferLatticeType(structure);
      const generated = await pythonApi.createLatticePicture({ lattice_const: latticeType });
      const generatedPoints = (generated.points ?? []) as unknown[];
      const generatedConnections = (generated.connections ?? []) as unknown[];
      const points = generatedPoints
        .map((row) => (Array.isArray(row) ? row.map((v) => Number(v)) : []))
        .filter((row) => row.length === 3 && row.every((v) => Number.isFinite(v))) as number[][];
      const bonds = generatedConnections
        .map((row) => (Array.isArray(row) ? row.map((v) => Number(v)) : []))
        .filter((row) => row.length === 2 && row.every((v) => Number.isFinite(v))) as number[][];
      setSidebarLattice({
        positions: points,
        connections: bonds,
        latticeConst,
        elements: points.map((_, idx) => formulaSymbols[idx % formulaSymbols.length] ?? 'default'),
      });
      setSidebarLatticeStatus(`已按 ${latticeType} 生成原胞图`);
    } catch (error) {
      setSidebarLattice(null);
      setSidebarLatticeStatus(`原胞图生成失败: ${(error as Error).message}`);
    }
  }

  function addDroppedSymbol(symbol: string) {
    setDroppedSymbols((prev) => (prev.includes(symbol) ? prev : [...prev, symbol]));
  }

  function removeDroppedSymbol(symbol: string) {
    setDroppedSymbols((prev) => prev.filter((item) => item !== symbol));
  }

  function clearDroppedSymbols() {
    setDroppedSymbols([]);
    setStatus('已清空右侧元素栏');
  }

  async function fetchBarMaterials() {
    if (!elementFormula) {
      return;
    }
    try {
      setSearchCards([]);
      setSearchEmptyText('');
      setMaterialOptions([]);
      setSelectedMaterialId('');
      setMaterialPickerQuery('');
      setStatus(`正在检索 ${elementFormula} ...`);
      const page2Res = (await pythonApi.page2Search({
        q: elementFormula,
        fuzzy: true,
        case_sensitive: false,
        search_in: 'property',
      })) as { elements?: unknown[]; materials?: unknown[]; error?: string };
      if (page2Res.error) {
        setStatus(`检索异常: ${page2Res.error}`);
      }
      const mysqlRes = (await pythonApi.mysqlReceive({
        element: elementFormula,
        text: '晶体结构,晶格常数,弹性刚度常数C11,C12,杨氏模量E-H',
      })) as {
        message?: unknown[];
        db_meta?: Record<string, unknown>;
        db_materials?: Array<Record<string, unknown>>;
      };
      let mpOptions: MaterialOption[] = [];
      try {
        await pythonApi.submitElement({ element: elementFormula, num_element: droppedSymbols.length || 1 });
        const mpRaw = await pythonApi.queryData();
        const mpLines = mpRaw.message ?? [];
        const mpError = mpLines.find(
          (line) =>
            String(line).includes('MP-API请求失败') ||
            String(line).startsWith('获取数据时出错') ||
            String(line).startsWith('获取数据时发生错误'),
        );
        if (mpError) {
          setStatus(String(mpError));
        }
        mpOptions = parseMpApiMaterials(mpLines);
      } catch (mpErr) {
        setStatus(`MP-API 不可用: ${(mpErr as Error).message}`);
      }
      const options: MaterialOption[] = [];

      (page2Res.elements ?? []).forEach((item, idx) => {
        const data = item as Record<string, unknown>;
        const id = normalizeLocalMaterialId(String(data.元素 ?? data.element ?? idx), `element-${idx}`);
        options.push({
          id,
          title: String(data.元素 ?? data.element ?? '元素'),
          sourceType: 'local',
          tag: 'element_inf',
          kind: 'elements',
          data: { ...data, id },
        });
      });

      (page2Res.materials ?? []).forEach((item, idx) => {
        const data = item as Record<string, unknown>;
        const isMp = data.source === 'Materials Project' || String(data.data_source ?? '').includes('Materials Project');
        const id = isMp
          ? String(data.id ?? `material-${idx}`).startsWith('mp-')
            ? String(data.id)
            : `mp-${data.id ?? idx}`
          : normalizeLocalMaterialId(data.id as string | number | undefined, `material-${idx}`);
        options.push({
          id,
          title: String(data.material_name ?? data.id ?? '化合物'),
          sourceType: isMp ? 'mp' : 'local',
          tag: isMp ? 'MP' : 'materials',
          kind: 'materials',
          data: { ...data, id: isMp ? id : normalizeLocalMaterialId(data.id as string | number | undefined, `material-${idx}`) },
        });
      });

      (mysqlRes.db_materials ?? []).forEach((item) => {
        const id = normalizeLocalMaterialId(item.id as string | number | undefined);
        options.push({
          id,
          title: String(item.material_name ?? item.db_formula ?? item.id ?? '本地材料'),
          sourceType: 'local',
          tag: 'db_materials',
          kind: 'materials',
          data: { ...item, id },
        });
      });

      if (mysqlRes.message && mysqlRes.message.some((v) => v !== null)) {
        options.push({
          id: 'db-meta',
          title: String(mysqlRes.db_meta?.formula ?? elementFormula),
          sourceType: 'local',
          tag: 'db_meta',
          kind: 'elements',
          data: {
            source: '数据库',
            晶体结构: mysqlRes.message[0],
            晶格常数: mysqlRes.message[1],
            弹性刚度常数C11: mysqlRes.message[2],
            弹性刚度常数C12: mysqlRes.message[3],
            '杨氏模量E-H': mysqlRes.message[4],
            ...mysqlRes.db_meta,
          },
        });
      }
      options.push(...mpOptions);

      const dedup = new Map<string, MaterialOption>();
      options.forEach((opt) => {
        if (!dedup.has(opt.id)) {
          dedup.set(opt.id, opt);
        }
      });
      const merged = Array.from(dedup.values());
      const requiredSymbols = Array.from(new Set(droppedSymbols));
      const matched = merged.filter((opt) => matchesSelectedSymbols(opt, requiredSymbols));
      setMaterialOptions(matched);
      if (matched.length > 0) {
        setSelectedMaterialId(matched[0].id);
      }
      setSearchCards(
        matched.map((opt) => ({
          id: opt.id,
          kind: opt.kind,
          title: getMaterialFormulaPretty(opt) || opt.title,
          subtitle: buildSearchCardSubtitle(opt),
          tag: opt.tag,
          fields: Object.entries(opt.data)
            .filter(([, value]) => value !== null && value !== undefined && String(value) !== '')
            .filter(([, value]) => typeof value !== 'object')
            .map(([key, value]) => ({ key, value: String(value) })),
        })),
      );
      setSearchEmptyText(matched.length === 0 ? '未找到与所选元素匹配的数据' : '');
      setStatus(`检索完成：${matched.length} 条匹配数据（${requiredSymbols.join(', ')}）`);
    } catch (error) {
      setMaterialOptions([]);
      setSelectedMaterialId('');
      setSearchCards([]);
      setSearchEmptyText(`检索失败: ${(error as Error).message}`);
      setStatus((error as Error).message);
    }
  }

  function addInputRow() {
    setInputRows((prev) => [...prev, { id: crypto.randomUUID(), key: '', value: '' }]);
  }

  function removeInputRow(id: string) {
    setInputRows((prev) => (prev.length > 1 ? prev.filter((row) => row.id !== id) : prev));
  }

  function updateInputRow(id: string, field: 'key' | 'value', value: string) {
    setInputRows((prev) => prev.map((row) => (row.id === id ? { ...row, [field]: value } : row)));
  }

  async function submitDataInputApplication() {
    if (!auth.username) {
      setSubmitStatus('请先登录');
      return;
    }
    const payload: Record<string, unknown> = {};
    inputRows.forEach((row) => {
      const key = row.key.trim();
      const value = row.value.trim();
      if (key) {
        payload[key] = value;
      }
    });
    if (Object.keys(payload).length === 0) {
      setSubmitStatus('请至少填写一行属性（需有字段名）');
      return;
    }
    try {
      const response = await pythonApi.submitDataInput({ username: auth.username, data: payload });
      setSubmitStatus(response.success ? '提交成功，请等待管理员审核。' : response.message);
      if (response.success) {
        setInputRows([{ id: crypto.randomUUID(), key: '', value: '' }]);
        await loadMyApplications();
      }
    } catch (error) {
      setSubmitStatus(`提交失败: ${(error as Error).message}`);
    }
  }

  async function loadMyApplications() {
    if (!auth.username) {
      setMyApplications([]);
      return;
    }
    try {
      setLoadingApplications(true);
      const response = await pythonApi.myDataInputs(auth.username);
      setMyApplications(response.data ?? []);
    } catch {
      // Keep existing list when refresh fails to avoid clearing useful context.
    } finally {
      setLoadingApplications(false);
    }
  }

  return (
    <>
      <section className="viz-legacy-page">
        <div className="viz-legacy-main-box">
          <nav className="viz-legacy-platform-nav" id="platformNav">
            <span className="viz-legacy-platform-title">基本物性计算平台</span>
            <div className="viz-legacy-platform-buttons">
              <button
                type="button"
                className={`viz-legacy-platform-item ${activeTab === 'elements' ? 'is-active' : ''}`}
                onClick={() => setActiveTab('elements')}
              >
                元素周期表
              </button>
              <button
                type="button"
                className={`viz-legacy-platform-item ${activeTab === 'detail' ? 'is-active' : ''}`}
                onClick={() => setActiveTab('detail')}
              >
                详细数据
              </button>
              <button
                type="button"
                className={`viz-legacy-platform-item ${activeTab === 'terminal' ? 'is-active' : ''}`}
                onClick={() => setActiveTab('terminal')}
              >
                终端
              </button>
              <button
                type="button"
                className={`viz-legacy-platform-item ${activeTab === 'input' ? 'is-active' : ''}`}
                onClick={() => setActiveTab('input')}
              >
                数据输入
              </button>
            </div>
          </nav>

          <div className="viz-legacy-sec-box">
            <div className="viz-main">

            {activeTab === 'elements' ? (
              <div className="panel" style={{ marginTop: 12 }}>
                <h3>元素周期表（可拖拽）</h3>
                <label className="field" style={{ maxWidth: 280 }}>
                  过滤元素
                  <input value={elementKeyword} onChange={(e) => setElementKeyword(e.target.value)} placeholder="输入元素符号，如 Nb" />
                </label>
                <div className="periodic-table-wrap">
                  <div className="periodic-legend">
                    <span className="legend-item alkali">碱金属</span>
                    <span className="legend-item alkaline-earth">碱土金属</span>
                    <span className="legend-item transition">过渡金属</span>
                    <span className="legend-item post-transition">后过渡金属</span>
                    <span className="legend-item metalloid">类金属</span>
                    <span className="legend-item nonmetal">非金属</span>
                    <span className="legend-item halogen">卤素</span>
                    <span className="legend-item noble-gas">稀有气体</span>
                    <span className="legend-item lanthanide">镧系</span>
                    <span className="legend-item actinide">锕系</span>
                  </div>
                  <div className="periodic-groups">
                    {Array.from({ length: 18 }, (_, i) => (
                      <span key={`group-${i + 1}`}>{i + 1}</span>
                    ))}
                  </div>
                  <div className="periodic-table">
                    {PERIODIC_ELEMENTS.map((element) => {
                      const pos = getElementGridPosition(element.number);
                      const isDimmed = elementKeyword.trim() !== '' && !filteredSymbolSet.has(element.symbol);
                      const category = getElementCategory(element.number, element.symbol);
                      return (
                        <button
                          key={element.symbol}
                          className={`element-card category-${category} ${isDimmed ? 'is-dimmed' : ''}`}
                          style={{ gridColumn: pos.col, gridRow: pos.row }}
                          draggable
                          onDragStart={(e) => e.dataTransfer.setData('text/plain', element.symbol)}
                          onClick={() => addDroppedSymbol(element.symbol)}
                          title={`${element.name} (${element.symbol})`}
                        >
                          <span className="element-card-number">{element.number}</span>
                          <span className="element-card-mass">{element.mass}</span>
                          <span className="element-card-symbol">{element.symbol}</span>
                          <span className="element-card-name">{element.name}</span>
                        </button>
                      );
                    })}
                    <div className="series-placeholder lanthanide" style={{ gridColumn: 3, gridRow: 6 }}>
                      57-71
                    </div>
                    <div className="series-placeholder actinide" style={{ gridColumn: 3, gridRow: 7 }}>
                      89-103
                    </div>
                  </div>
                </div>
                <p className="status">拖拽元素到右侧固定栏，或点击元素直接加入。</p>
              </div>
            ) : null}

            {activeTab === 'detail' ? (
              <section className="panel" style={{ marginTop: 12 }}>
                <h3>详细数据（由右侧元素栏驱动）</h3>
                <p>当前组合：{elementFormula || '未选择元素'}</p>
                <label className="field" style={{ maxWidth: 420 }}>
                  筛选检索结果（与右侧固定栏同步）
                  <input
                    type="search"
                    value={materialPickerQuery}
                    onChange={(e) => setMaterialPickerQuery(e.target.value)}
                    placeholder="按元素、化学式、材料 ID 过滤…"
                    disabled={searchCards.length === 0}
                  />
                </label>
                {searchEmptyText ? <p className="status">{searchEmptyText}</p> : null}
                {visibleSearchCards.length === 0 && searchCards.length > 0 ? (
                  <p className="status">没有符合筛选条件的结果，请调整关键字。</p>
                ) : null}
                {visibleSearchCards.length > 0 ? (
                  <div className="search-card-list">
                    {visibleSearchCards.map((card) => (
                      <article className="search-card" key={card.id}>
                        <div className="search-card-title">
                          <div>
                            <strong>{card.title}</strong>
                            {card.subtitle ? <div className="search-card-sub">{card.subtitle}</div> : null}
                          </div>
                          <span className="search-card-tag">{card.tag}</span>
                        </div>
                        <div className="search-card-fields">
                          {card.fields.map((field) => (
                            <div className="search-kv" key={`${card.id}-${field.key}`}>
                              <span className="search-k">{field.key}</span>
                              <span className="search-v">{field.value}</span>
                            </div>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : searchCards.length === 0 ? (
                  <p className="status">请先在右侧拖入元素并完成检索。</p>
                ) : null}
              </section>
            ) : null}

            {activeTab === 'terminal' ? (
              <>
                <section className="viz-terminal-page panel">
                  <div className="viz-terminal-layout">
                    <aside className="viz-terminal-col viz-terminal-servers">
                      <div className="viz-terminal-col-head">服务器</div>
                      <div className="viz-terminal-server-list">
                        {servers.map((server) => {
                          const reach = serverReachability[server.id] ?? { status: 'checking' as ReachabilityStatus, label: '检测中' };
                          const dotClass =
                            reach.status === 'online' ? 'online' : reach.status === 'checking' ? 'checking' : 'offline';
                          return (
                            <button
                              key={server.id}
                              type="button"
                              className={`viz-terminal-server-card ${selectedServerId === server.id ? 'is-active' : ''}`}
                              onClick={() => selectServerAndOpenTerminal(server)}
                            >
                              <span className={`viz-terminal-server-dot ${dotClass}`} aria-hidden />
                              <div className="viz-terminal-server-text">
                                <div className="viz-terminal-server-title">{server.name}</div>
                                <div className="viz-terminal-server-sub">
                                  公网 · {server.username}@{server.host}
                                </div>
                                <div className="viz-terminal-server-meta">{reach.label}</div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                      <div className="viz-terminal-server-actions">
                        <button type="button" className="viz-terminal-btn-add" onClick={() => setShowServerConfig(true)}>
                          添加服务器
                        </button>
                        <button type="button" className="btn secondary" onClick={() => setShowServerConfig((v) => !v)}>
                          编辑
                        </button>
                        <button type="button" className="btn secondary viz-terminal-btn-danger-text" onClick={deleteCurrentServerProfile}>
                          删除
                        </button>
                      </div>
                      {showServerConfig ? (
                        <div className="viz-terminal-server-form">
                          <label className="field">
                            主机
                            <input value={host} onChange={(e) => setHost(e.target.value)} />
                          </label>
                          <label className="field">
                            端口
                            <input type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} />
                          </label>
                          <label className="field">
                            用户名
                            <input value={username} onChange={(e) => setUsername(e.target.value)} />
                          </label>
                          <label className="field">
                            登录密码
                            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="可选" />
                          </label>
                          <button className="btn secondary" onClick={updateCurrentServerProfile}>更新当前服务器</button>
                          <button className="btn secondary" onClick={deleteCurrentServerProfile}>删除当前服务器</button>
                          <label className="field">
                            新服务器名称
                            <input value={newServerName} onChange={(e) => setNewServerName(e.target.value)} placeholder="如: 计算节点 A" />
                          </label>
                          <label className="field">
                            新服务器主机
                            <input value={newServerHost} onChange={(e) => setNewServerHost(e.target.value)} placeholder="10.0.0.12" />
                          </label>
                          <label className="field">
                            端口
                            <input type="number" value={newServerPort} onChange={(e) => setNewServerPort(Number(e.target.value))} />
                          </label>
                          <label className="field">
                            用户名
                            <input value={newServerUsername} onChange={(e) => setNewServerUsername(e.target.value)} placeholder="ubuntu" />
                          </label>
                          <label className="field">
                            登录密码
                            <input type="password" value={newServerPassword} onChange={(e) => setNewServerPassword(e.target.value)} placeholder="可选" />
                          </label>
                          <button className="btn" onClick={addServerProfile}>新建/添加服务器</button>
                        </div>
                      ) : null}
                    </aside>

                    <div className="viz-terminal-col viz-terminal-sftp">
                      <div className="viz-terminal-col-head">远程文件 (SFTP)</div>
                      <div className="viz-terminal-sftp-meta">
                        <span>协议: SSH / SFTP</span>
                        <span className="viz-terminal-sftp-sep">·</span>
                        <span>连接方式: 公网主机</span>
                      </div>
                      <div className="viz-terminal-sftp-toolbar">
                        <button type="button" className="btn secondary" onClick={() => void checkReachable()}>
                          诊断
                        </button>
                        <button type="button" className="btn secondary" onClick={() => requestRemoteList(remoteCwd)} disabled={!canSend}>
                          刷新
                        </button>
                        <button type="button" className="btn secondary" onClick={mkdirRemoteFolder} disabled={!canSend}>
                          新建文件夹
                        </button>
                      </div>
                      <div className="viz-terminal-path-row">
                        <button
                          type="button"
                          className="btn secondary"
                          onClick={() => requestRemoteList(getParentPosixPath(remoteCwd))}
                          disabled={!canSend}
                        >
                          ↑ 上级
                        </button>
                        <span className="viz-terminal-path-text">{remoteCwd}</span>
                      </div>
                      <div
                        className="viz-terminal-table-wrap"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault();
                          Array.from(e.dataTransfer.files ?? []).forEach((file) => {
                            void uploadFileToRemote(file);
                          });
                        }}
                      >
                        <table className="viz-terminal-file-table">
                          <thead>
                            <tr>
                              <th>名称</th>
                              <th>大小</th>
                              <th>操作</th>
                            </tr>
                          </thead>
                          <tbody>
                            {remoteEntries.length === 0 ? (
                              <tr>
                                <td colSpan={3} className="viz-terminal-file-empty">
                                  连接后将显示服务器文件
                                </td>
                              </tr>
                            ) : (
                              remoteEntries.map((entry) => (
                                <tr
                                  key={entry.name}
                                  className={selectedRemoteName === entry.name ? 'is-selected' : ''}
                                  onClick={() => setSelectedRemoteName(entry.name)}
                                  onDoubleClick={() => {
                                    if (entry.kind === 'd') {
                                      requestRemoteList(joinPosixPath(remoteCwd, entry.name));
                                    } else {
                                      requestDownloadFromRemote(joinPosixPath(remoteCwd, entry.name));
                                    }
                                  }}
                                >
                                  <td className="viz-terminal-file-name">
                                    {entry.kind === 'd' ? '📁 ' : '📄 '}
                                    {entry.name}
                                  </td>
                                  <td>{entry.kind === 'f' ? formatBytes(entry.size) : '—'}</td>
                                  <td className="viz-terminal-file-ops">
                                    <button
                                      type="button"
                                      className="viz-terminal-file-action"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        void copyRemotePathToClipboard(entry);
                                      }}
                                    >
                                      复制路径
                                    </button>
                                    <button
                                      type="button"
                                      className="viz-terminal-file-action danger"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        deleteRemoteEntry(entry);
                                      }}
                                    >
                                      删除
                                    </button>
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                      <p className="viz-terminal-sftp-hint">{transferStatus || '拖拽文件到上方列表区域上传'}</p>
                      {uploadQueue.length > 0 ? (
                        <div className="viz-terminal-upload-queue">
                          {uploadQueue.slice(-4).map((item) => (
                            <div key={item.id}>
                              {item.name} · {item.progress}% · {item.status}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>

                    <div className="viz-terminal-col viz-terminal-console">
                      <div className="viz-terminal-console-tabs">
                        <span className="viz-terminal-console-tabs-static">终端</span>
                        {terminalSessions.map((session) => (
                          <div
                            key={session.id}
                            className={`viz-terminal-console-tab ${session.id === activeTerminalSessionId ? 'is-active' : ''}`}
                            role="presentation"
                          >
                            <button type="button" className="viz-terminal-console-tab-main" onClick={() => switchTerminalSession(session.id)}>
                              {session.name}
                            </button>
                            <button
                              type="button"
                              className="viz-terminal-console-tab-x"
                              title="关闭会话"
                              onClick={(e) => {
                                e.stopPropagation();
                                removeTerminalSession(session.id);
                              }}
                            >
                              ×
                            </button>
                          </div>
                        ))}
                        <button type="button" className="viz-terminal-console-tab-new" onClick={() => createTerminalSession()}>
                          + 新建
                        </button>
                      </div>
                      <div className="viz-terminal-console-subbar">
                        <span className="viz-terminal-console-cwd">终端 · {remoteCwd}</span>
                        <button type="button" className="viz-terminal-console-close" onClick={disconnectTerminal}>
                          关闭
                        </button>
                      </div>
                      <div className="viz-terminal-console-body">
                        <div
                          className="terminal-shell terminal-shell-live viz-terminal-xterm-host"
                          ref={terminalMountRef}
                          onClick={() => xtermRef.current?.focus()}
                        />
                      </div>
                    </div>
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'input' ? (
              <section className="panel" style={{ marginTop: 12 }}>
                <h3>数据输入申请（page4）</h3>
                <p>按键值对填写数据后提交，管理员在审核页通过后写入数据库。当前登录用户：{auth.username || '未登录'}</p>
                <div className="input-kv-list">
                  {inputRows.map((row) => (
                    <div className="input-kv-row" key={row.id}>
                      <input
                        placeholder="字段名（如 material_name）"
                        value={row.key}
                        onChange={(e) => updateInputRow(row.id, 'key', e.target.value)}
                      />
                      <input
                        placeholder="字段值（如 NbU3）"
                        value={row.value}
                        onChange={(e) => updateInputRow(row.id, 'value', e.target.value)}
                      />
                      <button className="btn secondary" onClick={() => removeInputRow(row.id)} disabled={inputRows.length === 1}>
                        删除
                      </button>
                    </div>
                  ))}
                </div>
                <div className="row" style={{ marginTop: 10 }}>
                  <button className="btn secondary" onClick={addInputRow}>
                    添加一行
                  </button>
                  <button className="btn" onClick={submitDataInputApplication}>
                    提交申请
                  </button>
                  <button className="btn secondary" onClick={loadMyApplications}>
                    刷新我的申请
                  </button>
                </div>
                <p className="status">{submitStatus || (loadingApplications ? '正在加载申请列表...' : '')}</p>
                <div className="app-list">
                  {myApplications.length === 0 ? (
                    <p className="status">暂无申请记录</p>
                  ) : (
                    myApplications.map((item) => {
                      const statusMap: Record<string, string> = {
                        pending: '待管理员审核',
                        approved: '已通过',
                        rejected: '已拒绝',
                      };
                      return (
                        <div className="app-item" key={item.id}>
                          <span>{item.created_at || item.id}</span>
                          <span className={`app-status app-status-${item.status}`}>{statusMap[item.status] || item.status}</span>
                        </div>
                      );
                    })
                  )}
                </div>
              </section>
            ) : null}

          </div>
          </div>

          <aside className="viz-legacy-sec-box2">
            <div className="viz-sidebar">
            <h3>固定数据栏</h3>
            <p>此栏不随次级页签切换。拖入元素后检索并选择数据源。</p>
            <div
              className={`sidebar-dropzone ${droppedSymbols.length > 0 ? 'sidebar-dropzone-filled' : ''}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const symbol = e.dataTransfer.getData('text/plain');
                if (symbol) {
                  addDroppedSymbol(symbol);
                }
              }}
            >
              {droppedSymbols.length === 0 ? (
                <span className="status">拖拽元素到这里</span>
              ) : (
                <div className="dropped-element-list">
                  {droppedSymbols.map((symbol) => {
                    const element = elementBySymbol.get(symbol);
                    const category = element ? getElementCategory(element.number, element.symbol) : 'unknown';
                    return (
                      <button
                        key={symbol}
                        className={`dropped-element-card category-${category}`}
                        onClick={() => removeDroppedSymbol(symbol)}
                        title={`点击移除 ${element?.name ?? symbol}`}
                      >
                        {element ? (
                          <>
                            <span className="dropped-element-number">{element.number}</span>
                            <span className="dropped-element-mass">{element.mass}</span>
                            <span className="dropped-element-symbol">{element.symbol}</span>
                            <span className="dropped-element-name">{element.name}</span>
                          </>
                        ) : (
                          <span className="dropped-element-symbol">{symbol}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn secondary" onClick={clearDroppedSymbols}>
                清空元素
              </button>
              <button className="btn" onClick={fetchBarMaterials} disabled={!elementFormula}>
                检索
              </button>
            </div>
            <p className="status">当前组合：{elementFormula || '无'}</p>

            <label className="field">
              数据源
              <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}>
                <option value="all">全部</option>
                <option value="local">本地数据库</option>
                <option value="mp">MP-API</option>
              </select>
            </label>
            <label className="field">
              筛选材料
              <input
                type="search"
                value={materialPickerQuery}
                onChange={(e) => setMaterialPickerQuery(e.target.value)}
                placeholder="元素、化学式、mp-id…"
                disabled={filteredMaterials.length === 0}
              />
            </label>
            <label className="field">
              选择数据
              <select
                value={selectedMaterialId}
                onChange={(e) => setSelectedMaterialId(e.target.value)}
                disabled={filteredMaterials.length === 0}
              >
                <option value="">选择材料...</option>
                {pickerMaterials.map((item) => (
                  <option key={item.id} value={item.id}>
                    {buildMaterialPickerLabel(item)}
                  </option>
                ))}
              </select>
            </label>
            <div className="sidebar-metrics">
              <h4>可视化数据</h4>
              {selectedCoreMetrics ? (
                <>
                  <div className="search-kv"><span className="search-k">材料 ID</span><span className="search-v">{selectedCoreMetrics.listingId}</span></div>
                  {selectedCoreMetrics.elementsSummary ? (
                    <div className="search-kv"><span className="search-k">元素组成</span><span className="search-v">{selectedCoreMetrics.elementsSummary}</span></div>
                  ) : null}
                  {selectedCoreMetrics.formulaPretty ? (
                    <div className="search-kv"><span className="search-k">化学式</span><span className="search-v">{selectedCoreMetrics.formulaPretty}</span></div>
                  ) : null}
                  <div className="search-kv"><span className="search-k">数据来源</span><span className="search-v">{selectedCoreMetrics.source}</span></div>
                  <div className="search-kv"><span className="search-k">晶体结构</span><span className="search-v">{selectedCoreMetrics.structure}</span></div>
                  <div className="search-kv"><span className="search-k">晶格常数</span><span className="search-v">{selectedCoreMetrics.latticeText}</span></div>
                  <div className="search-kv"><span className="search-k">弹性常数 C11</span><span className="search-v">{selectedCoreMetrics.c11}</span></div>
                  <div className="search-kv"><span className="search-k">弹性常数 C12</span><span className="search-v">{selectedCoreMetrics.c12}</span></div>
                  <div className="search-kv"><span className="search-k">杨氏模量 E-H</span><span className="search-v">{selectedCoreMetrics.young}</span></div>
                </>
              ) : (
                <p className="status">请选择材料后显示关键可视化数据</p>
              )}
              <button className="btn secondary" onClick={generateSidebarLattice} disabled={!selectedMaterial} style={{ marginTop: 8 }}>
                生成原胞图像
              </button>
              <div className="sidebar-lattice-canvas" ref={sidebarLatticeRef} />
              {sidebarLatticeStatus ? <p className="status">{sidebarLatticeStatus}</p> : null}
            </div>
            <div className="sidebar-properties">
              {selectedMaterialFields.length === 0 ? (
                <p className="status">请选择数据后显示属性</p>
              ) : (
                selectedMaterialFields.map((field) => (
                  <div className="search-kv" key={`sb-${field.key}`}>
                    <span className="search-k">{field.key}</span>
                    <span className="search-v">{field.value}</span>
                  </div>
                ))
              )}
            </div>
            </div>
          </aside>
        </div>
        <p className="status">{status}</p>
      </section>
    </>
  );
}
