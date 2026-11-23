import React, { useState, useEffect } from 'react';
import { api } from '../api';
import {
  User,
  Stethoscope,
  ShieldCheck,
  ArrowRight,
  Eye
} from 'lucide-react';

export default function LoginModal({ onLoginSuccess }) {
  const [role, setRole] = useState('patient');
  const [mobile, setMobile] = useState('9000000001'); // Default to Asha Verma for convenience
  const [name, setName] = useState('Asha Verma');
  const [doctorId, setDoctorId] = useState('D1');
  const [doctors, setDoctors] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getDoctors()
      .then(docs => {
        setDoctors(docs);
        if (docs.length > 0) setDoctorId(docs[0].doctor_id);
      })
      .catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      let payload = { role };
      if (role === 'patient') {
        payload.mobile = mobile.trim();
        payload.name = name.trim();
      } else if (role === 'doctor') {
        payload.doctor_id = doctorId;
      } else if (role === 'staff') {
        payload.name = name.trim() || 'Clinic Receptionist';
      }

      const res = await api.login(payload);
      localStorage.setItem('netracare_user', JSON.stringify(res));
      onLoginSuccess(res);
    } catch (err) {
      setError(err?.detail?.message || err?.detail || 'Login failed. Please check inputs.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickDemoPatient = (demoMobile, demoName) => {
    setRole('patient');
    setMobile(demoMobile);
    setName(demoName);
  };

  return (
    <div style={{
      minHeight: '70vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem 1rem'
    }}>
      {/* Centered Sign In Card */}
      <div className="card" style={{
        maxWidth: '440px',
        width: '100%',
        margin: '0 auto',
        boxShadow: 'var(--shadow-card)',
        borderRadius: '8px',
        padding: '2.25rem 2rem',
        border: '1px solid var(--border)',
        background: '#ffffff'
      }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div style={{
            background: 'var(--navy-light)',
            color: 'var(--coral)',
            width: '44px',
            height: '44px',
            borderRadius: '6px',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '0.75rem',
            border: '1px solid rgba(244, 237, 224, 0.15)'
          }}>
            <Eye size={22} />
          </div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--navy)', letterSpacing: '-0.015em' }}>
            Sign In to NetraCare
          </h2>
          <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            Select your clinical role to access your workspace
          </p>
        </div>

        {/* Role Tabs */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          background: 'var(--cream-surface)',
          padding: '4px',
          borderRadius: '6px',
          gap: '4px',
          marginBottom: '1.5rem',
          border: '1px solid var(--border)'
        }}>
          <button
            type="button"
            onClick={() => setRole('patient')}
            style={{
              padding: '8px 4px',
              borderRadius: '4px',
              fontWeight: 600,
              fontSize: '0.82rem',
              background: role === 'patient' ? 'var(--navy)' : 'transparent',
              color: role === 'patient' ? 'var(--cream-text)' : 'var(--text-muted)',
              border: role === 'patient' ? '1px solid var(--navy)' : '1px solid transparent',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px'
            }}
          >
            <User size={14} color={role === 'patient' ? 'var(--cream-text)' : 'var(--text-muted)'} /> Patient
          </button>
          <button
            type="button"
            onClick={() => setRole('doctor')}
            style={{
              padding: '8px 4px',
              borderRadius: '4px',
              fontWeight: 600,
              fontSize: '0.82rem',
              background: role === 'doctor' ? 'var(--navy)' : 'transparent',
              color: role === 'doctor' ? 'var(--cream-text)' : 'var(--text-muted)',
              border: role === 'doctor' ? '1px solid var(--navy)' : '1px solid transparent',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px'
            }}
          >
            <Stethoscope size={14} color={role === 'doctor' ? 'var(--cream-text)' : 'var(--text-muted)'} /> Doctor
          </button>
          <button
            type="button"
            onClick={() => setRole('staff')}
            style={{
              padding: '8px 4px',
              borderRadius: '4px',
              fontWeight: 600,
              fontSize: '0.82rem',
              background: role === 'staff' ? 'var(--navy)' : 'transparent',
              color: role === 'staff' ? 'var(--cream-text)' : 'var(--text-muted)',
              border: role === 'staff' ? '1px solid var(--navy)' : '1px solid transparent',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px'
            }}
          >
            <ShieldCheck size={14} color={role === 'staff' ? 'var(--cream-text)' : 'var(--text-muted)'} /> Staff
          </button>
        </div>

        {error && (
          <div className="alert alert-danger" style={{ marginBottom: '1.15rem', padding: '0.75rem 0.9rem', borderRadius: '6px' }}>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {role === 'patient' && (
            <div style={{ display: 'grid', gap: '1.15rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--navy)', marginBottom: '0.4rem' }}>
                  Mobile Number (10 digits)
                </label>
                <input
                  type="text"
                  required
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value)}
                  placeholder="e.g. 9000000001"
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    outline: 'none',
                    fontSize: '0.92rem',
                    color: 'var(--navy)',
                    background: '#ffffff'
                  }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.35rem' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Prefilled demo profile:
                  </span>
                  <button
                    type="button"
                    onClick={() => handleQuickDemoPatient('9000000001', 'Asha Verma')}
                    style={{ fontSize: '0.76rem', color: 'var(--navy)', fontWeight: 600, textDecoration: 'underline' }}
                  >
                    Asha Verma (9000000001)
                  </button>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--navy)', marginBottom: '0.4rem' }}>
                  Patient Full Name
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Asha Verma"
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    outline: 'none',
                    fontSize: '0.92rem',
                    color: 'var(--navy)',
                    background: '#ffffff'
                  }}
                />
              </div>
            </div>
          )}

          {role === 'doctor' && (
            <div style={{ display: 'grid', gap: '1.15rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--navy)', marginBottom: '0.4rem' }}>
                  Select Doctor Workspace
                </label>
                <select
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    background: '#ffffff',
                    outline: 'none',
                    fontSize: '0.92rem',
                    fontWeight: 500,
                    color: 'var(--navy)'
                  }}
                >
                  {doctors.map(d => (
                    <option key={d.doctor_id} value={d.doctor_id}>
                      {d.name} ({d.specialities.join(', ')})
                    </option>
                  ))}
                </select>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginTop: '0.35rem' }}>
                  Access daily consultation queues, clinical summaries, and patient notes.
                </span>
              </div>
            </div>
          )}

          {role === 'staff' && (
            <div style={{ display: 'grid', gap: '1.15rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--navy)', marginBottom: '0.4rem' }}>
                  Staff / Receptionist Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Clinic Receptionist"
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    outline: 'none',
                    fontSize: '0.92rem',
                    color: 'var(--navy)',
                    background: '#ffffff'
                  }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginTop: '0.35rem' }}>
                  Administrative access for walk-in booking and 2-hour cancellations.
                </span>
              </div>
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{
              width: '100%',
              marginTop: '1.5rem',
              padding: '0.8rem',
              fontSize: '0.95rem',
              borderRadius: '6px',
              fontWeight: 600
            }}
          >
            {loading ? 'Entering Clinic...' : 'Continue to Workspace'} <ArrowRight size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
