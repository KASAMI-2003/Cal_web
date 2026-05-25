import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { pythonApi } from '../api/pythonApi';
import { getAuthState } from '../auth/authStore';
import type { DataInputApplication } from '../types/contracts';

export function AdminPage() {
  const auth = getAuthState();
  const [items, setItems] = useState<DataInputApplication[]>([]);
  const [status, setStatus] = useState('');
  const [targetDbById, setTargetDbById] = useState<Record<string, 'element_inf' | 'materials'>>({});

  async function reload() {
    try {
      const data = await pythonApi.pendingDataInputs();
      setItems(data.data ?? []);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  async function review(id: string, action: 'approve' | 'reject') {
    try {
      const item = items.find((i) => i.id === id);
      const defaultDb =
        item?.suggested_target_db ?? (item?.source_type === 'vasp_import' ? 'element_inf' : 'materials');
      const targetDb = targetDbById[id] ?? defaultDb;
      const payload = action === 'approve'
        ? { id, action, admin_user: 'admin' as const, target_db: targetDb }
        : { id, action, admin_user: 'admin' as const };
      const resp = await pythonApi.reviewDataInput(payload);
      setStatus(resp.message);
      await reload();
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  if (auth.username !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return (
    <section className="panel">
      <h2>管理员审核</h2>
      {items.map((item) => {
        const defaultDb =
          item.suggested_target_db ?? (item.source_type === 'vasp_import' ? 'element_inf' : 'materials');
        const selectedDb = targetDbById[item.id] ?? defaultDb;
        return (
        <div className="panel" key={item.id}>
          <strong>
            用户: {item.username} | 提交时间: {item.created_at}
            {item.source_type === 'vasp_import' ? ' | VASP 入库' : ''}
            {item.method ? ` | ${item.method}` : ''}
          </strong>
          {item.stability ? (
            <div className={`vasp-stability ${item.stability.passed ? 'is-pass' : 'is-fail'}`}>
              <strong>稳定性（Born/Mouhat）：{item.stability.passed ? '通过' : '未通过'}</strong>
              <ul>
                {item.stability.checks.map((c) => (
                  <li key={c.id}>
                    {c.expr} → {c.value} {c.passed ? '✓' : '✗'}
                  </li>
                ))}
              </ul>
              {item.stability.messages?.length ? (
                <p className="status">{item.stability.messages.join('；')}</p>
              ) : null}
            </div>
          ) : null}
          {item.cij ? (
            <p className="mono">Cij: {JSON.stringify(item.cij)}</p>
          ) : null}
          {item.moduli ? (
            <p className="mono">模量: {JSON.stringify(item.moduli)}</p>
          ) : null}
          <pre className="mono">{JSON.stringify(item.data, null, 2)}</pre>
          <div className="row">
            <label className="field">
              加入数据库
              <select
                value={selectedDb}
                onChange={(e) =>
                  setTargetDbById((prev) => ({
                    ...prev,
                    [item.id]: e.target.value as 'element_inf' | 'materials',
                  }))
                }
              >
                <option value="element_inf">element_inf（单元素）</option>
                <option value="materials">materials（化合物）</option>
              </select>
            </label>
          </div>
          <div className="row">
            <button className="btn" onClick={() => review(item.id, 'approve')}>
              通过
            </button>
            <button className="btn secondary" onClick={() => review(item.id, 'reject')}>
              驳回
            </button>
          </div>
        </div>
        );
      })}
      <p className="status">{status}</p>
    </section>
  );
}
