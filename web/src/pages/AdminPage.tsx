import { useCallback, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { pythonApi } from '../api/pythonApi';
import { getAuthState } from '../auth/authStore';
import type { DataInputApplication } from '../types/contracts';

function formatDbPreview(data: Record<string, unknown> | undefined) {
  if (!data) return null;
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== '');
  if (entries.length === 0) return null;
  return (
    <dl className="vasp-db-preview">
      {entries.map(([key, value]) => (
        <div key={key} className="vasp-db-preview-row">
          <dt>{key}</dt>
          <dd>{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function AdminPage() {
  const auth = getAuthState();
  const [items, setItems] = useState<DataInputApplication[]>([]);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [targetDbById, setTargetDbById] = useState<Record<string, 'element_inf' | 'materials'>>({});

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await pythonApi.pendingDataInputs();
      if (data.success === false) {
        setStatus(data.message || '加载待审核列表失败');
        setItems([]);
        return;
      }
      setItems(data.data ?? []);
      setStatus(
        (data.data?.length ?? 0) > 0
          ? `共 ${data.data!.length} 条待审核`
          : '当前无待审核申请（VASP 入库须去掉 --dry-run 并成功 POST 到 pyserver）',
      );
    } catch (error) {
      setItems([]);
      setStatus(
        `无法加载待审核列表：${(error as Error).message}。请确认 pyserver 已启动且前端 VITE_PYTHON_API_ORIGIN 或 Nginx 已反代 /data_input/*`,
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function review(id: string, action: 'approve' | 'reject') {
    try {
      const item = items.find((i) => i.id === id);
      const defaultDb =
        item?.suggested_target_db ?? (item?.source_type === 'vasp_import' ? 'element_inf' : 'materials');
      const targetDb = targetDbById[id] ?? defaultDb;
      const payload =
        action === 'approve'
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
      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>管理员审核</h2>
        <button type="button" className="btn secondary" onClick={() => void reload()} disabled={loading}>
          {loading ? '刷新中…' : '刷新列表'}
        </button>
      </div>
      <p className="status">{status}</p>

      {items.length === 0 && !loading ? (
        <div className="panel vasp-stability">
          <p>
            暂无待审核记录。若终端已显示 Born/Mouhat 通过，请确认：
          </p>
          <ul>
            <li>使用的是<strong>提交审核</strong>按钮，而不是「仅检验（--dry-run）」</li>
            <li>终端输出含 <code>已提交管理员审核，申请 ID: …</code></li>
            <li>
              服务器 <code>server/data_input_applications.json</code> 已写入（与 pyserver 同机、同实例）
            </li>
          </ul>
        </div>
      ) : null}

      {items.map((item) => {
        const defaultDb =
          item.suggested_target_db ?? (item.source_type === 'vasp_import' ? 'element_inf' : 'materials');
        const selectedDb = targetDbById[item.id] ?? defaultDb;
        const calcMeta = item.calc_meta as Record<string, unknown> | undefined;
        return (
          <div className="panel" key={item.id}>
            <strong>
              申请 ID: {item.id} | 用户: {item.username} | 提交: {item.created_at}
              {item.source_type === 'vasp_import' ? ' | VASP 入库' : ''}
              {item.method ? ` | ${item.method}` : ''}
            </strong>
            {calcMeta?.work_dir ? (
              <p className="mono" style={{ marginTop: 8 }}>
                工作目录: {String(calcMeta.work_dir)}
                {calcMeta.source_file ? ` | 源: ${String(calcMeta.source_file)}` : ''}
              </p>
            ) : null}
            {item.stability ? (
              <div className={`vasp-stability ${item.stability.passed ? 'is-pass' : 'is-fail'}`}>
                <strong>稳定性（Born/Mouhat）：{item.stability.passed ? '通过' : '未通过'}</strong>
                <ul>
                  {item.stability.checks.map((c) => (
                    <li key={c.id}>
                      {c.expr.replace('\u2212', '-').replace('\u00b2', '^2')} → {c.value}{' '}
                      {c.passed ? '✓' : '✗'}
                    </li>
                  ))}
                </ul>
                {item.stability.messages?.length ? (
                  <p className="status">{item.stability.messages.join('；')}</p>
                ) : null}
              </div>
            ) : null}
            {item.cij ? <p className="mono">Cij (GPa): {JSON.stringify(item.cij)}</p> : null}
            {item.moduli ? <p className="mono">多晶模量: {JSON.stringify(item.moduli)}</p> : null}
            <h4 style={{ marginBottom: 8 }}>待写入字段</h4>
            {formatDbPreview(item.data as Record<string, unknown>)}
            <details style={{ marginTop: 8 }}>
              <summary className="mono">原始 JSON</summary>
              <pre className="mono">{JSON.stringify(item.data, null, 2)}</pre>
            </details>
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
              <button type="button" className="btn" onClick={() => review(item.id, 'approve')}>
                通过并写入
              </button>
              <button type="button" className="btn secondary" onClick={() => review(item.id, 'reject')}>
                驳回
              </button>
            </div>
          </div>
        );
      })}
    </section>
  );
}
