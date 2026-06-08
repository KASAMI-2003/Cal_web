import { useCallback, useEffect, useState } from 'react';
import { pythonApi } from '../api/pythonApi';
import { getAuthState } from '../auth/authStore';
import type { DataInputApplication } from '../types/contracts';

interface InputKvRow {
  id: string;
  key: string;
  value: string;
}

type InputMode = 'form' | 'json';

interface DataInputPanelProps {
  /** 面板标题，默认「数据录入」 */
  title?: string;
  /** 是否显示说明段落 */
  showIntro?: boolean;
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待管理员审核',
  approved: '已通过',
  rejected: '已拒绝',
};

export function DataInputPanel({ title = '数据录入', showIntro = true }: DataInputPanelProps) {
  const auth = getAuthState();
  const [mode, setMode] = useState<InputMode>('form');
  const [inputRows, setInputRows] = useState<InputKvRow[]>([{ id: crypto.randomUUID(), key: '', value: '' }]);
  const [jsonPayload, setJsonPayload] = useState(
    JSON.stringify(
      {
        元素: 'Al',
        备注: '平台录入功能测试-单元素',
        晶体结构: 'fcc',
        晶格常数: '4.05',
        晶格常数数据来源: 'VASP 静态计算 / 测试用',
        k取值: '0.15',
        etmx: '0.03',
        '杨氏模量E-H': '72.5',
        体积模量B_H: '76.2',
        泊松比nu_H: '0.35',
        弹性刚度常数C11: '108.2',
        C12: '60.1',
        C44: '28.3',
      },
      null,
      2,
    ),
  );
  const [submitStatus, setSubmitStatus] = useState('');
  const [myApplications, setMyApplications] = useState<DataInputApplication[]>([]);
  const [loadingApplications, setLoadingApplications] = useState(false);

  const loadMyApplications = useCallback(async () => {
    if (!auth.username) {
      setMyApplications([]);
      return;
    }
    try {
      setLoadingApplications(true);
      const response = await pythonApi.myDataInputs(auth.username);
      setMyApplications(response.data ?? []);
    } catch {
      // 刷新失败时保留已有列表
    } finally {
      setLoadingApplications(false);
    }
  }, [auth.username]);

  useEffect(() => {
    void loadMyApplications();
  }, [loadMyApplications]);

  function addInputRow() {
    setInputRows((prev) => [...prev, { id: crypto.randomUUID(), key: '', value: '' }]);
  }

  function removeInputRow(id: string) {
    setInputRows((prev) => (prev.length > 1 ? prev.filter((row) => row.id !== id) : prev));
  }

  function updateInputRow(id: string, field: 'key' | 'value', value: string) {
    setInputRows((prev) => prev.map((row) => (row.id === id ? { ...row, [field]: value } : row)));
  }

  function buildFormPayload(): Record<string, unknown> | null {
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
      return null;
    }
    return payload;
  }

  function buildJsonPayload(): Record<string, unknown> | null {
    try {
      const data = JSON.parse(jsonPayload) as unknown;
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        setSubmitStatus('JSON 须为对象，例如 {"元素":"Nb","晶体结构":"bcc"}');
        return null;
      }
      return data as Record<string, unknown>;
    } catch {
      setSubmitStatus('JSON 格式无效，请检查括号与引号');
      return null;
    }
  }

  async function handleSubmit() {
    if (!auth.username) {
      setSubmitStatus('请先登录');
      return;
    }
    const payload = mode === 'form' ? buildFormPayload() : buildJsonPayload();
    if (!payload) return;

    try {
      const response = await pythonApi.submitDataInput({ username: auth.username, data: payload });
      setSubmitStatus(response.success ? '提交成功，请等待管理员审核。' : response.message);
      if (response.success) {
        if (mode === 'form') {
          setInputRows([{ id: crypto.randomUUID(), key: '', value: '' }]);
        }
        await loadMyApplications();
      }
    } catch (error) {
      setSubmitStatus(`提交失败: ${(error as Error).message}`);
    }
  }

  return (
    <div className="data-input-panel">
      <h2>{title}</h2>
      {showIntro ? (
        <p className="data-input-intro">
          提交材料或元素属性变更申请，管理员审核通过后写入数据库。当前用户：{auth.username || '未登录'}
        </p>
      ) : null}

      <div className="data-input-mode-tabs" role="tablist" aria-label="录入方式">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'form'}
          className={`data-input-mode-tab${mode === 'form' ? ' is-active' : ''}`}
          onClick={() => setMode('form')}
        >
          表单录入
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'json'}
          className={`data-input-mode-tab${mode === 'json' ? ' is-active' : ''}`}
          onClick={() => setMode('json')}
        >
          JSON 录入
        </button>
      </div>

      {mode === 'form' ? (
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
              <button type="button" className="btn secondary" onClick={() => removeInputRow(row.id)} disabled={inputRows.length === 1}>
                删除
              </button>
            </div>
          ))}
        </div>
      ) : (
        <label className="field data-input-json-field">
          录入 JSON
          <textarea rows={10} value={jsonPayload} onChange={(e) => setJsonPayload(e.target.value)} spellCheck={false} />
        </label>
      )}

      <div className="row data-input-actions">
        {mode === 'form' ? (
          <button type="button" className="btn secondary" onClick={addInputRow}>
            添加一行
          </button>
        ) : null}
        <button type="button" className="btn" onClick={() => void handleSubmit()}>
          提交审核
        </button>
        <button type="button" className="btn secondary" onClick={() => void loadMyApplications()}>
          刷新我的申请
        </button>
      </div>

      <p className="status">{submitStatus || (loadingApplications ? '正在加载申请列表…' : '')}</p>

      <div className="app-list">
        {myApplications.length === 0 ? (
          <p className="status">暂无申请记录</p>
        ) : (
          myApplications.map((item) => (
            <div className="app-item" key={item.id}>
              <span>{item.created_at || item.id}</span>
              <span className={`app-status app-status-${item.status}`}>{STATUS_LABEL[item.status] || item.status}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
