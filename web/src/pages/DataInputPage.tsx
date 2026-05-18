import { useState } from 'react';
import { pythonApi } from '../api/pythonApi';
import { getAuthState } from '../auth/authStore';

export function DataInputPage() {
  const auth = getAuthState();
  const [payload, setPayload] = useState('{"元素":"U-Nb","备注":"TSX迁移测试"}');
  const [status, setStatus] = useState('');

  async function handleSubmit() {
    if (!auth.username) {
      setStatus('请先登录');
      return;
    }
    try {
      const data = JSON.parse(payload) as Record<string, unknown>;
      const resp = await pythonApi.submitDataInput({ username: auth.username, data });
      setStatus(resp.message);
    } catch (error) {
      setStatus(`提交失败: ${(error as Error).message}`);
    }
  }

  return (
    <section className="panel">
      <h2>数据录入</h2>
      <label className="field">
        录入 JSON
        <textarea rows={10} value={payload} onChange={(e) => setPayload(e.target.value)} />
      </label>
      <button className="btn" onClick={handleSubmit}>
        提交审核
      </button>
      <p className="status">{status}</p>
    </section>
  );
}
