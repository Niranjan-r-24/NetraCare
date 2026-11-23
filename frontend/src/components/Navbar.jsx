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
  X,
  Search,
  Bell,
  Download
} from 'lucide-react';

export default function Navbar({ user, onLogout, onChangeRole, onToggleSidebar, isSidebarOpen }) {
  const getRoleBadge = (role) => {
    switch (role) {
      case 'patient':
        return (
          <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.12)', color: 'var(--cream-text)', border: '1px solid rgba(244, 237, 224, 0.2)', padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: '0.7rem' }}>
            <User size={11} /> Patient
          </span>
        );
      case 'doctor':
        return (
          <span className="badge" style={{ background: 'rgba(244, 237, 224, 0.15)', color: 'var(--cream-text)', border: '1px solid rgba(244, 237, 224, 0.25)', padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: '0.7rem' }}>
            <Stethoscope size={11} /> Doctor
          </span>
        );
      case 'staff':
        return (
          <span className="badge badge-warning" style={{ padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: '0.7rem' }}>
            <ShieldCheck size={11} /> Staff
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

  const todayFormatted = new Date().toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric'
  });

  return (
    <header style={{
      background: 'var(--navy)',
      borderBottom: '1px solid rgba(244, 237, 224, 0.12)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '0.75rem 1.5rem',
      width: '100%',
      boxSizing: 'border-box',
      boxShadow: '0 2px 12px -2px rgba(20, 33, 61, 0.35)'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '0.75rem',
        width: '100%',
        maxWidth: '100%'
      }}>
        
        {/* Left: Hamburger Toggle & Brand Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexShrink: 0 }}>
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

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div style={{
              background: 'var(--navy-light)',
              color: 'var(--coral)',
              border: '1px solid rgba(244, 237, 224, 0.15)',
              width: '38px',
              height: '38px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              <Eye size={20} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <h1 style={{
                  fontSize: '1.2rem',
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
                  fontSize: '0.65rem',
                  border: '1px solid rgba(244, 237, 224, 0.2)',
                  padding: '0.1rem 0.45rem',
                  borderRadius: '4px'
                }}>
                  EHR 2.0
                </span>
              </div>
              <span className="navbar-subtitle" style={{ fontSize: '0.72rem', color: '#A0ADC0', fontWeight: 500, display: 'block' }}>
                Specialized Eye Care & Clinical Operations
              </span>
            </div>
          </div>
        </div>

        {/* Center: Search input & Live OPD Badge */}
        <div style={{
          display: 'none',
          alignItems: 'center',
          gap: '0.65rem',
          minWidth: 0
        }} className="desktop-navbar-center">
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            background: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(244, 237, 224, 0.18)',
            borderRadius: '6px',
            padding: '0.4rem 0.85rem',
            fontSize: '0.82rem',
            color: 'var(--cream-text)',
            width: '230px'
          }}>
            <Search size={14} color="#A0ADC0" />
            <input
              type="text"
              placeholder="Search patients, doctors..."
              style={{
                border: 'none',
                background: 'transparent',
                outline: 'none',
                width: '100%',
                fontSize: '0.82rem',
                color: 'var(--cream-text)'
              }}
            />
          </div>

          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.45rem',
            background: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(244, 237, 224, 0.18)',
            borderRadius: '6px',
            padding: '0.35rem 0.75rem',
            fontSize: '0.76rem',
            color: 'var(--cream-text)',
            fontWeight: 500,
            whiteSpace: 'nowrap'
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: 'var(--coral)'
            }} className="pulse" />
            <span>OPD Rule Engine</span>
            <span style={{ color: 'rgba(244, 237, 224, 0.25)' }}>|</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--cream-text)' }}>
              <Calendar size={12} color="var(--cream-text)" /> {todayFormatted}
            </span>
          </div>
        </div>

        {/* Right: Quick Action, User Chip, Switch Role & Logout */}
        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', flexShrink: 0 }}>
            
            {/* Quick Action */}
            <div style={{ display: 'none', alignItems: 'center', gap: '0.5rem' }} className="desktop-export-btn">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{
                  fontSize: '0.78rem',
                  padding: '0.45rem 0.85rem',
                  background: 'rgba(255, 255, 255, 0.08)',
                  color: 'var(--cream-text)',
                  borderColor: 'rgba(244, 237, 224, 0.2)',
                  borderRadius: '6px'
                }}
                onClick={() => alert('Exporting clinic schedule summary...')}
              >
                <Download size={13} color="var(--cream-text)" /> Export CSV
              </button>
            </div>

            {/* Notification bell */}
            <button
              type="button"
              className="btn btn-secondary btn-icon"
              style={{
                width: '34px',
                height: '34px',
                background: 'rgba(255, 255, 255, 0.08)',
                borderColor: 'rgba(244, 237, 224, 0.2)',
                color: 'var(--cream-text)',
                borderRadius: '6px'
              }}
              title="Notifications"
            >
              <Bell size={15} color="var(--cream-text)" />
            </button>

            {/* User Profile */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.55rem',
              padding: '0.3rem 0.65rem',
              background: 'rgba(255, 255, 255, 0.08)',
              borderRadius: '6px',
              border: '1px solid rgba(244, 237, 224, 0.18)',
              maxWidth: '220px'
            }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '4px',
                background: user.role === 'doctor'
                  ? 'var(--navy-light)'
                  : user.role === 'staff'
                  ? '#d97706'
                  : 'var(--navy-light)',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}>
                {getInitials(user.name)}
              </div>
              <div style={{ textAlign: 'left', minWidth: 0, overflow: 'hidden' }}>
                <div style={{
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  color: 'var(--cream-text)',
                  lineHeight: 1.15,
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
                gap: '5px',
                fontSize: '0.78rem',
                padding: '0.45rem 0.85rem',
                background: 'rgba(255, 255, 255, 0.08)',
                color: 'var(--cream-text)',
                borderColor: 'rgba(244, 237, 224, 0.2)',
                borderRadius: '6px'
              }}
            >
              <RefreshCw size={12} color="var(--cream-text)" />
              <span className="btn-label-desktop">Switch Role</span>
            </button>

            <button
              onClick={onLogout}
              className="btn btn-danger btn-sm"
              title="Sign Out"
              style={{ padding: '0.45rem 0.75rem', borderRadius: '6px' }}
            >
              <LogOut size={13} />
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span className="badge" style={{
              background: 'rgba(255, 255, 255, 0.12)',
              color: 'var(--cream-text)',
              border: '1px solid rgba(244, 237, 224, 0.2)',
              padding: '0.3rem 0.75rem',
              borderRadius: '4px',
              fontWeight: 600
            }}>
              Ophthalmology Suite
            </span>
          </div>
        )}
      </div>

      <style>{`
        @media (min-width: 1200px) {
          .desktop-navbar-center {
            display: flex !important;
          }
          .desktop-export-btn {
            display: flex !important;
          }
        }
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
