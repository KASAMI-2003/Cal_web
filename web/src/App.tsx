import type { ReactElement } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { HomePage } from './pages/HomePage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ProfilePage } from './pages/ProfilePage';
import { AdminPage } from './pages/AdminPage';
import { DataInputPage } from './pages/DataInputPage';
import { DataFittingPage } from './pages/DataFittingPage';
import { VisualizationPage } from './pages/VisualizationPage';
import { DigitalTwinPage } from './pages/DigitalTwinPage';
import { getAuthState } from './auth/authStore';
import { MP_API_BLOCKED_NOTICE_TEXT, SHOW_MP_API_BLOCKED_NOTICE } from './config/opsNotice';

const publicRoutes = new Set(['/login', '/register', '/']);

function ProtectedLayout({ children }: { children: ReactElement }) {
  const location = useLocation();
  const auth = getAuthState();
  if (!auth.isLoggedIn && !publicRoutes.has(location.pathname)) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function TopNav() {
  const navigate = useNavigate();
  const auth = getAuthState();

  function goMine() {
    if (auth.isLoggedIn) {
      navigate('/profile');
      return;
    }
    navigate('/login');
  }

  return (
    <nav className="site-header-nav" id="top">
      <ul className="site-header-nav__list">
        <li className="site-header-nav__item site-header-nav__logo">
          <NavLink to="/" className="site-header-nav__link">
            <img src="/img/logol.png" alt="首页" className="site-header-nav__logo-img" height="40" />
          </NavLink>
        </li>
        <li className="site-header-nav__item">
          <NavLink to="/" className={({ isActive }) => `site-header-nav__link${isActive ? ' site-header-nav__link--active' : ''}`}>
            首页
          </NavLink>
        </li>
        <li className="site-header-nav__item">
          <NavLink
            to="/data-fitting"
            className={({ isActive }) => `site-header-nav__link${isActive ? ' site-header-nav__link--active' : ''}`}
          >
            数据拟合
          </NavLink>
        </li>
        <li className="site-header-nav__item">
          <NavLink
            to="/visualization"
            className={({ isActive }) => `site-header-nav__link${isActive ? ' site-header-nav__link--active' : ''}`}
          >
            可视化网页
          </NavLink>
        </li>
        <li className="site-header-nav__item">
          <NavLink
            to="/digital-twin"
            className={({ isActive }) => `site-header-nav__link${isActive ? ' site-header-nav__link--active' : ''}`}
          >
            弹性孪生可视化
          </NavLink>
        </li>
        <li className="site-header-nav__item dropdown">
          <a href="#" className="site-header-nav__link">
            联系我们
          </a>
          <div className="dropdown-content">
            <div className="contact-item"><i>📞</i><span>电话：</span></div>
            <div className="contact-item"><i>📧</i><span>邮箱：</span></div>
            <div className="contact-item"><i>📍</i><span>地址：</span></div>
          </div>
        </li>
        <li className="site-header-nav__item site-header-nav__item--mine">
          <a
            href="#"
            className="site-header-nav__link"
            onClick={(e) => {
              e.preventDefault();
              goMine();
            }}
          >
            我的
          </a>
        </li>
      </ul>
    </nav>
  );
}

function SiteOpsNotice() {
  if (!SHOW_MP_API_BLOCKED_NOTICE) {
    return null;
  }
  return (
    <div className="site-ops-notice" role="status">
      {MP_API_BLOCKED_NOTICE_TEXT}
    </div>
  );
}

export function App() {
  return (
    <div className={`app-shell${SHOW_MP_API_BLOCKED_NOTICE ? ' app-shell--ops-notice' : ''}`}>
      <TopNav />
      <SiteOpsNotice />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/profile"
            element={
              <ProtectedLayout>
                <ProfilePage />
              </ProtectedLayout>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedLayout>
                <AdminPage />
              </ProtectedLayout>
            }
          />
          <Route
            path="/data-input"
            element={
              <ProtectedLayout>
                <DataInputPage />
              </ProtectedLayout>
            }
          />
          <Route
            path="/data-fitting"
            element={
              <ProtectedLayout>
                <DataFittingPage />
              </ProtectedLayout>
            }
          />
          <Route path="/digital-twin" element={<DigitalTwinPage />} />
          <Route
            path="/visualization"
            element={
              <ProtectedLayout>
                <VisualizationPage />
              </ProtectedLayout>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
