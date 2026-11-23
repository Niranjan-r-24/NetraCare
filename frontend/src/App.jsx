import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import LoginModal from './components/LoginModal';
import PatientPortal from './components/PatientPortal';
import DoctorDashboard from './components/DoctorDashboard';
import StaffDesk from './components/StaffDesk';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.innerWidth > 1024;
    }
    return true;
  });

  useEffect(() => {
    const saved = localStorage.getItem('netracare_user');
    if (saved) {
      try {
        setCurrentUser(JSON.parse(saved));
      } catch (e) {
        localStorage.removeItem('netracare_user');
      }
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('netracare_user');
    setCurrentUser(null);
  };

  const handleChangeRole = () => {
    localStorage.removeItem('netracare_user');
    setCurrentUser(null);
  };

  return (
    <div className="app-shell-frame">
      <Navbar
        user={currentUser}
        onLogout={handleLogout}
        onChangeRole={handleChangeRole}
        onToggleSidebar={() => setSidebarOpen(prev => !prev)}
        isSidebarOpen={sidebarOpen}
      />

      {!currentUser ? (
        <main style={{ flex: 1, padding: '2rem 0 3.5rem 0' }}>
          <div className="container">
            <LoginModal onLoginSuccess={setCurrentUser} />
          </div>
        </main>
      ) : (
        <div className="dashboard-layout">
          <Sidebar
            user={currentUser}
            onLogout={handleLogout}
            onChangeRole={handleChangeRole}
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />

          <main className="main-content" style={{ padding: '2rem 0 3.5rem 0' }}>
            <div className="dashboard-container">
              {currentUser.role === 'patient' && <PatientPortal user={currentUser} />}
              {currentUser.role === 'doctor' && <DoctorDashboard user={currentUser} />}
              {currentUser.role === 'staff' && <StaffDesk user={currentUser} />}
            </div>
          </main>
        </div>
      )}

      <footer style={{
        borderTop: '1px solid rgba(244, 237, 224, 0.12)',
        background: 'var(--navy)',
        color: 'var(--cream-text)',
        padding: '1.25rem 0',
        fontSize: '0.84rem',
        marginTop: 'auto'
      }}>
        <div className="dashboard-container" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <b style={{ color: 'var(--cream-text)', fontSize: '0.95rem', fontWeight: 600 }}>
              Netra<span style={{ color: 'var(--coral)' }}>Care</span>
            </b>
            <span style={{ color: '#A0ADC0', fontSize: '0.82rem' }}>· Specialized Eye Care & Clinical Operations</span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#A0ADC0' }}>
            Ophthalmic Clinical Health Platform
          </div>
        </div>
      </footer>
    </div>
  );
}
