import React, { useState, useEffect } from 'react';
import { api } from '../api';
import StaffSearchDebug from './StaffSearchDebug';
import {
  ShieldCheck,
  Plus,
  XCircle,
  Search,
  Calendar,
  User,
  Clock,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Check,
  Bot,
  Layers,
  ArrowRight,
  Sparkles,
  Users,
  Activity,
  FileText,
  TrendingUp,
  Download
} from 'lucide-react';

export default function StaffDesk({ user }) {
  const [appointments, setAppointments] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [specialities, setSpecialities] = useState([]);

  // Urgent Cases state (R4)
  const [urgentCases, setUrgentCases] = useState([]);
  const [urgentLoading, setUrgentLoading] = useState(false);

  // Staff Approvals state (Iteration 4 R1)
  const [approvals, setApprovals] = useState([]);
  const [approvalsLoading, setApprovalsLoading] = useState(false);

  // Filters
  const [filterDoctorId, setFilterDoctorId] = useState('');
  const [filterDate, setFilterDate] = useState(() => new Date().toISOString().split('T')[0]);

  // Walk-in booking modal state
  const [showBookingModal, setShowBookingModal] = useState(false);
  const [walkinPatientId, setWalkinPatientId] = useState('');
  const [walkinDoctorId, setWalkinDoctorId] = useState('');
  const [walkinSpeciality, setWalkinSpeciality] = useState('');
  const [walkinVisitType, setWalkinVisitType] = useState('new');
  const [walkinDate, setWalkinDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [walkinSlots, setWalkinSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState('');
  const [walkinReason, setWalkinReason] = useState('');

  // New patient registration in walkin
  const [isNewPatient, setIsNewPatient] = useState(false);
  const [newPatientName, setNewPatientName] = useState('');
  const [newPatientMobile, setNewPatientMobile] = useState('');

  const [msg, setMsg] = useState({ text: '', type: '' });
  const [loading, setLoading] = useState(false);

  const loadUrgentCases = async () => {
    setUrgentLoading(true);
    try {
      const data = await api.getUrgentCases(true);
      setUrgentCases(data);
    } catch (err) {
      console.error('Failed to load urgent cases', err);
    } finally {
      setUrgentLoading(false);
    }
  };

  const loadAppointments = async () => {
    setLoading(true);
    try {
      const data = await api.getAppointments({
        date: filterDate,
        doctor_id: filterDoctorId || undefined
      });
      setAppointments(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadApprovals = async () => {
    setApprovalsLoading(true);
    try {
      const data = await api.getStaffApprovals('pending');
      setApprovals(data);
    } catch (err) {
      console.error('Failed to load staff approvals', err);
    } finally {
      setApprovalsLoading(false);
    }
  };

  const handleApprove = async (id) => {
    try {
      const res = await api.approveStaffRequest(id);
      setMsg({ text: res.message || 'Request approved successfully.', type: 'success' });
      loadApprovals();
      loadAppointments();
    } catch (err) {
      const detail = err.detail || 'Failed to approve request.';
      setMsg({ text: typeof detail === 'string' ? detail : JSON.stringify(detail), type: 'danger' });
    }
  };

  const handleReject = async (id) => {
    try {
      const res = await api.rejectStaffRequest(id);
      setMsg({ text: res.message || 'Request rejected.', type: 'info' });
      loadApprovals();
      loadAppointments();
    } catch (err) {
      const detail = err.detail || 'Failed to reject request.';
      setMsg({ text: typeof detail === 'string' ? detail : JSON.stringify(detail), type: 'danger' });
    }
  };

  useEffect(() => {
    loadUrgentCases();
    loadApprovals();

    api.getDoctors().then(docs => {
      setDoctors(docs);
      if (docs.length > 0) {
        setWalkinDoctorId(docs[0].doctor_id);
      }
    });

    api.getSpecialities().then(specs => {
      setSpecialities(specs);
      if (specs.length > 0) {
        setWalkinSpeciality(specs[0]);
      }
    });
  }, []);

  useEffect(() => {
    loadAppointments();
  }, [filterDate, filterDoctorId]);

  // Load slots for walkin modal
  useEffect(() => {
    if (!walkinDoctorId || !walkinDate) return;
    api.getFreeSlots(walkinDoctorId, walkinDate, walkinVisitType)
      .then(res => setWalkinSlots(res.slots || []))
      .catch(() => setWalkinSlots([]));
  }, [walkinDoctorId, walkinDate, walkinVisitType]);

  const handleMarkSeen = async (caseId) => {
    try {
      await api.markUrgentCaseSeen(caseId);
      setMsg({ text: `Urgent Case #${caseId} marked as seen and removed from triage queue.`, type: 'success' });
      loadUrgentCases();
    } catch (err) {
      setMsg({ text: 'Failed to mark urgent case seen.', type: 'danger' });
    }
  };

  const handleStaffCancel = async (apptId) => {
    if (!window.confirm(`Staff Override: Cancel appointment ${apptId}? (Allowed even within 2 hours)`)) return;
    try {
      await api.cancelAppointment(apptId);
      setMsg({ text: `Appointment ${apptId} successfully cancelled by Staff override.`, type: 'success' });
      loadAppointments();
    } catch (err) {
      const detail = err.detail?.message || err.detail || 'Failed to cancel appointment.';
      setMsg({ text: detail, type: 'danger' });
    }
  };

  const handleWalkinSubmit = async (e) => {
    e.preventDefault();
    setMsg({ text: '', type: '' });

    const cleanReason = walkinReason.trim();
    if (!cleanReason) {
      setMsg({ text: 'Please enter a visit reason (up to 300 characters).', type: 'danger' });
      return;
    }

    try {
      let finalPatientId = walkinPatientId.trim();

      // If new patient, register via auth/login
      if (isNewPatient) {
        if (!newPatientName || !newPatientMobile) {
          setMsg({ text: 'Please enter patient name and mobile number.', type: 'danger' });
          return;
        }
        const patRes = await api.login({
          role: 'patient',
          name: newPatientName.trim(),
          mobile: newPatientMobile.trim()
        });
        finalPatientId = patRes.user_id;
      }

      if (!finalPatientId) {
        setMsg({ text: 'Patient ID is required.', type: 'danger' });
        return;
      }
      if (!selectedSlot) {
        setMsg({ text: 'Please pick an available time slot.', type: 'danger' });
        return;
      }

      const res = await api.createAppointment({
        patient_id: finalPatientId,
        doctor_id: walkinDoctorId,
        speciality: walkinSpeciality,
        visit_type: walkinVisitType,
        date: walkinDate,
        start_time: selectedSlot,
        reason: cleanReason
      });

      let successText = `Walk-in appointment ${res.appointment_id} booked for ${finalPatientId}!`;
      if (res.emergency_message) {
        successText += ` [EMERGENCY RECORDED: Urgent case added to triage list]`;
      }
      setMsg({ text: successText, type: res.is_urgent ? 'danger' : 'success' });
      setShowBookingModal(false);
      setWalkinReason('');
      setSelectedSlot('');
      loadAppointments();
      loadUrgentCases();
    } catch (err) {
      const detail = err.detail;
      let text = 'Booking failed.';
      if (typeof detail === 'object') {
        text = detail.message || (detail.reason_code ? `[${detail.reason_code}]` : 'Refused by rules');
        if (detail.emergency_message) {
          text = `[EMERGENCY NOTIFIED] ${detail.emergency_message} (Rule outcome: ${text})`;
        }
      } else {
        text = detail || 'Booking failed.';
      }
      setMsg({ text, type: 'danger' });
      loadUrgentCases();
    }
  };

  // Helper for source badge styling
  const renderSourceBadge = (source) => {
    switch (source) {
      case 'MCP':
        return (
          <span className="badge badge-primary" style={{ fontWeight: 600 }}>
            MCP AGENT
          </span>
        );
      case 'Chat':
        return (
          <span className="badge badge-primary" style={{ fontWeight: 600 }}>
            CHAT BOT
          </span>
        );
      case 'Staff':
        return (
          <span className="badge badge-warning" style={{ fontWeight: 600 }}>
            STAFF DESK
          </span>
        );
      default:
        return (
          <span className="badge badge-neutral" style={{ fontWeight: 500 }}>
            {source || 'Website'}
          </span>
        );
    }
  };

  return (
    <div style={{ display: 'grid', gap: '1.75rem' }}>
      
      {/* 1. Admin Dashboard Header Banner */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '1.5rem'
      }}>
        <div>
          <h2 style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '30px',
            fontWeight: 700,
            color: 'var(--navy)',
            letterSpacing: '-0.025em',
            margin: 0
          }}>
            Admin & Clinic Operations Desk
          </h2>
          <p style={{ fontSize: '15px', color: 'var(--text-muted)', marginTop: '4px', lineHeight: 1.6 }}>
            Logged in as: <b>{user.name}</b> · Master appointment calendar, walk-in scheduling, triage alerts & late approvals
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => setShowBookingModal(true)}
            className="btn btn-primary"
            style={{
              padding: '0.75rem 1.45rem',
              fontSize: '14.5px',
              borderRadius: '6px',
              fontWeight: 600
            }}
          >
            <Plus size={16} /> Book Walk-in Appointment
          </button>
        </div>
      </div>

      {msg.text && (
        <div className={`alert alert-${msg.type}`} style={{ borderRadius: '6px' }}>
          {msg.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <span style={{ fontWeight: 500 }}>{msg.text}</span>
        </div>
      )}

      {/* 2. Admin Metric Cards with Mini Charts */}
      <div className="metric-cards-grid">
        {/* Metric 1: Total Appointments Scheduled */}
        <div className="metric-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                background: 'var(--cream-surface)',
                color: 'var(--navy)',
                border: '1px solid var(--cream-border)',
                width: '38px',
                height: '38px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Calendar size={19} />
              </div>
              <span style={{ fontSize: '14px', color: 'var(--text-muted)', fontWeight: 500 }}>
                Appointments
              </span>
            </div>
            <span className="badge badge-neutral" style={{ fontSize: '12px', padding: '2px 8px' }}>
              +95% in 7 days
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.75rem' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-heading)', fontSize: '28px', fontWeight: 700, color: 'var(--navy)', lineHeight: 1 }}>
                {appointments.length}
              </div>
              <span style={{ fontSize: '13px', color: 'var(--text-subtle)', fontWeight: 400, marginTop: '3px', display: 'block' }}>Date: {filterDate}</span>
            </div>

            {/* Embedded Mini Bar Chart */}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: '32px' }}>
              <div style={{ width: '6px', height: '14px', background: 'var(--cream-alt)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '22px', background: 'var(--cream-border)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '16px', background: 'var(--navy-light)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '30px', background: 'var(--navy)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '24px', background: 'var(--navy)', borderRadius: '2px' }} />
            </div>
          </div>
        </div>

        {/* Metric 2: Urgent Care Triage Queue */}
        <div className="metric-card" style={{
          borderColor: urgentCases.length > 0 ? '#fecdd3' : 'var(--border)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                background: '#fee2e2',
                color: '#b91c1c',
                width: '38px',
                height: '38px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <AlertTriangle size={19} />
              </div>
              <span style={{ fontSize: '14px', color: '#64748b', fontWeight: 500 }}>
                Urgent Triage
              </span>
            </div>
            <span className="badge badge-danger" style={{ fontSize: '12px', padding: '2px 8px' }}>
              Red Flag
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '1.8rem', fontWeight: 600, color: urgentCases.length > 0 ? '#b91c1c' : 'var(--navy)', lineHeight: 1 }}>
                {urgentCases.length}
              </div>
              <span style={{ fontSize: '0.72rem', color: urgentCases.length > 0 ? '#b91c1c' : 'var(--navy)', fontWeight: 600 }}>
                {urgentCases.length > 0 ? 'Immediate action required' : 'Triage queue clear'}
              </span>
            </div>

            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: '6px',
              background: '#fee2e2',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <AlertTriangle size={18} color="#b91c1c" className={urgentCases.length > 0 ? 'pulse' : ''} />
            </div>
          </div>
        </div>

        {/* Metric 3: Late Change Approvals (Amber accent) */}
        <div className="metric-card" style={{
          borderColor: approvals.length > 0 ? '#fde68a' : 'var(--border)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{
                background: '#fef3c7',
                color: '#d97706',
                width: '36px',
                height: '36px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <ShieldCheck size={18} />
              </div>
              <span style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>
                Late Approvals
              </span>
            </div>
            <span className="badge badge-warning" style={{ fontSize: '0.68rem', padding: '2px 8px' }}>
              Inside 2 hrs
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '2.2rem', fontWeight: '800', color: approvals.length > 0 ? '#d97706' : 'var(--navy)', lineHeight: 1 }}>
                {approvals.length}
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-subtle)', fontWeight: '600' }}>Staff review pending</span>
            </div>

            {/* Embedded Mini Area Wave */}
            <svg width="80" height="34" viewBox="0 0 80 34" fill="none">
              <path d="M0 24 Q20 8 40 18 T80 12" stroke="#f59e0b" strokeWidth="2" fill="none" />
              <path d="M0 24 Q20 8 40 18 T80 12 L80 34 L0 34 Z" fill="rgba(245, 158, 11, 0.15)" />
            </svg>
          </div>
        </div>

        {/* Metric 4: Active Doctors */}
        <div className="metric-card" style={{ borderRadius: '22px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{
                background: 'rgba(255, 107, 91, 0.14)',
                color: 'var(--coral)',
                width: '38px',
                height: '38px',
                borderRadius: '11px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Users size={18} />
              </div>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: '700' }}>
                Active Doctors
              </span>
            </div>
            <span className="badge badge-primary" style={{ fontSize: '0.68rem', padding: '2px 8px' }}>
              +25% OPD
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '2.2rem', fontWeight: '800', color: 'var(--navy)', lineHeight: 1 }}>
                {doctors.length}
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-subtle)', fontWeight: '600' }}>{specialities.length} specialities</span>
            </div>

            {/* Embedded Mini Sparkline */}
            <svg width="80" height="34" viewBox="0 0 80 34" fill="none">
              <path d="M0 26 Q20 14 40 16 T80 8" stroke="var(--navy)" strokeWidth="2.5" fill="none" />
              <circle cx="80" cy="8" r="3.5" fill="var(--coral)" stroke="#ffffff" strokeWidth="1.5" />
            </svg>
          </div>
        </div>
      </div>

      {/* 3. Pinned Urgent Cases Section (R4) */}
      {urgentCases.length > 0 && (
        <div id="section-urgent-triage" style={{
          background: 'linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%)',
          border: '2px solid #e11d48',
          borderRadius: 'var(--radius-2xl)',
          padding: '1.75rem',
          display: 'grid',
          gap: '1rem',
          boxShadow: '0 10px 30px -4px rgba(225, 29, 72, 0.2)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.85rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#be123c', fontWeight: '800', fontSize: '1.2rem' }}>
              <div style={{ background: '#be123c', color: '#fff', padding: '8px', borderRadius: '10px' }}>
                <AlertTriangle size={20} />
              </div>
              <span>Urgent Care Triage Queue ({urgentCases.length} Active Priority Case{urgentCases.length > 1 ? 's' : ''})</span>
            </div>
            <span className="badge badge-danger" style={{ padding: '0.35rem 0.85rem', fontSize: '0.75rem' }}>
              Requires Immediate Clinic Check-in
            </span>
          </div>

          <div style={{ display: 'grid', gap: '0.85rem' }}>
            {urgentCases.map(uc => (
              <div key={uc.id} style={{
                background: '#ffffff',
                border: '1px solid #fecdd3',
                borderRadius: '16px',
                padding: '1.15rem 1.35rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '1.25rem',
                flexWrap: 'wrap',
                boxShadow: 'var(--shadow-xs)'
              }}>
                <div style={{ display: 'grid', gap: '0.4rem', flex: '1 1 280px', minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                    <span className="badge badge-danger" style={{ textTransform: 'uppercase' }}>
                      {uc.category.replace(/_/g, ' ')}
                    </span>
                    {(uc.is_mcp_origin || (uc.reason && uc.reason.includes('from MCP')) || (uc.why && uc.why.includes('from MCP'))) ? (
                      <span className="badge badge-primary" style={{ fontWeight: '800' }}>
                        FROM MCP
                      </span>
                    ) : (uc.is_chat_origin || (uc.reason && uc.reason.startsWith('[Chat]')) || !uc.appointment_id) ? (
                      <span className="badge badge-coral" style={{ fontWeight: '800' }}>
                        CHAT ORIGIN
                      </span>
                    ) : null}
                    <span style={{ fontWeight: '800', color: '#0f172a', fontSize: '1rem' }}>
                      {uc.patient_name} ({uc.patient_id})
                    </span>
                    {uc.patient_mobile && (
                      <span style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: '600' }}>
                        Tel: {uc.patient_mobile}
                      </span>
                    )}
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                      {new Date(uc.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  <div style={{ fontSize: '0.95rem', color: '#1e293b', fontWeight: '700' }}>
                    "{uc.reason}"
                  </div>

                  <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                    <b style={{ color: '#0f172a' }}>AI Clinical Assessment:</b> {uc.why}
                  </div>
                </div>

                <button
                  onClick={() => handleMarkSeen(uc.id)}
                  className="btn btn-secondary btn-sm btn-pill"
                  style={{
                    flexShrink: 0,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                    borderColor: '#fda4af',
                    color: '#be123c',
                    fontWeight: '800',
                    padding: '0.5rem 1rem'
                  }}
                >
                  <Check size={14} /> Mark Seen
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 4. Late Change Approvals Queue (Iteration 4 R1) */}
      {approvals.length > 0 && (
        <div id="section-approvals" style={{
          background: 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
          border: '2px solid #f59e0b',
          borderRadius: 'var(--radius-2xl)',
          padding: '1.75rem',
          display: 'grid',
          gap: '1rem',
          boxShadow: '0 10px 30px -4px rgba(245, 158, 11, 0.2)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.85rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#b45309', fontWeight: '800', fontSize: '1.2rem' }}>
              <div style={{ background: '#b45309', color: '#fff', padding: '8px', borderRadius: '10px' }}>
                <ShieldCheck size={20} />
              </div>
              <span>Late Change Approvals Queue ({approvals.length} Request{approvals.length > 1 ? 's' : ''})</span>
            </div>
            <span className="badge badge-warning" style={{ padding: '0.35rem 0.85rem', fontSize: '0.75rem' }}>
              Submitted inside 2-hour window
            </span>
          </div>

          <div style={{ display: 'grid', gap: '0.85rem' }}>
            {approvals.map(appr => (
              <div key={appr.id} style={{
                background: '#ffffff',
                border: '1px solid #fde68a',
                borderRadius: '16px',
                padding: '1.15rem 1.35rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '1.25rem',
                flexWrap: 'wrap',
                boxShadow: 'var(--shadow-xs)'
              }}>
                <div style={{ display: 'grid', gap: '0.4rem', flex: '1 1 280px', minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                    <span className="badge" style={{
                      background: appr.action_type === 'cancel' ? 'var(--danger-light)' : 'var(--cream-surface)',
                      color: appr.action_type === 'cancel' ? '#991b1b' : 'var(--navy)',
                      border: appr.action_type === 'cancel' ? '1px solid var(--danger-border)' : '1px solid var(--cream-border)',
                      fontWeight: '800',
                      textTransform: 'uppercase'
                    }}>
                      {appr.action_type} REQUEST
                    </span>
                    <span style={{ fontWeight: '800', color: '#0f172a' }}>
                      Ref: {appr.appointment_id}
                    </span>
                    <span style={{ color: '#475569', fontWeight: '700' }}>
                      {appr.patient_name} ({appr.patient_id})
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                      {new Date(appr.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  {appr.action_type === 'reschedule' && (
                    <div style={{ fontSize: '0.9rem', color: '#1e293b', marginTop: '0.2rem', fontWeight: '600' }}>
                      Proposed slot: <b>{appr.new_doctor_name || appr.new_doctor_id}</b> ({appr.new_speciality}) on <b>{appr.new_date}</b> at <b>{appr.new_start_time} - {appr.new_end_time}</b> ({appr.new_visit_type})
                    </div>
                  )}

                  {appr.reason && (
                    <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                      <i>Reason: {appr.reason}</i>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', flexShrink: 0 }}>
                  <button
                    onClick={() => handleApprove(appr.id)}
                    className="btn btn-primary btn-sm btn-pill"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '0.5rem 1.15rem'
                    }}
                  >
                    <Check size={14} /> Approve
                  </button>
                  <button
                    onClick={() => handleReject(appr.id)}
                    className="btn btn-secondary btn-sm btn-pill"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      color: '#b91c1c',
                      borderColor: '#fca5a5',
                      padding: '0.5rem 1.15rem'
                    }}
                  >
                    <XCircle size={14} /> Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Filter Bar */}
      <div className="card" style={{
        display: 'flex',
        gap: '1.25rem',
        alignItems: 'center',
        flexWrap: 'wrap',
        borderRadius: 'var(--radius-xl)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <Calendar size={18} color="var(--primary)" />
          <label style={{ fontSize: '0.88rem', fontWeight: '800', color: '#1e293b' }}>Filter Date:</label>
          <input
            type="date"
            value={filterDate}
            onChange={(e) => setFilterDate(e.target.value)}
            style={{
              padding: '0.55rem 0.85rem',
              borderRadius: '10px',
              border: '1px solid var(--border)',
              fontWeight: '700',
              outline: 'none'
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <label style={{ fontSize: '0.88rem', fontWeight: '800', color: '#1e293b' }}>Doctor:</label>
          <select
            value={filterDoctorId}
            onChange={(e) => setFilterDoctorId(e.target.value)}
            style={{
              padding: '0.55rem 0.85rem',
              borderRadius: '10px',
              border: '1px solid var(--border)',
              background: '#fff',
              fontWeight: '700',
              outline: 'none'
            }}
          >
            <option value="">All Doctors (Clinic Master)</option>
            {doctors.map(d => (
              <option key={d.doctor_id} value={d.doctor_id}>{d.name}</option>
            ))}
          </select>
        </div>

        <button
          onClick={loadAppointments}
          className="btn btn-secondary btn-sm btn-pill"
          style={{ marginLeft: 'auto' }}
        >
          Refresh Master Schedule
        </button>
      </div>

      {/* 6. Master Clinic Appointments Table (DIRECTLY MATCHING IMAGE 2 & 3) */}
      <div id="section-staff-table" className="card" style={{ borderRadius: 'var(--radius-2xl)' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.25rem',
          borderBottom: '1px solid #f1f5f9',
          paddingBottom: '0.85rem'
        }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: '800', color: '#0f172a' }}>
              Master Clinic Appointments Schedule
            </h3>
            <p style={{ fontSize: '0.82rem', color: '#64748b', marginTop: '2px' }}>
              Comprehensive roster of consultations across Website, Chat, Staff, and MCP origins
            </p>
          </div>
          <span className="badge badge-primary">
            {appointments.length} Total Records
          </span>
        </div>

        {loading ? (
          <div style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span className="spin">⏳</span> Loading clinic appointments...
          </div>
        ) : appointments.length === 0 ? (
          <div style={{
            padding: '3rem',
            textAlign: 'center',
            color: 'var(--text-muted)',
            background: '#f8fafc',
            borderRadius: '16px',
            border: '1px dashed #cbd5e1'
          }}>
            <Calendar size={38} style={{ opacity: 0.35, marginBottom: '0.5rem' }} />
            <p style={{ fontWeight: '800', color: '#334155' }}>No appointments found for the selected date and filters.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="modern-table">
              <thead>
                <tr>
                  <th>Ref ID</th>
                  <th>Slot Time</th>
                  <th>Specialist</th>
                  <th>Patient Details</th>
                  <th>Speciality</th>
                  <th>Type</th>
                  <th>Booked Via</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Staff Actions</th>
                </tr>
              </thead>
              <tbody>
                {appointments.map(a => (
                  <tr key={a.appointment_id}>
                    {/* Ref ID */}
                    <td style={{ fontFamily: 'monospace', fontWeight: '800', color: '#0f172a', whiteSpace: 'nowrap' }}>
                      {a.appointment_id}
                    </td>

                    {/* Time */}
                    <td style={{ fontWeight: '800', color: '#1e293b', whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Clock size={14} color="var(--primary)" />
                        <span>{a.start_time} - {a.end_time}</span>
                      </div>
                    </td>

                    {/* Doctor */}
                    <td style={{ fontWeight: '700', color: '#0f172a', whiteSpace: 'nowrap' }}>
                      {a.doctor_name}
                    </td>

                    {/* Patient */}
                    <td style={{ maxWidth: '320px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                        {a.is_urgent && <span className="badge badge-danger">URGENT</span>}
                        <b style={{ color: '#0f172a' }}>{a.patient_name}</b>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>({a.patient_id})</span>
                      </div>
                      {a.reason && (
                        <div style={{ fontSize: '0.8rem', color: '#475569', marginTop: '3px', fontStyle: 'italic' }}>
                          "{a.reason}"
                        </div>
                      )}
                    </td>

                    {/* Speciality */}
                    <td>
                      <span className="badge badge-primary">{a.speciality}</span>
                    </td>

                    {/* Type */}
                    <td>
                      <span className="badge badge-neutral">
                        {a.visit_type === 'new' ? '20m' : '10m'}
                      </span>
                    </td>

                    {/* Booked Via (Website, Chat, Staff, MCP) */}
                    <td>
                      {renderSourceBadge(a.source)}
                    </td>

                    {/* Status */}
                    <td>
                      <span className={`badge ${
                        a.status === 'booked' ? (a.is_urgent ? 'badge-danger' : 'badge-primary') :
                        a.status === 'completed' ? 'badge-primary' : 'badge-neutral'
                      }`}>
                        {a.status}
                      </span>
                    </td>

                    {/* Actions */}
                    <td style={{ textAlign: 'right' }}>
                      {a.status === 'booked' && (
                        <button
                          onClick={() => handleStaffCancel(a.appointment_id)}
                          className="btn btn-danger btn-sm btn-pill"
                          title="Staff Override Cancel (Allowed even within 2 hours)"
                          style={{ padding: '0.45rem 0.95rem' }}
                        >
                          Cancel Override
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 7. Staff Search Debug Tool (Iteration 3) */}
      <div id="section-search-debug">
        <StaffSearchDebug />
      </div>

      {/* Walk-in Booking Modal */}
      {showBookingModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '1rem',
          zIndex: 9999
        }}>
          <div className="card glass-card" style={{ maxWidth: '600px', width: '100%', maxHeight: '92vh', overflowY: 'auto', borderRadius: 'var(--radius-2xl)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div>
                <h3 style={{ fontSize: '1.35rem', fontWeight: '800', color: '#0f172a' }}>
                  Book Walk-in Patient
                </h3>
                <p style={{ fontSize: '0.85rem', color: '#64748b' }}>
                  Register or schedule immediate clinic consultations
                </p>
              </div>
              <button onClick={() => setShowBookingModal(false)} className="btn btn-secondary btn-icon" style={{ borderRadius: '50%' }}>
                <XCircle size={18} />
              </button>
            </div>

            <form onSubmit={handleWalkinSubmit} style={{ display: 'grid', gap: '1.25rem' }}>
              {/* Toggle Existing vs New Walk-in */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '6px',
                background: '#f1f5f9',
                padding: '4px',
                borderRadius: '14px'
              }}>
                <button
                  type="button"
                  onClick={() => setIsNewPatient(false)}
                  style={{
                    padding: '9px',
                    borderRadius: '10px',
                    fontSize: '0.85rem',
                    fontWeight: '800',
                    background: !isNewPatient ? '#ffffff' : 'transparent',
                    color: !isNewPatient ? 'var(--primary)' : 'var(--text-muted)',
                    boxShadow: !isNewPatient ? 'var(--shadow-xs)' : 'none'
                  }}
                >
                  Existing Patient ID
                </button>
                <button
                  type="button"
                  onClick={() => setIsNewPatient(true)}
                  style={{
                    padding: '9px',
                    borderRadius: '10px',
                    fontSize: '0.85rem',
                    fontWeight: '800',
                    background: isNewPatient ? '#ffffff' : 'transparent',
                    color: isNewPatient ? 'var(--primary)' : 'var(--text-muted)',
                    boxShadow: isNewPatient ? 'var(--shadow-xs)' : 'none'
                  }}
                >
                  Register New Walk-in
                </button>
              </div>

              {!isNewPatient ? (
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                    Patient ID (e.g. P01 to P25)
                  </label>
                  <input
                    type="text"
                    value={walkinPatientId}
                    onChange={(e) => setWalkinPatientId(e.target.value)}
                    placeholder="e.g. P01"
                    style={{ width: '100%', padding: '0.75rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', outline: 'none' }}
                  />
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                      Full Name
                    </label>
                    <input
                      type="text"
                      value={newPatientName}
                      onChange={(e) => setNewPatientName(e.target.value)}
                      placeholder="e.g. Ramesh Kumar"
                      style={{ width: '100%', padding: '0.75rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', outline: 'none' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                      Mobile Number
                    </label>
                    <input
                      type="text"
                      value={newPatientMobile}
                      onChange={(e) => setNewPatientMobile(e.target.value)}
                      placeholder="10-digit mobile"
                      style={{ width: '100%', padding: '0.75rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', outline: 'none' }}
                    />
                  </div>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                    Speciality
                  </label>
                  <select
                    value={walkinSpeciality}
                    onChange={(e) => setWalkinSpeciality(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', background: '#fff', outline: 'none', fontWeight: '600' }}
                  >
                    {specialities.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                    Doctor
                  </label>
                  <select
                    value={walkinDoctorId}
                    onChange={(e) => setWalkinDoctorId(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', background: '#fff', outline: 'none', fontWeight: '600' }}
                  >
                    {doctors.map(d => <option key={d.doctor_id} value={d.doctor_id}>{d.name}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                    Visit Type
                  </label>
                  <select
                    value={walkinVisitType}
                    onChange={(e) => setWalkinVisitType(e.target.value)}
                    style={{ width: '100%', padding: '0.75rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', background: '#fff', outline: 'none', fontWeight: '600' }}
                  >
                    <option value="new">New Consultation (20m)</option>
                    <option value="follow_up">Follow-up (10m)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                    Date
                  </label>
                  <input
                    type="date"
                    value={walkinDate}
                    onChange={(e) => setWalkinDate(e.target.value)}
                    style={{ width: '100%', padding: '0.7rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', outline: 'none', fontWeight: '700' }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.4rem' }}>
                  Available Free Slots ({walkinSlots.length})
                </label>
                {walkinSlots.length === 0 ? (
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', padding: '1rem', background: '#f8fafc', borderRadius: '12px', textAlign: 'center' }}>
                    No free slots for this doctor and date.
                  </div>
                ) : (
                  <div className="slot-grid" style={{ maxHeight: '160px', overflowY: 'auto' }}>
                    {walkinSlots.map(t => (
                      <button
                        key={t}
                        type="button"
                        className={`slot-chip ${selectedSlot === t ? 'selected' : ''}`}
                        onClick={() => setSelectedSlot(t)}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                  <label style={{ fontSize: '0.85rem', fontWeight: '800', color: '#334155' }}>
                    Reason for Visit <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {walkinReason.length}/300
                  </span>
                </div>
                <textarea
                  value={walkinReason}
                  onChange={(e) => setWalkinReason(e.target.value)}
                  placeholder="Patient's stated reason / symptoms..."
                  rows={2}
                  maxLength={300}
                  style={{ width: '100%', padding: '0.75rem 0.95rem', borderRadius: '12px', border: '1px solid var(--border)', fontSize: '0.9rem' }}
                />
              </div>

              <button
                type="submit"
                disabled={!selectedSlot || !walkinReason.trim()}
                className="btn btn-primary btn-pill"
                style={{ width: '100%', marginTop: '0.75rem', padding: '0.9rem' }}
              >
                Confirm Walk-in Booking {selectedSlot && `at ${selectedSlot}`}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
