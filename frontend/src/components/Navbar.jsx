import React from 'react';
import {
  Eye,
  User,
  Stethoscope,
  ShieldCheck,
  LogOut,
  RefreshCw,
  Calendar,
  Sparkles,
  Menu,
  X
} from 'lucide-react';

export default function Navbar({ user, onLogout, onChangeRole, onToggleSidebar, isSidebarOpen }) {
  const getRoleBadge = (role) => {
    switch (role) {
      case 'patient':
        return (
          <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.12)', color: 'var(--cream-text)', border: '1px solid rgba(244, 237, 224, 0.2)', padding: '0.15rem 0.55rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 500 }}>
            <User size={12} /> Patient
          </span>
        );
      case 'doctor':
        return (
          <span className="badge" style={{ background: 'rgba(244, 237, 224, 0.15)', color: 'var(--cream-text)', border: '1px solid rgba(244, 237, 224, 0.25)', padding: '0.15rem 0.55rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 500 }}>
            <Stethoscope size={12} /> Doctor
          </span>
        );
      case 'staff':
        return (
          <span className="badge badge-warning" style={{ padding: '0.15rem 0.55rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 500 }}>
            <ShieldCheck size={12} /> Staff
          </span>
        );
      default:
        return null;
    }
  };

  const getInitials = (name) => {
    if (!name) return 'U';
    return name.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase();
  };

  return (
    <header style={{
      background: 'var(--navy)',
      borderBottom: '1px solid rgba(244, 237, 224, 0.12)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '0.9rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
      boxShadow: '0 2px 8px rgba(20, 33, 61, 0.15)'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '1.5rem',
        width: '100%',
        maxWidth: '100%'
      }}>
        
        {/* Left: Hamburger Toggle & Brand Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexShrink: 0 }}>
          {user && onToggleSidebar && (
            <button
              onClick={onToggleSidebar}
              className="btn btn-secondary btn-icon"
              style={{
                display: 'inline-flex',
                background: isSidebarOpen ? 'rgba(255, 255, 255, 0.16)' : 'rgba(255, 255, 255, 0.08)',
                color: 'var(--cream-text)',
                borderColor: 'rgba(244, 237, 224, 0.2)',
                borderRadius: '6px'
              }}
              title={isSidebarOpen ? "Slide sidebar closed" : "Slide sidebar open"}
              aria-label="Toggle navigation sidebar"
            >
              <Menu size={18} />
            </button>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              background: 'var(--navy-light)',
              color: 'var(--coral)',
              border: '1px solid rgba(244, 237, 224, 0.15)',
              width: '40px',
              height: '40px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              <Eye size={22} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <h1 style={{
                  fontFamily: 'var(--font-heading)',
                  fontSize: '1.35rem',
                  fontWeight: 700,
                  color: 'var(--cream-text)',
                  letterSpacing: '-0.02em',
                  lineHeight: 1.1,
                  margin: 0
                }}>
                  Netra<span style={{ color: 'var(--coral)' }}>Care</span>
                </h1>
                <span className="badge" style={{
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: 'var(--cream-text)',
                  fontSize: '0.7rem',
                  border: '1px solid rgba(244, 237, 224, 0.2)',
                  padding: '0.1rem 0.45rem',
                  borderRadius: '4px',
                  fontWeight: 500
                }}>
                  Clinical EHR
                </span>
              </div>
              <span className="navbar-subtitle" style={{ fontSize: '0.78rem', color: '#A0ADC0', fontWeight: 400, display: 'block', marginTop: '2px' }}>
                Specialized Eye Care & Clinical Operations
              </span>
            </div>
          </div>
        </div>

        {/* Right: User Profile, Switch Role & Logout */}
        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexShrink: 0 }}>
            {/* User Profile */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.65rem',
              padding: '0.35rem 0.85rem',
              background: 'rgba(255, 255, 255, 0.08)',
              borderRadius: '6px',
              border: '1px solid rgba(244, 237, 224, 0.18)',
              maxWidth: '240px'
            }}>
              <div style={{
                width: '30px',
                height: '30px',
                borderRadius: '4px',
                background: user.role === 'doctor'
                  ? 'var(--navy-light)'
                  : user.role === 'staff'
                  ? '#d97706'
                  : 'var(--navy-light)',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}>
                {getInitials(user.name)}
              </div>
              <div style={{ textAlign: 'left', minWidth: 0, overflow: 'hidden' }}>
                <div style={{
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: 'var(--cream-text)',
                  lineHeight: 1.2,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                }}>
                  {user.name}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginTop: '1px' }}>
                  {getRoleBadge(user.role)}
                </div>
              </div>
            </div>

            <button
              onClick={onChangeRole}
              className="btn btn-secondary btn-sm"
              title="Switch user or clinic role"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.82rem',
                padding: '0.5rem 0.95rem',
                background: 'rgba(255, 255, 255, 0.08)',
                color: 'var(--cream-text)',
                borderColor: 'rgba(244, 237, 224, 0.2)',
                borderRadius: '6px',
                fontWeight: 500
              }}
            >
              <RefreshCw size={13} color="var(--cream-text)" />
              <span className="btn-label-desktop">Switch Role</span>
            </button>

            <button
              onClick={onLogout}
              className="btn btn-danger btn-sm"
              title="Sign Out"
              style={{ padding: '0.5rem 0.85rem', borderRadius: '6px', fontSize: '0.82rem', fontWeight: 500 }}
            >
              <LogOut size={14} />
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span className="badge" style={{
              background: 'rgba(255, 255, 255, 0.12)',
              color: 'var(--cream-text)',
              border: '1px solid rgba(244, 237, 224, 0.2)',
              padding: '0.35rem 0.85rem',
              borderRadius: '4px',
              fontWeight: 500,
              fontSize: '0.82rem'
            }}>
              Ophthalmology Suite
            </span>
          </div>
        )}
      </div>

      <style>{`
        @media (max-width: 768px) {
          .navbar-subtitle {
            display: none !important;
          }
          .btn-label-desktop {
            display: none !important;
          }
        }
      `}</style>
    </header>
  );
}
