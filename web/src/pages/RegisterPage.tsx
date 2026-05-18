import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { rustApi } from '../api/rustApi';

export function RegisterPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');

  async function handleRegister() {
    if (!username.trim() || !password.trim() || !email.trim()) {
      setMessage('请填写完整信息');
      return;
    }
    try {
      const resp = await rustApi.register({ username: username.trim(), password, email: email.trim() });
      setMessage(resp.message || (resp.success ? '注册成功' : '注册失败'));
      if (resp.success) {
        setTimeout(() => navigate('/login'), 900);
      }
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  return (
    <section className="panel">
      <h2>注册</h2>
      <div className="row">
        <label className="field">
          用户名
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          密码
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className="field">
          邮箱
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
      </div>
      <button className="btn" onClick={handleRegister}>
        注册
      </button>
      <p style={{ marginTop: 10 }}>
        已有账号？<Link to="/login">去登录</Link>
      </p>
      <p className="status">{message}</p>
    </section>
  );
}
