import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { rustApi } from '../api/rustApi';
import { setAuthState } from '../auth/authStore';

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');

  async function handleLogin() {
    if (!username.trim() || !password.trim()) {
      setMessage('请填写用户名和密码');
      return;
    }
    try {
      const resp = await rustApi.login({ username: username.trim(), password });
      if (resp.success) {
        setAuthState(username.trim());
        setMessage('登录成功');
        navigate('/');
        return;
      }
      setMessage(resp.message || '登录失败');
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  return (
    <section className="panel">
      <h2>登录</h2>
      <div className="row">
        <label className="field">
          用户名
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          密码
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
      </div>
      <button className="btn" onClick={handleLogin}>
        登录
      </button>
      <p style={{ marginTop: 10 }}>
        没有账号？<Link to="/register">去注册</Link>
      </p>
      <p className="status">{message}</p>
    </section>
  );
}
