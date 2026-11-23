import React, { useState } from 'react';
import {
  LayoutDashboard,
  Calendar,
  Clock,
  MessageSquare,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  User,
  Stethoscope,
  Search,
  ChevronRight,
  Eye,
  Activity,
  FileText,
  PhoneCall,
  Sliders,
  X,
  HelpCircle
} from 'lucide-react';

export default function Sidebar({ user, onLogout, onChangeRole, isOpen, onClose }) {
  const [activeItem, setActiveItem] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');

  if (!user) return null;

  const scrollTo = (id, idx) => {
    setActiveItem(idx);
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (window.innerWidth <= 1024 && onClose) {
      onClose();
    }
  };

  const getNavItems = () => {
    if (user.role === 'patient') {
      return [
        { label: 'Ophthalmic Overview', icon: <Eye size={17} />, target: 'section-hero' },
        { label: 'Care Specialities', icon: <Activity size={17} />, target: 'section-services' },
        { label: 'Our Eye Specialists', icon: <Stethoscope size={17} />, target: 'section-doctors' },
        { label: 'Clinical Insights', icon: <Sparkles size={17} />, target: 'section-fact' },
        { label: 'Schedule Consultation', icon: <Calendar size={17} />, target: 'section-booking' },
        { label: 'Your Consultations', icon: <Clock size={17} />, target: 'section-appointments' },
        { label: 'Care Assistant & AI', icon: <MessageSquare size={17} />, target: 'section-chat-launcher', badge: 'Online', badgeColor: 'var(--cream-text)', badgeBg: 'rgba(255, 255, 255, 0.12)' },
        { label: 'Patient FAQs & Help', icon: <HelpCircle size={17} />, target: 'section-faq' },
      ];
    } else if (user.role === 'doctor') {
      return [
        { label: 'Consultation Queue', icon: <LayoutDashboard size={17} />, target: 'section-doctor-queue', badge: 'Live OPD', badgeColor: 'var(--cream-text)', badgeBg: 'rgba(255, 255, 255, 0.12)' },
        { label: 'Patient Arrival Stats', icon: <Activity size={17} />, target: 'section-arrival-stats' },
        { label: 'Weekly OPD Schedule', icon: <Calendar size={17} />, target: 'section-doctor-schedule' },
      ];
    } else if (user.role === 'staff') {
      return [
        { label: 'Clinic Schedule Master', icon: <Calendar size={17} />, target: 'section-staff-table' },
        { label: 'Urgent Care Triage', icon: <AlertTriangle size={17} />, target: 'section-urgent-triage', badge: 'Priority', badgeColor: '#991b1b', badgeBg: '#fee2e2' },
        { label: 'Late Change Approvals', icon: <ShieldCheck size={17} />, target: 'section-approvals', badge: 'Review', badgeColor: '#92400e', badgeBg: '#fef3c7' },
        { label: 'Knowledge Search Debug', icon: <Sliders size={17} />, target: 'section-search-debug' },
      ];
    }
    return [];
  };

  const navItems = getNavItems();

  return (
    <>
      {/* Mobile Drawer Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="sidebar-backdrop"
          aria-hidden="true"
        />
      )}

      <aside
        className={`sidebar ${isOpen ? 'open' : 'collapsed'}`}
        aria-hidden={!isOpen}
      >
        <div style={{ width: '260px', minWidth: '260px', height: '100%', display: 'flex', flexDirection: 'column' }}>
          {/* Brand Banner */}
          <div style={{
            padding: '1.25rem 1.25rem 1rem 1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.85rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
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
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--cream-text)', letterSpacing: '-0.02em', lineHeight: 1.1 }}>
                  Netra<span style={{ color: 'var(--coral)' }}>Care</span>
                </div>
                <span style={{ fontSize: '0.72rem', color: '#9AAAC0', fontWeight: 500 }}>
                  Clinical Platform
                </span>
              </div>
            </div>

            {/* Close button on mobile/tablet */}
            <button
              onClick={onClose}
              className="btn btn-secondary btn-icon mobile-sidebar-close"
              title="Close sidebar"
              style={{ background: 'rgba(255, 255, 255, 0.08)', color: 'var(--cream-text)', borderColor: 'rgba(244, 237, 224, 0.2)', borderRadius: '6px' }}
            >
              <X size={16} />
            </button>
          </div>

          {/* Quick Search Bar in Sidebar */}
          <div style={{ padding: '0.4rem 1.25rem 0.75rem 1.25rem' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(244, 237, 224, 0.14)',
              borderRadius: '6px',
              padding: '0.45rem 0.75rem',
              fontSize: '0.8rem',
              color: 'var(--cream-text)'
            }}>
              <Search size={14} color="#8E9CAE" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search..."
                style={{
                  border: 'none',
                  background: 'transparent',
                  outline: 'none',
                  width: '100%',
                  fontSize: '0.8rem',
                  color: 'var(--cream-text)'
                }}
              />
              <span style={{
                fontSize: '0.68rem',
                background: 'rgba(255, 255, 255, 0.1)',
                padding: '1px 5px',
                borderRadius: '4px',
                color: 'var(--cream-text)',
                fontWeight: 600
              }}>
                ⌘K
              </span>
            </div>
          </div>

          {/* User Identity Chip */}
          <div style={{ padding: '0 1.25rem 0.75rem 1.25rem' }}>
            <div style={{
              background: 'rgba(255, 255, 255, 0.06)',
              borderRadius: '6px',
              padding: '0.75rem 0.85rem',
              border: '1px solid rgba(244, 237, 224, 0.14)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', minWidth: 0 }}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '6px',
                  background: user.role === 'doctor'
                    ? 'rgba(244, 237, 224, 0.15)'
                    : user.role === 'staff'
                    ? '#fef3c7'
                    : 'rgba(255, 255, 255, 0.15)',
                  color: user.role === 'doctor'
                    ? 'var(--cream-text)'
                    : user.role === 'staff'
                    ? '#92400e'
                    : 'var(--cream-text)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  flexShrink: 0
                }}>
                  {user.role === 'doctor' ? <Stethoscope size={16} /> : user.role === 'staff' ? <ShieldCheck size={16} /> : <User size={16} />}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--cream-text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {user.name}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#9AAAC0', textTransform: 'capitalize', fontWeight: 500 }}>
                    {user.role} workspace
                  </div>
                </div>
              </div>
              <span style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: 'var(--coral)',
                flexShrink: 0
              }} className="pulse" />
            </div>
          </div>

          {/* Navigation Section */}
          <div style={{ flex: 1, padding: '0.5rem 0.75rem', overflowY: 'auto' }}>
            <div style={{
              fontSize: '0.68rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: '#7D8C9E',
              padding: '0.4rem 0.65rem'
            }}>
              Navigation
            </div>

            <nav style={{ display: 'grid', gap: '3px' }}>
              {navItems.map((item, idx) => {
                const isActive = activeItem === idx;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => scrollTo(item.target, idx)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.65rem 0.85rem',
                      borderRadius: '6px',
                      color: isActive ? '#FFFFFF' : '#B2BFCF',
                      fontSize: '0.875rem',
                      fontWeight: isActive ? 600 : 500,
                      textAlign: 'left',
                      width: '100%',
                      background: isActive ? 'rgba(255, 255, 255, 0.1)' : 'transparent',
                      borderLeft: isActive ? '3px solid var(--coral)' : '3px solid transparent',
                      transition: 'all 0.15s ease'
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                        e.currentTarget.style.color = 'var(--cream-text)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.background = 'transparent';
                        e.currentTarget.style.color = '#B2BFCF';
                      }
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                      <span style={{ color: isActive ? 'var(--coral)' : '#8E9CAE', flexShrink: 0 }}>
                        {item.icon}
                      </span>
                      <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>
                    </div>
                    {item.badge ? (
                      <span
                        className="badge"
                        style={{
                          background: item.badgeBg || 'rgba(255, 255, 255, 0.1)',
                          color: item.badgeColor || 'var(--cream-text)',
                          fontSize: '0.65rem',
                          padding: '0.12rem 0.45rem',
                          borderRadius: '4px',
                          flexShrink: 0
                        }}
                      >
                        {item.badge}
                      </span>
                    ) : isActive ? (
                      <ChevronRight size={14} color="var(--coral)" style={{ flexShrink: 0 }} />
                    ) : null}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Sidebar Footer info card */}
          <div style={{
            padding: '0.85rem',
            borderTop: '1px solid rgba(244, 237, 224, 0.12)',
            background: 'rgba(0, 0, 0, 0.08)'
          }}>
            <div style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(244, 237, 224, 0.12)',
              borderRadius: '6px',
              padding: '0.75rem',
              fontSize: '0.75rem',
              color: '#B2BFCF'
            }}>
              <div style={{ fontWeight: 600, color: 'var(--cream-text)', marginBottom: '2px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <PhoneCall size={12} color="var(--cream-text)" /> Clinic Emergency Desk
              </div>
              <div>OPD Mon–Sat: 09:00 - 18:00</div>
              <div style={{ color: '#F87171', fontWeight: 600, marginTop: '2px' }}>
                Red Flag Triage: Active 24/7
              </div>
            </div>
          </div>
        </div>
      </aside>

      <style>{`
        @media (max-width: 1024px) {
          .mobile-sidebar-close {
            display: inline-flex !important;
          }
        }
      `}</style>
    </>
  );
}
