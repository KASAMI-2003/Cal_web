import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { rustApi } from '../api/rustApi';
import { pythonApi } from '../api/pythonApi';
import { clearAuthState, getAuthState } from '../auth/authStore';
import type { DataInputApplication } from '../types/contracts';

export function ProfilePage() {
  const auth = getAuthState();
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState('');
  const [applications, setApplications] = useState<DataInputApplication[]>([]);

  useEffect(() => {
    async function loadProfile() {
      if (!auth.username) {
        return;
      }
      try {
        const [userInfo, myApps] = await Promise.all([
          rustApi.userInfo(auth.username),
          pythonApi.myDataInputs(auth.username),
        ]);
        setEmail(userInfo.user?.email ?? '');
        setPhone(userInfo.user?.phone ?? '');
        setApplications(myApps.data ?? []);
      } catch (error) {
        setMessage((error as Error).message);
      }
    }
    void loadProfile();
  }, [auth.username]);

  async function handleUpdate() {
    if (!auth.username) {
      return;
    }
    try {
      const resp = await rustApi.updateUser({ username: auth.username, email, phone });
      setMessage(resp.message ?? '资料已更新');
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  function handleLogout() {
    clearAuthState();
    window.location.href = '/';
  }

  function handleChangeAccount() {
    clearAuthState();
    window.location.href = '/login';
  }

  return (
    <>
      <section className="panel">
        <h2>个人中心</h2>
        <p>当前用户：{auth.username || '未登录'}</p>
        <div className="row">
          <label className="field">
            邮箱
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">
            手机
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
        </div>
        <div className="row">
          <button className="btn" onClick={handleUpdate}>
            保存资料
          </button>
          <button className="btn secondary" onClick={handleChangeAccount}>
            更改账号
          </button>
          <button className="btn secondary" onClick={handleLogout}>
            退出登录
          </button>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <Link to="/data-input">去填写并提交申请</Link>
          {auth.username === 'admin' ? <Link to="/admin">管理员审核</Link> : null}
        </div>
        <p className="status">{message}</p>
      </section>

      <section className="panel">
        <h3>我的数据录入申请</h3>
        {applications.length === 0 ? (
          <p className="status">暂无申请记录</p>
        ) : (
          <div className="app-list">
            {applications.map((app) => {
              const statusMap: Record<string, string> = {
                pending: '待管理员审核',
                approved: '已通过',
                rejected: '已拒绝',
              };
              const isVasp = app.source_type === 'vasp_import';
              return (
                <div className="app-item" key={app.id}>
                  <span>
                    {app.created_at}
                    {isVasp ? ' · VASP' : ''}
                    {app.id ? ` · ID ${app.id}` : ''}
                  </span>
                  <span className={`app-status app-status-${app.status}`}>
                    {statusMap[app.status] || app.status}
                  </span>
                  {isVasp && app.stability ? (
                    <span className="mono" style={{ fontSize: 12 }}>
                      Born/Mouhat: {app.stability.passed ? '通过' : '未通过'}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
