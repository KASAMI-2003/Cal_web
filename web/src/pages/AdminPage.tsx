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
      const targetDb = targetDbById[id] ?? 'materials';
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
      {items.map((item) => (
        <div className="panel" key={item.id}>
          <strong>
            用户: {item.username} | 提交时间: {item.created_at}
          </strong>
          <pre className="mono">{JSON.stringify(item.data, null, 2)}</pre>
          <div className="row">
            <label className="field">
              加入数据库
              <select
                value={targetDbById[item.id] ?? 'materials'}
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
      ))}
      <p className="status">{status}</p>
    </section>
  );
}
