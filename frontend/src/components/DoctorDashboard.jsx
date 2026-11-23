import React, { useState, useEffect } from 'react';
import { api } from '../api';
import {
  Calendar,
  CheckCircle2,
  Clock,
  User,
  AlertCircle,
  Stethoscope,
  FileText,
  XCircle,
  Sparkles,
  AlertTriangle,
  ClipboardList,
  Activity,
  Users,
  Check,
  ChevronRight,
  Eye,
  TrendingUp,
  Download,
  Share2,
  MoreVertical,
  ShieldAlert
} from 'lucide-react';

export default function DoctorDashboard({ user }) {
  const [selectedDate, setSelectedDate] = useState(() => {
    return new Date().toISOString().split('T')[0];
  });
  const [appointments, setAppointments] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [allDoctors, setAllDoctors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState({ text: '', type: '' });

  // Doctor note completion modal state (R2)
  const [completingAppt, setCompletingAppt] = useState(null);
  const [doctorNoteText, setDoctorNoteText] = useState('');
  const [noteError, setNoteError] = useState('');
  const [completeLoading, setCompleteLoading] = useState(false);

  // Patient AI Summary drawer/modal state (R6)
  const [summaryPatient, setSummaryPatient] = useState(null);
  const [summaryData, setSummaryData] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const loadAppointments = async () => {
    setLoading(true);
    try {
      const data = await api.getAppointments({ date: selectedDate });
      setAppointments(data);
    } catch (err) {
      console.error('Failed to load appointments', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAppointments();
    if (user.user_id) {
      api.getDoctorSchedule(user.user_id)
        .then(setSchedule)
        .catch(() => {});
    }
    api.getDoctors()
      .then(setAllDoctors)
      .catch(() => {});
  }, [selectedDate, user.user_id]);

  const getInitials = (docName) => {
    if (!docName) return 'DR';
    return docName.replace('Dr.', '').trim().split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase();
  };

  const currentDoctor = allDoctors.find(
    d => d.doctor_id === (user.doctor_id || user.user_id) || d.name === user.name
  ) || {
    doctor_id: user.doctor_id || user.user_id || 'D1',
    name: user.name || 'Dr. Specialist',
    specialities: user.speciality ? [user.speciality] : ['Ophthalmology']
  };

  const otherDoctors = allDoctors.filter(d => d.doctor_id !== currentDoctor.doctor_id);

  // Dynamic Real-time Consultation Analytics (OPD time brackets)
  const timeSlots = [
    { label: '09:00 - 10:30', start: '09:00', end: '10:30', x: 50 },
    { label: '10:30 - 12:00', start: '10:30', end: '12:00', x: 150 },
    { label: '12:00 - 13:30', start: '12:00', end: '13:30', x: 250 },
    { label: '13:30 - 15:00', start: '13:30', end: '15:00', x: 350 },
    { label: '15:00 - 16:30', start: '15:00', end: '16:30', x: 450 },
    { label: '16:30 - 18:00', start: '16:30', end: '18:00', x: 550 },
  ];

  const slotAnalytics = timeSlots.map(slot => {
    const inSlot = appointments.filter(a => {
      if (!a.start_time) return false;
      return a.start_time >= slot.start && a.start_time < slot.end;
    });
    const newCount = inSlot.filter(a => a.visit_type === 'new').length;
    const followCount = inSlot.filter(a => a.visit_type === 'followup').length;
    const completedInSlot = inSlot.filter(a => a.status === 'completed').length;
    return {
      ...slot,
      total: inSlot.length,
      newCount,
      followCount,
      completedInSlot,
    };
  });

  const maxSlotCount = Math.max(1, ...slotAnalytics.map(s => s.total));
  const peakSlot = slotAnalytics.reduce((prev, curr) => (curr.total > prev.total ? curr : prev), slotAnalytics[0]);
  const newVisitsTotal = appointments.filter(a => a.visit_type === 'new').length;
  const followupVisitsTotal = appointments.filter(a => a.visit_type === 'followup').length;
  const completedTotal = appointments.filter(a => a.status === 'completed').length;
  const completionPercentage = appointments.length > 0 
    ? Math.round((completedTotal / appointments.length) * 100) 
    : 100;

  const handleOpenCompleteModal = (appt) => {
    setCompletingAppt(appt);
    setDoctorNoteText('');
    setNoteError('');
  };

  const handleSaveComplete = async (e) => {
    e.preventDefault();
    const cleanNote = doctorNoteText.trim();
    if (!cleanNote) {
      setNoteError('Doctor consultation note is required to complete the visit.');
      return;
    }

    setCompleteLoading(true);
    try {
      await api.completeAppointment(completingAppt.appointment_id, cleanNote);
      setMsg({
        text: `Visit ${completingAppt.appointment_id} completed and clinical note saved. Patient is now eligible for follow-ups.`,
        type: 'success'
      });
      setCompletingAppt(null);
      loadAppointments();
    } catch (err) {
      const detail = err.detail?.message || err.detail || 'Failed to complete visit.';
      setNoteError(detail);
    } finally {
      setCompleteLoading(false);
    }
  };

  const handleOpenSummary = async (appt) => {
    setSummaryPatient(appt);
    setSummaryLoading(true);
    setSummaryData(null);
    try {
      const res = await api.getDoctorPatientSummary(appt.patient_id, appt.appointment_id);
      setSummaryData(res);
    } catch (err) {
      const detail = err.detail || 'Failed to load patient clinical summary.';
      setMsg({ text: detail, type: 'danger' });
      setSummaryPatient(null);
    } finally {
      setSummaryLoading(false);
    }
  };

  // Metrics
  const totalCount = appointments.length;
  const completedCount = appointments.filter(a => a.status === 'completed').length;
  const pendingCount = appointments.filter(a => a.status === 'booked').length;
  const urgentCount = appointments.filter(a => a.is_urgent).length;

  return (
    <div style={{ display: 'grid', gap: '2rem' }}>
      
      {/* 1. Header Banner & Action Pills */}
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
            Welcome back, {user.name}!
          </h2>
          <p style={{ fontSize: '15px', color: 'var(--text-muted)', marginTop: '4px', lineHeight: 1.6 }}>
            Doctor ID: <b>{user.user_id}</b> · Review daily consultations, clinical intake notes, and AI chart summaries
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ borderRadius: '6px', fontSize: '14px', padding: '0.6rem 1.1rem', fontWeight: 500 }}
            onClick={() => alert('Generating daily OPD clinical report...')}
          >
            <Download size={14} color="var(--navy)" /> Export to CSV
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ borderRadius: '6px', fontSize: '14px', padding: '0.6rem 1.1rem', fontWeight: 500 }}
            onClick={() => alert('Generating comprehensive weekly summary...')}
          >
            Generate Report
          </button>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            background: 'var(--navy)',
            color: 'var(--cream-text)',
            padding: '0.6rem 1.15rem',
            borderRadius: '6px',
            fontSize: '14px',
            fontWeight: 500,
            boxShadow: 'var(--shadow-xs)'
          }}>
            <Calendar size={14} color="var(--cream-text)" /> Today's Session
          </div>
        </div>
      </div>

      {msg.text && (
        <div className={`alert alert-${msg.type}`} style={{ borderRadius: 'var(--radius)' }}>
          {msg.type === 'success' ? <CheckCircle2 size={19} /> : <AlertCircle size={19} />}
          <span style={{ fontWeight: '500' }}>{msg.text}</span>
        </div>
      )}

      {/* 2. Four Stat Metric Cards - Clean SaaS Presentation */}
      <div className="metric-cards-grid">
        
        {/* Metric 1: Total Consultations (with mini SVG wave chart) */}
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
                <Users size={19} />
              </div>
              <span style={{ fontSize: '14px', color: 'var(--text-muted)', fontWeight: 500 }}>
                Total Patients
              </span>
            </div>
            <span className="badge badge-neutral" style={{ fontSize: '12px', padding: '2px 8px' }}>
              +24% vs last week
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.75rem' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-heading)', fontSize: '30px', fontWeight: 700, color: 'var(--navy)', lineHeight: 1 }}>
                {totalCount}
              </div>
              <span style={{ fontSize: '13px', color: 'var(--text-subtle)', fontWeight: 400, marginTop: '3px', display: 'block' }}>Consultations today</span>
            </div>

            {/* Embedded Mini SVG Wave Sparkline */}
            <svg width="100" height="40" viewBox="0 0 100 40" fill="none">
              <path d="M0 30 Q25 10 50 25 T100 12" stroke="var(--navy)" strokeWidth="2" fill="none" />
              <path d="M0 30 Q25 10 50 25 T100 12 L100 40 L0 40 Z" fill="rgba(20, 33, 61, 0.06)" />
              <circle cx="50" cy="25" r="3" fill="var(--coral)" stroke="#ffffff" strokeWidth="1.5" />
            </svg>
          </div>
        </div>

        {/* Metric 2: Completed Visits */}
        <div className="metric-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                background: 'var(--cream-surface)',
                color: 'var(--navy)',
                width: '38px',
                height: '38px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid var(--cream-border)'
              }}>
                <CheckCircle2 size={19} />
              </div>
              <span style={{ fontSize: '14px', color: 'var(--text-muted)', fontWeight: 500 }}>
                Completed Visits
              </span>
            </div>
            <span className="badge badge-primary" style={{ fontSize: '12px', padding: '2px 8px' }}>
              +14% OPD
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.75rem' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-heading)', fontSize: '28px', fontWeight: 700, color: 'var(--navy)', lineHeight: 1 }}>
                {completedCount}
              </div>
              <span style={{ fontSize: '13px', color: 'var(--text-subtle)', fontWeight: 400, marginTop: '3px', display: 'block' }}>Notes recorded</span>
            </div>

            {/* Embedded Mini Bar Chart */}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: '32px' }}>
              <div style={{ width: '6px', height: '14px', background: 'var(--cream-alt)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '22px', background: 'var(--cream-border)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '18px', background: 'var(--navy-light)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '30px', background: 'var(--navy)', borderRadius: '2px' }} />
              <div style={{ width: '6px', height: '24px', background: 'var(--navy)', borderRadius: '2px' }} />
            </div>
          </div>
        </div>

        {/* Metric 3: Pending Queue */}
        <div className="metric-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                background: '#fef3c7',
                color: '#d97706',
                width: '38px',
                height: '38px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Clock size={19} />
              </div>
              <span style={{ fontSize: '14px', color: '#64748b', fontWeight: 500 }}>
                Pending Queue
              </span>
            </div>
            <span className="badge badge-warning" style={{ fontSize: '12px', padding: '2px 8px' }}>
              In Progress
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.75rem' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-heading)', fontSize: '28px', fontWeight: 700, color: '#d97706', lineHeight: 1 }}>
                {pendingCount}
              </div>
              <span style={{ fontSize: '13px', color: '#94a3b8', fontWeight: 400, marginTop: '3px', display: 'block' }}>Awaiting consultation</span>
            </div>

            {/* Embedded Progress Wave */}
            <svg width="80" height="30" viewBox="0 0 80 30" fill="none">
              <path d="M0 22 Q20 5 40 18 T80 8" stroke="#f59e0b" strokeWidth="2" fill="none" />
              <circle cx="40" cy="18" r="3" fill="#f59e0b" stroke="#ffffff" strokeWidth="1" />
            </svg>
          </div>
        </div>

        {/* Metric 4: Urgent Priority Cases */}
        <div className="metric-card">
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
                Urgent Attention
              </span>
            </div>
            <span className="badge badge-danger" style={{ fontSize: '12px', padding: '2px 8px' }}>
              Priority Triage
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '0.75rem' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-heading)', fontSize: '28px', fontWeight: 700, color: '#b91c1c', lineHeight: 1 }}>
                {urgentCount}
              </div>
              <span style={{ fontSize: '13px', color: '#94a3b8', fontWeight: 400, marginTop: '3px', display: 'block' }}>Red flag cases</span>
            </div>

            <div style={{
              width: '38px',
              height: '38px',
              borderRadius: '6px',
              background: '#fee2e2',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <AlertTriangle size={19} color="#b91c1c" className={urgentCount > 0 ? 'pulse' : ''} />
            </div>
          </div>
        </div>

      </div>

      {/* 3. Middle Section: Consultation Arrival Analytics (Left) & Specialist Roster (Right) */}
      <div id="section-arrival-stats" className="arrival-stats-grid">
        
        {/* Left: Patient Arrival Statistics */}
        <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.65rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ background: 'var(--cream-surface)', color: 'var(--navy)', padding: '6px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                  <TrendingUp size={16} />
                </div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--navy)', margin: 0 }}>
                  Patient Arrival & Consultation Flow
                </h3>
              </div>
              <span className="badge badge-primary" style={{ fontSize: '0.72rem' }}>
                Live OPD Flow
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
              <div style={{ fontSize: '1.75rem', fontWeight: 600, color: 'var(--navy)' }}>
                {appointments.length} Consultations
              </div>
              <span style={{ fontSize: '0.84rem', color: 'var(--navy)', fontWeight: 500 }}>
                {appointments.length > 0 ? `${completionPercentage}% Completed` : 'Open for patient intake'}
              </span>
            </div>
          </div>

          {/* Dynamic SVG Area & Bar Chart calculated directly from Appointments */}
          <div style={{ margin: '1.25rem 0 0.5rem 0', position: 'relative' }}>
            <svg width="100%" height="165" viewBox="0 0 600 165" fill="none" preserveAspectRatio="none">
              <defs>
                <pattern id="diagonalHatch" patternUnits="userSpaceOnUse" width="6" height="6">
                  <path d="M-1,1 l2,-2 M0,6 l6,-6 M5,7 l2,-2" stroke="rgba(20, 33, 61, 0.08)" strokeWidth="1.2" />
                </pattern>
                <linearGradient id="areaGlow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgba(20, 33, 61, 0.15)" />
                  <stop offset="100%" stopColor="rgba(20, 33, 61, 0.01)" />
                </linearGradient>
                <linearGradient id="peakBarGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--navy)" />
                  <stop offset="100%" stopColor="var(--coral)" />
                </linearGradient>
              </defs>

              {/* Dynamic SVG Area Path */}
              {(() => {
                const points = slotAnalytics.map((s) => {
                  const barH = s.total > 0 ? 30 + Math.round((s.total / maxSlotCount) * 80) : 18;
                  const y = 145 - barH;
                  return { x: s.x, y };
                });
                const dArea = `M0 145 L${points[0].x} ${points[0].y} ` +
                  points.slice(1).map(p => `L${p.x} ${p.y} `).join('') +
                  `L600 145 Z`;
                const dLine = `M0 145 L${points[0].x} ${points[0].y} ` +
                  points.slice(1).map(p => `L${p.x} ${p.y} `).join('');
                return (
                  <>
                    <path d={dArea} fill="url(#areaGlow)" />
                    <path d={dArea} fill="url(#diagonalHatch)" />
                    <path d={dLine} stroke="var(--navy)" strokeWidth="2.5" fill="none" />
                  </>
                );
              })()}

              {/* Dynamic Bars and Points for each slot */}
              {slotAnalytics.map((s) => {
                const barH = s.total > 0 ? 25 + Math.round((s.total / maxSlotCount) * 85) : 12;
                const y = 145 - barH;
                const isPeak = s.total === peakSlot.total && peakSlot.total > 0;
                return (
                  <g key={s.label}>
                    {/* Bar stem */}
                    <rect
                      x={s.x - 14}
                      y={y}
                      width="28"
                      height={barH}
                      rx="7"
                      fill={isPeak ? 'url(#peakBarGrad)' : s.total > 0 ? 'var(--cream-alt)' : '#FAF5ED'}
                      opacity={isPeak ? 1 : 0.85}
                    />

                    {/* Count label above bar */}
                    <text
                      x={s.x}
                      y={y - 7}
                      fill={isPeak ? 'var(--navy)' : 'var(--text-muted)'}
                      fontSize="11"
                      fontWeight="800"
                      textAnchor="middle"
                    >
                      {s.total > 0 ? `${s.total}` : '0'}
                    </text>

                    {/* Tooltip badge over peak slot */}
                    {isPeak && (
                      <g transform={`translate(${Math.min(460, Math.max(20, s.x - 70))}, 0)`}>
                        <rect width="140" height="24" rx="6" fill="var(--navy)" />
                        <text x="70" y="16" fill="var(--cream-text)" fontSize="10.5" fontWeight="700" textAnchor="middle">
                          Peak OPD: {s.start} - {s.end}
                        </text>
                      </g>
                    )}

                    {/* Point circle marker */}
                    <circle cx={s.x} cy={y} r="4" fill={isPeak ? '#ffffff' : 'var(--coral)'} stroke={isPeak ? 'var(--coral)' : '#ffffff'} strokeWidth="2" />
                  </g>
                );
              })}
            </svg>

            {/* X-axis time marks */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem', color: '#64748b', fontWeight: '700', marginTop: '4px' }}>
              <span>09:00</span>
              <span>10:30</span>
              <span>12:00</span>
              <span>13:30 (Lunch)</span>
              <span>15:00</span>
              <span>16:30</span>
              <span>18:00</span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1.25rem', marginTop: '0.65rem', fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: '600', flexWrap: 'wrap' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--navy)' }} />
              New Visits (20m): <b style={{ color: 'var(--navy)' }}>{newVisitsTotal}</b>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--coral)' }} />
              Follow-ups (10m): <b style={{ color: 'var(--navy)' }}>{followupVisitsTotal}</b>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--cream-border)' }} />
              Completed: <b style={{ color: 'var(--navy)' }}>{completedTotal}</b>
            </span>
            {peakSlot.total > 0 && (
              <span style={{ marginLeft: 'auto', color: 'var(--navy)', fontWeight: '800' }}>
                Peak Flow: {peakSlot.start} - {peakSlot.end} ({peakSlot.total} patients)
              </span>
            )}
          </div>
        </div>

        {/* Right: "Our Specialists" Showcase Card */}
        <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Stethoscope size={16} color="var(--navy)" />
                <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--navy)', margin: 0 }}>
                  Eye Specialist Profile
                </h4>
              </div>
              <span className="badge badge-primary" style={{ fontSize: '0.68rem' }}>
                Active OPD
              </span>
            </div>

            {/* Featured Active Doctor Card */}
            <div style={{
              background: 'var(--cream-surface)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              padding: '1.15rem 1rem',
              textAlign: 'center',
              marginBottom: '0.85rem'
            }}>
              <div style={{
                width: '48px',
                height: '48px',
                borderRadius: '6px',
                background: 'var(--navy-light)',
                border: '1px solid rgba(244, 237, 224, 0.2)',
                color: 'var(--cream-text)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 600,
                fontSize: '1.15rem',
                marginBottom: '0.4rem'
              }}>
                {getInitials(currentDoctor.name)}
              </div>
              <div style={{ fontWeight: 600, fontSize: '1.05rem', color: 'var(--navy)' }}>
                {currentDoctor.name}
              </div>
              <div style={{ display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'wrap', marginTop: '4px' }}>
                {(currentDoctor.specialities || ['Ophthalmology']).map(spec => (
                  <span key={spec} className="badge badge-navy" style={{ fontSize: '0.68rem', borderRadius: '4px' }}>
                    {spec}
                  </span>
                ))}
              </div>
              <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginTop: '6px' }}>
                Doctor ID: <b>{currentDoctor.doctor_id}</b> · OPD: Mon–Sat
              </div>
            </div>

            {/* Other Doctors mini list */}
            <div>
              <div style={{ fontSize: '0.74rem', fontWeight: 600, color: '#64748b', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Clinic Specialists Roster
              </div>
              <div style={{ display: 'grid', gap: '0.4rem' }}>
                {otherDoctors.slice(0, 3).map(d => (
                  <div key={d.doctor_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.45rem 0.6rem', background: '#ffffff', borderRadius: '6px', border: '1px solid var(--border)' }}>
                    <div>
                      <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--navy)' }}>
                        {d.name}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: '#64748b' }}>
                        {d.specialities ? d.specialities.join(', ') : 'Ophthalmology'}
                      </div>
                    </div>
                    <span className="badge badge-neutral" style={{ fontSize: '0.65rem' }}>
                      {d.doctor_id}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* 4. Controls & Date Filter */}
      <div className="card" style={{ padding: '1rem 1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Calendar size={16} color="var(--navy)" />
            <label style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--navy)' }}>
              Select Roster Date:
            </label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid var(--border)',
                outline: 'none',
                fontWeight: 500,
                color: 'var(--navy)'
              }}
            />
            <button
              type="button"
              onClick={() => setSelectedDate(new Date().toISOString().split('T')[0])}
              className="btn btn-secondary btn-sm"
              style={{ borderRadius: '6px', fontWeight: 600 }}
            >
              Today
            </button>
          </div>

          <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)', fontWeight: 500 }}>
            Showing <b>{appointments.length}</b> scheduled patient(s) on <b>{selectedDate}</b>
          </div>
        </div>
      </div>

      {/* 5. Daily Consultation Queue Table */}
      <div id="section-doctor-queue" className="card">
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem',
          borderBottom: '1px solid var(--border-light)',
          paddingBottom: '0.75rem'
        }}>
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--navy)' }}>
              Daily Consultation Queue
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              Scheduled consultations with pre-assessment intake notes and clinical records
            </p>
          </div>
          <span className="badge badge-primary">
            {appointments.length} Patient{appointments.length !== 1 ? 's' : ''}
          </span>
        </div>

        {loading ? (
          <div style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span className="spin">⏳</span> Loading patient queue...
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
            <p style={{ fontWeight: '800', color: '#334155', fontSize: '1rem' }}>No appointments scheduled for {selectedDate}.</p>
            <p style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>Change the roster date above to inspect past or upcoming consultations.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="modern-table">
              <thead>
                <tr>
                  <th>Slot Time</th>
                  <th>Patient & Reason</th>
                  <th>Speciality</th>
                  <th>Visit Type</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {appointments.map(a => (
                  <tr key={a.appointment_id}>
                    {/* Time Slot */}
                    <td style={{ fontWeight: '800', color: '#0f172a', whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Clock size={15} color="var(--primary)" />
                        <span>{a.start_time} - {a.end_time}</span>
                      </div>
                    </td>

                    {/* Patient & Reason & Pre-Assessment Intake Notes */}
                    <td style={{ maxWidth: '440px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                        {a.is_urgent && (
                          <span className="badge badge-danger">URGENT</span>
                        )}
                        <span style={{ fontWeight: '800', color: '#0f172a', fontSize: '0.95rem' }}>
                          {a.patient_name}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace' }}>
                          ({a.patient_id})
                        </span>
                      </div>

                      <div style={{ fontSize: '0.85rem', color: '#475569', marginTop: '4px', fontStyle: 'italic' }}>
                        Reason: "{a.reason || 'No reason recorded'}"
                      </div>

                      {/* Pre-Assessment Intake Notes Card */}
                      {a.intake_notes && (
                        <div style={{
                          fontSize: '0.82rem',
                          color: 'var(--navy)',
                          marginTop: '8px',
                          background: 'var(--cream-surface)',
                          padding: '10px 14px',
                          borderRadius: '12px',
                          border: '1px solid var(--border)',
                          boxShadow: 'var(--shadow-xs)'
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: '800', color: 'var(--navy)', marginBottom: '4px' }}>
                            <ClipboardList size={15} color="var(--coral)" /> Pre-Assessment Intake Notes:
                          </div>
                          <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                            {a.intake_notes}
                          </div>
                        </div>
                      )}

                      {/* Saved Doctor Note */}
                      {a.doctor_note && (
                        <div style={{
                          fontSize: '0.82rem',
                          color: 'var(--navy)',
                          marginTop: '6px',
                          background: 'var(--cream-surface)',
                          padding: '8px 12px',
                          borderRadius: '10px',
                          border: '1px solid var(--border)'
                        }}>
                          <b>Doctor Consultation Note:</b> {a.doctor_note}
                        </div>
                      )}
                    </td>

                    {/* Speciality */}
                    <td>
                      <span className="badge badge-cream">{a.speciality}</span>
                    </td>

                    {/* Visit Type */}
                    <td>
                      <span className="badge badge-neutral">
                        {a.visit_type === 'new' ? 'New (20m)' : 'Follow-up (10m)'}
                      </span>
                    </td>

                    {/* Status */}
                    <td>
                      <span className={`badge ${
                        a.status === 'completed' ? 'badge-primary' :
                        a.status === 'booked' ? (a.is_urgent ? 'badge-danger' : 'badge-primary') : 'badge-neutral'
                      }`}>
                        {a.status}
                      </span>
                    </td>

                    {/* Actions */}
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                        <button
                          onClick={() => handleOpenSummary(a)}
                          className="btn btn-secondary btn-sm btn-pill"
                          style={{ gap: '5px' }}
                          title="Open Patient Chart & AI Summary"
                        >
                          <FileText size={14} color="var(--coral)" /> AI Summary
                        </button>
                        {a.status === 'booked' && (
                          <button
                            onClick={() => handleOpenCompleteModal(a)}
                            className="btn btn-primary btn-sm btn-pill"
                            style={{ gap: '5px' }}
                          >
                            <CheckCircle2 size={14} /> Complete Visit
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 6. Weekly Schedule Reference Card (Image 1 style) */}
      {schedule.length > 0 && (
        <div id="section-doctor-schedule" className="card" style={{ borderRadius: 'var(--radius-2xl)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '1.25rem' }}>
            <Calendar size={20} color="var(--coral)" />
            <h3 style={{ fontSize: '1.15rem', fontWeight: '800', color: 'var(--navy)', margin: 0 }}>
              Weekly OPD & Surgery Schedule Reference
            </h3>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
            gap: '0.75rem'
          }}>
            {schedule.map((s, idx) => (
              <div key={idx} style={{
                padding: '0.9rem',
                borderRadius: '14px',
                border: '1px solid var(--border)',
                background: s.status === 'OPD' ? 'linear-gradient(135deg, var(--cream-surface) 0%, #ffffff 100%)' : s.status === 'SURGERY' ? 'linear-gradient(135deg, #fffbeb 0%, #ffffff 100%)' : 'var(--cream-surface)',
                fontSize: '0.85rem',
                textAlign: 'center',
                boxShadow: 'var(--shadow-xs)'
              }}>
                <div style={{ fontWeight: '800', color: 'var(--navy)' }}>{s.day}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'capitalize', marginTop: '2px' }}>
                  {s.session}
                </div>
                <div style={{
                  fontWeight: '800',
                  marginTop: '5px',
                  color: s.status === 'OPD' ? 'var(--navy)' : s.status === 'SURGERY' ? '#b45309' : 'var(--text-subtle)'
                }}>
                  {s.status}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Doctor Note Completion Modal (R2) */}
      {completingAppt && (
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
          <div className="card glass-card" style={{ maxWidth: '560px', width: '100%', borderRadius: 'var(--radius-2xl)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
              <div>
                <h3 style={{ fontSize: '1.35rem', fontWeight: '800', color: '#0f172a' }}>
                  Complete Consultation Visit
                </h3>
                <p style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '2px' }}>
                  Patient: <b>{completingAppt.patient_name}</b> ({completingAppt.patient_id}) · {completingAppt.speciality}
                </p>
              </div>
              <button onClick={() => setCompletingAppt(null)} className="btn btn-secondary btn-icon" style={{ borderRadius: '50%' }}>
                <XCircle size={18} />
              </button>
            </div>

            {noteError && (
              <div className="alert alert-danger" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>
                <AlertCircle size={16} />
                <span>{noteError}</span>
              </div>
            )}

            <form onSubmit={handleSaveComplete}>
              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '800', color: '#334155', marginBottom: '0.45rem' }}>
                  Doctor Clinical Note <span style={{ color: '#ef4444' }}>* (Required)</span>
                </label>
                <textarea
                  value={doctorNoteText}
                  onChange={(e) => { setDoctorNoteText(e.target.value); setNoteError(''); }}
                  placeholder="Record ophthalmic diagnosis, visual acuity (VA OD/OS), intraocular pressure (IOP), findings, prescribed drops, or review interval..."
                  rows={5}
                  required
                  style={{
                    width: '100%',
                    padding: '0.9rem',
                    borderRadius: '12px',
                    border: '1px solid var(--border)',
                    outline: 'none',
                    resize: 'vertical',
                    fontSize: '0.92rem',
                    lineHeight: 1.5
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  onClick={() => setCompletingAppt(null)}
                  className="btn btn-secondary btn-pill"
                  disabled={completeLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!doctorNoteText.trim() || completeLoading}
                  className="btn btn-primary btn-pill"
                >
                  {completeLoading ? 'Saving Note...' : 'Save & Mark Completed'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Patient AI Summary Modal (R6) */}
      {summaryPatient && (
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
          <div className="card glass-card" style={{
            maxWidth: '740px',
            width: '100%',
            maxHeight: '90vh',
            overflowY: 'auto',
            borderRadius: 'var(--radius-2xl)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div style={{
                  background: 'linear-gradient(135deg, var(--navy-light) 0%, var(--navy) 100%)',
                  color: 'var(--coral)',
                  padding: '9px',
                  borderRadius: '14px',
                  border: '1px solid rgba(255, 107, 91, 0.3)'
                }}>
                  <Sparkles size={24} />
                </div>
                <div>
                  <h3 style={{ fontSize: '1.3rem', fontWeight: '800', color: 'var(--navy)', margin: 0 }}>
                    Clinical Patient Chart: {summaryPatient.patient_name}
                  </h3>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                    Patient ID: {summaryPatient.patient_id} · NetraCare Medical EHR
                  </span>
                </div>
              </div>
              <button onClick={() => setSummaryPatient(null)} className="btn btn-secondary btn-icon" style={{ borderRadius: '50%' }}>
                <XCircle size={18} />
              </button>
            </div>

            {summaryLoading ? (
              <div style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                <div className="spin" style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>⏳</div>
                <p style={{ fontWeight: '800', color: 'var(--navy)' }}>Synthesizing clinical notes with Gemini LLM...</p>
              </div>
            ) : summaryData ? (
              <div style={{ display: 'grid', gap: '1.5rem' }}>
                
                {/* Patient Profile Card */}
                <div style={{
                  background: 'var(--cream-surface)',
                  borderRadius: '14px',
                  padding: '1.15rem 1.35rem',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                  gap: '0.85rem',
                  fontSize: '0.85rem',
                  border: '1px solid var(--border)'
                }}>
                  <div>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Age:</span>
                    <b style={{ color: 'var(--navy)' }}>{summaryData.age !== null ? `${summaryData.age} years` : 'Not recorded'}</b>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>General Health:</span>
                    <b style={{ color: 'var(--navy)' }}>{summaryData.general_health}</b>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Allergies:</span>
                    <b style={{ color: summaryData.allergies !== 'None known' ? '#b91c1c' : 'var(--navy)' }}>
                      {summaryData.allergies}
                    </b>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.75rem' }}>Today's Reason:</span>
                    <b style={{ color: 'var(--navy)' }}>{summaryData.today_reason || 'Routine review'}</b>
                  </div>
                </div>

                {/* AI Summary Card */}
                <div style={{
                  border: '1px solid var(--border)',
                  background: 'var(--cream-surface)',
                  borderRadius: '16px',
                  padding: '1.5rem',
                  boxShadow: 'var(--shadow-xs)'
                }}>
                  <div style={{
                    fontSize: '0.78rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.07em',
                    color: 'var(--navy)',
                    fontWeight: '800',
                    marginBottom: '0.65rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}>
                    <Sparkles size={15} color="var(--coral)" /> {summaryData.disclaimer}
                  </div>
                  <p style={{ fontSize: '1rem', color: 'var(--navy)', lineHeight: 1.65, fontWeight: '500' }}>
                    {summaryData.summary}
                  </p>
                </div>

                {/* Full Historical Doctor Notes */}
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: '800', marginBottom: '0.75rem', color: '#1e293b' }}>
                    Complete Historical Doctor Notes ({summaryData.past_notes.length} Completed Consultation{summaryData.past_notes.length !== 1 ? 's' : ''})
                  </h4>

                  {summaryData.past_notes.length === 0 ? (
                    <div style={{ padding: '1.5rem', background: '#f8fafc', borderRadius: '12px', fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center', border: '1px dashed #cbd5e1' }}>
                      No prior completed consultations on file for this patient.
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gap: '0.85rem' }}>
                      {summaryData.past_notes.map((pn, idx) => (
                        <div key={idx} style={{
                          border: '1px solid var(--border)',
                          borderRadius: '14px',
                          padding: '1.15rem',
                          background: '#fff',
                          fontSize: '0.85rem',
                          boxShadow: 'var(--shadow-xs)'
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                            <div style={{ fontWeight: '800', color: '#0f172a' }}>
                              <b>{pn.doctor_name}</b> ({pn.speciality}) · <span style={{ color: 'var(--text-muted)', fontWeight: '500' }}>{pn.date}</span>
                            </div>
                            <span className="badge badge-neutral" style={{ textTransform: 'uppercase', fontSize: '0.7rem' }}>
                              {pn.visit_type}
                            </span>
                          </div>
                          {pn.reason && (
                            <div style={{ color: '#475569', fontStyle: 'italic', marginBottom: '0.5rem', fontSize: '0.82rem' }}>
                              Patient Reason: "{pn.reason}"
                            </div>
                          )}
                          <div style={{
                            color: '#0f172a',
                            background: '#f8fafc',
                            padding: '0.75rem 1rem',
                            borderRadius: '10px',
                            border: '1px solid #f1f5f9',
                            lineHeight: 1.5
                          }}>
                            <b>Clinical Note:</b> {pn.doctor_note || 'None recorded'}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
