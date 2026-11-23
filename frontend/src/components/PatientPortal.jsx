import heroEyeImg from "../assets/hero.jpg";
import React, { useState, useEffect } from 'react';
import { api } from '../api';
import PatientChat from './PatientChat';
import {
  Calendar,
  Clock,
  AlertCircle,
  CheckCircle2,
  User,
  ChevronRight,
  XCircle,
  RefreshCw,
  Sparkles,
  AlertTriangle,
  Stethoscope,
  Activity,
  ShieldAlert,
  ShieldCheck,
  ArrowRight,
  Eye,
  Sliders,
  Check,
  Building,
  Video,
  FlaskConical,
  FileText,
  Bot,
  HelpCircle,
  ChevronDown,
  ThumbsUp,
  Copy
} from 'lucide-react';

export default function PatientPortal({ user }) {
  const [appointments, setAppointments] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [specialities, setSpecialities] = useState([]);

  // Fact of the Day state (R5)
  const [factOfTheDay, setFactOfTheDay] = useState('');
  const [factCaveat, setFactCaveat] = useState('General information, not medical advice');
  const [factLoading, setFactLoading] = useState(false);

  // Booking form state
  const [selectedSpeciality, setSelectedSpeciality] = useState('');
  const [selectedDoctorId, setSelectedDoctorId] = useState('');
  const [selectedDate, setSelectedDate] = useState(() => {
    // Tomorrow as sensible default
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
  });
  const [visitType, setVisitType] = useState('new');
  const [availableSlots, setAvailableSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState('');
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [visitReason, setVisitReason] = useState('');

  // Status feedback & Red Flag Emergency Notice (R4)
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [emergencyNotice, setEmergencyNotice] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // Full-screen Chat Assistant Modal state
  const [isChatOpen, setIsChatOpen] = useState(false);

  // Interactive Clinical Insight states
  const [showDoctorTip, setShowDoctorTip] = useState(false);
  const [helpfulCount, setHelpfulCount] = useState(142);
  const [hasLikedInsight, setHasLikedInsight] = useState(false);
  const [copiedInsight, setCopiedInsight] = useState(false);
  const [activeInsightTopic, setActiveInsightTopic] = useState('all');

  // FAQ accordion state
  const [openFaq, setOpenFaq] = useState(0);

  const faqItems = [
    {
      q: 'How do I book an appointment with an ophthalmologist at NetraCare?',
      a: 'Select your required eye speciality and doctor from the "Schedule a Consultation" panel on this page. Choose an available date, select whether it is a New Consultation (20 mins) or Follow-up (10 mins), pick your time slot, provide a brief reason for visit, and click Book. You can also launch our AI Assistant anytime to check availability and book via conversation.'
    },
    {
      q: 'What is the clinic 2-hour cancellation and rescheduling rule?',
      a: 'Under NetraCare clinic rules, cancellations and reschedules submitted more than 2 hours prior to the slot are processed automatically. Requests submitted within the 2-hour window are forwarded directly to the Clinic Receptionist late-change queue for manual staff approval to protect doctor clinical utilization.'
    },
    {
      q: 'What happens if I experience an eye emergency or chemical injury?',
      a: 'If chemical cleaner or foreign substance splashes in your eye, flush immediately with copious clean water for at least 15 minutes. Our AI Assistant and booking engine actively monitor all patient descriptions for clinical red flags (such as chemical burns, sudden vision loss, severe acute pain, or trauma) and immediately route emergency alerts to our 24/7 Red Flag Clinic Triage Desk.'
    },
    {
      q: 'Am I eligible for LASIK laser refractive surgery?',
      a: 'General eligibility requires being 18 years or older, having a stable refractive error (spectacle prescription) for at least 12 months, adequate corneal thickness, and no active corneal pathology, glaucoma, or severe dry eye. You can start your LASIK pre-assessment questionnaire through our AI Assistant to review candidacy guidelines before your clinical topography scan.'
    },
    {
      q: 'What is the difference between a New Visit (20 min) and a Follow-up (10 min)?',
      a: 'A New Visit is a comprehensive 20-minute consultation for first-time evaluations, sudden symptoms, or new diagnoses requiring full slit-lamp examination and dilated fundus check. A Follow-up is a focused 10-minute review for patients who have already seen that specialist and are returning for post-op check-ups, medication reviews, or pressure monitoring.'
    },
    {
      q: 'Where can I access my consultation clinical notes and doctor advice?',
      a: 'Once your doctor completes your consultation, clinical visit notes, diagnoses, and follow-up recommendations are permanently recorded in your electronic medical file. Our AI Assistant can also answer questions regarding your post-consultation recovery care plan.'
    }
  ];

  const handleCopyInsight = () => {
    const textToCopy = `${factOfTheDay || 'The human eye can distinguish approximately 10 million different colors.'} — NetraCare Clinical Insights`;
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(textToCopy);
    }
    setCopiedInsight(true);
    setTimeout(() => setCopiedInsight(false), 2200);
  };

  const handleLikeInsight = () => {
    if (!hasLikedInsight) {
      setHelpfulCount(prev => prev + 1);
      setHasLikedInsight(true);
    } else {
      setHelpfulCount(prev => prev - 1);
      setHasLikedInsight(false);
    }
  };

  const scrollToBooking = (docId = null, spec = null) => {
    if (docId) setSelectedDoctorId(docId);
    if (spec) setSelectedSpeciality(spec);
    const el = document.getElementById('section-booking');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const specialityDescriptions = {
    'Cataract': 'Micro-incision cataract surgery (MICS) with advanced monofocal, toric & multifocal intraocular lens implants.',
    'Cornea': 'Specialized clinical evaluation and therapy for corneal dystrophies, infections, and dry eye syndromes.',
    'Glaucoma': 'Comprehensive intraocular pressure monitoring, visual field assessments, and optic nerve preservation.',
    'Retina': 'Advanced diagnostic and therapeutic care for diabetic retinopathy, retinal tears, and macular health.',
    'Pediatric': 'Gentle, child-friendly eye examinations, amblyopia management, and pediatric strabismus review.',
    'Refractive': 'High-precision LASIK pre-assessment scans, corneal topography, and laser vision correction screening.'
  };

  const getDoctorMeta = (name) => {
    if (name.includes('Anand')) return { exp: '14+ Yrs Exp', title: 'Senior Cataract & Cornea Surgeon' };
    if (name.includes('Priya')) return { exp: '11+ Yrs Exp', title: 'Consultant Retina & Vitreous Specialist' };
    if (name.includes('Rajesh')) return { exp: '16+ Yrs Exp', title: 'Senior Glaucoma & Anterior Segment Specialist' };
    if (name.includes('Sunita')) return { exp: '9+ Yrs Exp', title: 'Pediatric Ophthalmologist & Strabismus Surgeon' };
    return { exp: '10+ Yrs Exp', title: 'Consultant Ophthalmologist' };
  };

  // Load patient appointments & master data
  const loadAppointments = async () => {
    try {
      const data = await api.getAppointments();
      setAppointments(data);
    } catch (err) {
      console.error('Failed to load appointments', err);
    }
  };

  const loadFact = async (prev = null) => {
    setFactLoading(true);
    try {
      const res = await api.getFactOfTheDay(prev);
      setFactOfTheDay(res.fact);
      if (res.caveat) setFactCaveat(res.caveat);
    } catch (err) {
      console.error('Failed to fetch fact of the day', err);
    } finally {
      setFactLoading(false);
    }
  };

  useEffect(() => {
    loadAppointments();
    loadFact();

    api.getDoctors().then(docs => {
      setDoctors(docs);
      if (docs.length > 0) {
        setSelectedDoctorId(docs[0].doctor_id);
      }
    });

    api.getSpecialities().then(specs => {
      setSpecialities(specs);
      if (specs.length > 0) {
        setSelectedSpeciality(specs[0]);
      }
    });
  }, []);

  // Filter doctors covering selected speciality
  const eligibleDoctors = doctors.filter(d => 
    !selectedSpeciality || d.specialities.map(s => s.toLowerCase()).includes(selectedSpeciality.toLowerCase())
  );

  // Ensure selected doctor is valid for the chosen speciality
  useEffect(() => {
    if (eligibleDoctors.length > 0) {
      if (!eligibleDoctors.find(d => d.doctor_id === selectedDoctorId)) {
        setSelectedDoctorId(eligibleDoctors[0].doctor_id);
      }
    } else {
      setSelectedDoctorId('');
    }
  }, [selectedSpeciality, eligibleDoctors]);

  // Fetch free slots when doctor, date, or visitType changes
  useEffect(() => {
    if (!selectedDoctorId || !selectedDate) {
      setAvailableSlots([]);
      return;
    }
    setSlotsLoading(true);
    setSelectedSlot('');
    setErrorMsg('');

    api.getFreeSlots(selectedDoctorId, selectedDate, visitType)
      .then(res => {
        setAvailableSlots(res.slots || []);
      })
      .catch(err => {
        setAvailableSlots([]);
      })
      .finally(() => {
        setSlotsLoading(false);
      });
  }, [selectedDoctorId, selectedDate, visitType]);

  const handleBook = async () => {
    if (!selectedSlot) return;
    setErrorMsg('');
    setSuccessMsg('');
    setEmergencyNotice('');

    // R3: Validate reason
    const cleanReason = visitReason.trim();
    if (!cleanReason) {
      setErrorMsg('Please state the reason for your visit (up to 300 characters).');
      return;
    }
    if (cleanReason.length > 300) {
      setErrorMsg('Reason must be 300 characters or less.');
      return;
    }

    setActionLoading(true);

    try {
      const res = await api.createAppointment({
        doctor_id: selectedDoctorId,
        speciality: selectedSpeciality,
        visit_type: visitType,
        date: selectedDate,
        start_time: selectedSlot,
        reason: cleanReason
      });

      // Check if red-flag emergency message returned
      if (res.emergency_message) {
        setEmergencyNotice(res.emergency_message);
      }

      setSuccessMsg(`Appointment booked successfully! Ref: ${res.appointment_id}`);
      setSelectedSlot('');
      setVisitReason('');
      loadAppointments();
      // Refresh slots
      api.getFreeSlots(selectedDoctorId, selectedDate, visitType).then(r => setAvailableSlots(r.slots || []));
    } catch (err) {
      const detail = err.detail;
      // R4: Emergency response message on refusal
      if (typeof detail === 'object') {
        if (detail.emergency_message) {
          setEmergencyNotice(detail.emergency_message);
        }
        if (detail.message) {
          setErrorMsg(`${detail.reason_code ? `[${detail.reason_code}] ` : ''}${detail.message}`);
        } else {
          setErrorMsg('Booking was refused by clinic rules.');
        }
      } else {
        setErrorMsg(detail || 'Booking was refused by clinic rules.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async (apptId) => {
    if (!window.confirm('Are you sure you want to cancel this appointment?')) return;
    setErrorMsg('');
    setSuccessMsg('');

    try {
      const res = await api.cancelAppointment(apptId);
      if (res.outcome === 'to_staff' || res.approval_status) {
        setSuccessMsg('Your cancellation request is within 2 hours and has been sent to Staff for approval. It remains booked until approved.');
      } else {
        setSuccessMsg('Appointment cancelled successfully.');
      }
      loadAppointments();
      if (selectedDoctorId && selectedDate) {
        api.getFreeSlots(selectedDoctorId, selectedDate, visitType).then(r => setAvailableSlots(r.slots || []));
      }
    } catch (err) {
      const detail = err.detail;
      if (typeof detail === 'object' && detail?.message) {
        setErrorMsg(`${detail.reason_code ? `[${detail.reason_code}] ` : ''}${detail.message}`);
      } else {
        setErrorMsg(detail || 'Could not cancel appointment.');
      }
    }
  };

  const activeBookings = appointments.filter(a => a.status === 'booked');
  const pastBookings = appointments.filter(a => a.status !== 'booked');

  return (
    <div style={{ display: 'grid', gap: '2.5rem' }}>
      
      {/* 1. Ophthalmology Hero Section */}
      <div id="section-hero" className="ref-hero-banner" style={{
        display: 'grid',
        gridTemplateColumns: '1.2fr 0.8fr',
        gap: '2rem',
        alignItems: 'center'
      }}>
        <div style={{ display: 'grid', gap: '1.15rem' }}>
          <div className="ref-eyebrow" style={{ color: '#D4C5B0' }}>
            <Activity size={14} color="#D4C5B0" /> Specialized Eye Care & Surgical Center
          </div>
          <h1 style={{
            fontSize: '2.25rem',
            fontWeight: 700,
            color: 'var(--cream-text)',
            lineHeight: 1.2,
            letterSpacing: '-0.025em',
            margin: 0
          }}>
            Advanced Ophthalmology & Precision Clinical Care
          </h1>
          <p style={{
            fontSize: '1rem',
            color: 'var(--cream-text)',
            opacity: 0.9,
            lineHeight: 1.6,
            maxWidth: '540px',
            margin: 0,
            fontWeight: 400
          }}>
            NetraCare is a safety-governed ophthalmology clinical center connecting patients with board-certified eye specialists, real-time OPD slot discovery, and 24/7 AI-guided clinical assistance for cornea, cataract, LASIK, and retina care.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', flexWrap: 'wrap', marginTop: '0.35rem' }}>
            <button
              type="button"
              onClick={() => scrollToBooking()}
              className="btn btn-primary"
              style={{ padding: '0.75rem 1.5rem', fontSize: '0.92rem', fontWeight: 600, background: '#FFFFFF', color: 'var(--navy)', border: '1px solid #FFFFFF' }}
            >
              <Calendar size={16} /> Schedule Consultation
            </button>
            <button
              type="button"
              onClick={() => setIsChatOpen(true)}
              className="btn btn-ghost-light"
              style={{ padding: '0.75rem 1.45rem', fontSize: '0.92rem', fontWeight: 500 }}
            >
              <Bot size={17} /> Ask AI Assistant 24/7
            </button>
          </div>
        </div>

        {/* Right Column: Hero Eye Image */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          position: 'relative',
          width: '100%',
          overflow: 'hidden'
        }} className="desktop-hero-visual">
          <img
            src={heroEyeImg}
            alt="NetraCare Ophthalmology Eye Examination"
            className="hero-eye-img"
          />
        </div>
      </div>

      {/* 2. Key Selling Points Strip - De-boxed, spacious & elegant */}
      <div className="ref-strip-grid">
        <div className="ref-strip-card">
          <div className="ref-icon-badge">
            <Eye size={22} />
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, color: 'var(--navy)', fontSize: '1.05rem' }}>
              Advanced Diagnostics
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              Slit-lamp & topography precision
            </div>
          </div>
        </div>

        <div className="ref-strip-card">
          <div className="ref-icon-badge">
            <Stethoscope size={22} />
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, color: 'var(--navy)', fontSize: '1.05rem' }}>
              Expert Ophthalmologists
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              6 surgical sub-specialities
            </div>
          </div>
        </div>

        <div className="ref-strip-card">
          <div className="ref-icon-badge">
            <ShieldAlert size={22} />
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, color: 'var(--navy)', fontSize: '1.05rem' }}>
              Red-Flag Safety Triage
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              Immediate emergency screening
            </div>
          </div>
        </div>

        <div className="ref-strip-card">
          <div className="ref-icon-badge">
            <Clock size={22} />
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, color: 'var(--navy)', fontSize: '1.05rem' }}>
              Governed OPD Slots
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              10m & 20m instant OPD bookings
            </div>
          </div>
        </div>
      </div>

      {/* 3. Specialized Services Grid */}
      <div id="section-services" style={{ display: 'grid', gap: '1.5rem', marginTop: '0.5rem' }}>
        <div>
          <div className="ref-eyebrow">
            <Activity size={14} /> Our Care Specialities
          </div>
          <h2 className="ref-section-title">
            Comprehensive Eye Care Services
          </h2>
          <p className="ref-section-sub">
            Sub-speciality clinics equipped for advanced diagnostic evaluations and microsurgical interventions
          </p>
        </div>

        <div className="ref-services-grid">
          {specialities.map((spec) => (
            <div
              key={spec}
              className="ref-service-card"
              onClick={() => scrollToBooking(null, spec)}
              title={`Click to book consultation for ${spec}`}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <div className="ref-icon-badge">
                    {spec === 'Cataract' && <Eye size={20} />}
                    {spec === 'Cornea' && <Sparkles size={20} />}
                    {spec === 'Glaucoma' && <Activity size={20} />}
                    {spec === 'Retina' && <Stethoscope size={20} />}
                    {spec === 'Pediatric' && <User size={20} />}
                    {spec === 'Refractive' && <CheckCircle2 size={20} />}
                  </div>
                  <span className="badge badge-primary">Active Clinic</span>
                </div>

                <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--navy)', margin: '0 0 0.45rem 0' }}>
                  {spec} {spec !== 'Cataract' && spec !== 'Glaucoma' && spec !== 'Retina' && spec !== 'Pediatric' ? 'Care' : 'Clinic'}
                </h3>
                <p style={{ fontSize: '0.92rem', color: 'var(--text-muted)', lineHeight: 1.6, margin: 0 }}>
                  {specialityDescriptions[spec] || 'Specialized diagnostic consultations, imaging, and personalized clinical treatment plans.'}
                </p>
              </div>

              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderTop: '1px solid var(--border-light)',
                paddingTop: '0.85rem',
                marginTop: '0.75rem'
              }}>
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--navy)' }}>
                  Schedule for {spec}
                </span>
                <ChevronRight size={16} color="var(--navy)" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 4. Meet Our Specialist Ophthalmologists */}
      <div id="section-doctors" style={{ display: 'grid', gap: '1.5rem', marginTop: '0.5rem' }}>
        <div>
          <div className="ref-eyebrow">
            <Stethoscope size={14} /> Clinical Excellence
          </div>
          <h2 className="ref-section-title">
            Our Specialist Ophthalmologists
          </h2>
          <p className="ref-section-sub">
            Consult with our dedicated eye surgeons across scheduled OPD consultation hours
          </p>
        </div>

        <div className="ref-doctors-grid">
          {doctors.map((doc) => {
            const meta = getDoctorMeta(doc.name);
            const initials = doc.name.replace('Dr.', '').trim().split(' ').map(n => n[0]).slice(0, 2).join('');
            return (
              <div key={doc.doctor_id} className="ref-doctor-card">
                <div style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '6px',
                  background: 'var(--navy-light)',
                  border: '1px solid rgba(244, 237, 224, 0.2)',
                  color: 'var(--cream-text)',
                  fontSize: '1.25rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1rem'
                }}>
                  {initials}
                </div>

                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--navy)', margin: '0 0 0.25rem 0' }}>
                  {doc.name}
                </h3>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 400, marginBottom: '0.85rem' }}>
                  {meta.title}
                </div>

                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', justifyContent: 'center', marginBottom: '1.25rem' }}>
                  {doc.specialities.map(s => (
                    <span key={s} className="badge badge-cream" style={{ fontSize: '0.78rem' }}>
                      {s}
                    </span>
                  ))}
                  <span className="badge badge-neutral" style={{ fontSize: '0.78rem' }}>
                    {meta.exp}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => scrollToBooking(doc.doctor_id, doc.specialities[0])}
                  className="btn btn-secondary btn-sm"
                  style={{ width: '100%', borderColor: 'var(--navy)', color: 'var(--navy)', fontWeight: 600, borderRadius: '6px', padding: '0.6rem 1rem' }}
                >
                  <Calendar size={15} color="var(--navy)" /> Book Consultation
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* 5. Clinical Insight of the Day - De-boxed, clean & spacious */}
      <div id="section-fact" style={{
        padding: '2rem 2.25rem',
        background: '#ffffff',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        display: 'grid',
        gap: '1.25rem',
        marginTop: '0.5rem'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <div style={{
              background: 'var(--cream-surface)',
              border: '1px solid var(--border)',
              color: 'var(--navy)',
              width: '42px',
              height: '42px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Sparkles size={20} />
            </div>
            <div>
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block' }}>
                Ophthalmic Clinical Note
              </span>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--navy)', margin: 0, letterSpacing: '-0.015em' }}>
                Clinical Insight of the Day
              </h3>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => loadFact(factOfTheDay)}
              disabled={factLoading}
              className="btn btn-primary btn-sm"
              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', padding: '0.55rem 1.1rem', borderRadius: '6px' }}
              title="Fetch new clinical fact"
            >
              <RefreshCw size={14} className={factLoading ? 'spin' : ''} />
              Next Insight
            </button>
            <button
              type="button"
              onClick={handleCopyInsight}
              className="btn btn-secondary btn-sm"
              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', padding: '0.55rem 1rem', borderRadius: '6px' }}
              title="Copy insight text"
            >
              {copiedInsight ? <Check size={14} color="var(--navy)" /> : <Copy size={14} />}
              {copiedInsight ? 'Copied' : 'Copy'}
            </button>
            <button
              type="button"
              onClick={handleLikeInsight}
              className="btn btn-secondary btn-sm"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.86rem',
                padding: '0.55rem 1rem',
                background: hasLikedInsight ? 'var(--cream-surface)' : '#ffffff',
                borderColor: 'var(--border)',
                color: 'var(--navy)',
                borderRadius: '6px'
              }}
              title="Helpful insight"
            >
              <ThumbsUp size={14} color={hasLikedInsight ? 'var(--navy)' : 'var(--text-muted)'} />
              Helpful ({helpfulCount})
            </button>
          </div>
        </div>

        {/* Insight Statement */}
        <div style={{
          background: 'var(--cream-surface)',
          borderRadius: '6px',
          padding: '1.5rem 1.75rem',
          borderLeft: '4px solid var(--navy)'
        }}>
          <p style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '1.2rem',
            color: 'var(--navy)',
            fontWeight: 600,
            lineHeight: 1.55,
            margin: '0 0 0.5rem 0'
          }}>
            "{factLoading ? 'Consulting ophthalmology clinical knowledge base...' : (factOfTheDay || 'The human eye can distinguish approximately 10 million different colors.')}"
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--coral)' }} />
            <span>{factCaveat}</span>
          </div>
        </div>

        {/* Expandable Doctor's Eye Care Tip */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
          <button
            type="button"
            onClick={() => setShowDoctorTip(!showDoctorTip)}
            className="btn btn-secondary btn-sm"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.85rem',
              fontWeight: 500,
              padding: '0.5rem 0.95rem',
              borderRadius: '6px'
            }}
          >
            <Stethoscope size={14} color="var(--navy)" />
            {showDoctorTip ? 'Hide Specialist Protocol' : 'Show Specialist Practical Protocol (20-20-20 Rule)'}
          </button>
          <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            Reviewed by NetraCare Clinical Quality Board
          </span>
        </div>

        {showDoctorTip && (
          <div style={{
            background: 'var(--cream-surface)',
            borderRadius: '6px',
            padding: '1.25rem 1.5rem',
            border: '1px solid var(--border)',
            display: 'grid',
            gap: '0.5rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--navy)', fontWeight: 600, fontSize: '0.95rem' }}>
              <Eye size={16} color="var(--navy)" /> Specialist Daily Eye Care Protocol:
            </div>
            <p style={{ fontSize: '0.92rem', color: 'var(--text-body)', margin: 0, lineHeight: 1.65 }}>
              • <b>Digital Screen Strain (20-20-20 Rule):</b> Every 20 minutes of screen exposure, shift your gaze to an object 20 feet away for at least 20 seconds to relax your ciliary accommodation muscles.<br />
              • <b>Blinking & Lubrication:</b> We blink 66% less frequently while staring at screens. Deliberately blink fully to replenish the tear film lipid layer.<br />
              • <b>UV Protection:</b> Always wear 100% UV400-rated sunglasses outdoors to prevent premature lens cataract formation and corneal photokeratitis.
            </p>
          </div>
        )}
      </div>

      {/* 3. Emergency Notice Banner (R4) */}
      {emergencyNotice && (
        <div style={{
          background: '#fef2f2',
          border: '1px solid #ef4444',
          borderRadius: '6px',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'flex-start',
          boxShadow: 'var(--shadow-xs)'
        }}>
          <div style={{
            background: '#ef4444',
            color: '#fff',
            padding: '8px',
            borderRadius: '6px',
            flexShrink: 0,
            marginTop: '2px'
          }}>
            <AlertTriangle size={20} />
          </div>
          <div>
            <div style={{ fontWeight: 600, color: '#b91c1c', fontSize: '1.05rem', marginBottom: '0.25rem' }}>
              Urgent Medical Attention Required (Red Flag Protocol)
            </div>
            <p style={{ color: '#991b1b', fontSize: '0.95rem', fontWeight: 500, lineHeight: 1.5 }}>
              {emergencyNotice}
            </p>
          </div>
        </div>
      )}

      {/* Global Alerts */}
      {errorMsg && (
        <div className="alert alert-danger" style={{ display: 'flex', alignItems: 'center', borderRadius: '6px' }}>
          <AlertCircle size={18} style={{ flexShrink: 0 }} />
          <div><b>Booking / Rule Refusal:</b> {errorMsg}</div>
        </div>
      )}
      {successMsg && (
        <div className="alert alert-success" style={{ display: 'flex', alignItems: 'center', borderRadius: '6px' }}>
          <CheckCircle2 size={18} style={{ flexShrink: 0 }} />
          <div>{successMsg}</div>
        </div>
      )}

      {/* 6. Chat Assistant Launcher Banner */}
      <div id="section-chat-launcher" className="ref-hero-banner" style={{
        padding: '2rem 2.25rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '1.5rem',
        borderRadius: 'var(--radius-lg)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.15rem' }}>
          <div style={{
            width: '46px',
            height: '46px',
            borderRadius: '6px',
            background: 'var(--navy-light)',
            color: 'var(--cream-text)',
            border: '1px solid rgba(244, 237, 224, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <Bot size={24} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0, color: 'var(--cream-text)' }}>
                NetraCare Clinical Assistant
              </h3>
              <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.12)', color: 'var(--cream-text)', border: '1px solid rgba(244, 237, 224, 0.2)', fontWeight: 600, borderRadius: '4px' }}>
                Online 24/7
              </span>
            </div>
            <p style={{ margin: '4px 0 0 0', color: 'var(--cream-text)', opacity: 0.9, fontSize: '0.9rem', maxWidth: '620px', lineHeight: 1.5 }}>
              Have questions about your eye symptoms, doctor schedules, or LASIK candidacy? Launch our full-screen AI clinical companion to chat in real-time with human confirmation.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsChatOpen(true)}
          className="btn btn-primary"
          style={{
            fontWeight: 600,
            fontSize: '0.92rem',
            padding: '0.75rem 1.45rem',
            background: '#FFFFFF',
            color: 'var(--navy)',
            border: '1px solid #FFFFFF',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: 'pointer'
          }}
        >
          Open Clinical Assistant
          <ArrowRight size={16} />
        </button>
      </div>

      {/* Floating Chat Assistant Button (Always Accessible) */}
      <button
        type="button"
        onClick={() => setIsChatOpen(true)}
        style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          zIndex: 80,
          background: 'var(--navy)',
          color: 'var(--cream-text)',
          border: '1px solid rgba(244, 237, 224, 0.25)',
          borderRadius: '6px',
          padding: '0.75rem 1.25rem',
          boxShadow: 'var(--shadow-elevated)',
          display: 'flex',
          alignItems: 'center',
          gap: '9px',
          fontWeight: 600,
          fontSize: '0.88rem',
          cursor: 'pointer'
        }}
        title="Open Clinical AI Chat Assistant"
      >
        <Bot size={18} color="var(--cream-text)" />
        <span>Clinical Assistant</span>
        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--coral)' }} />
      </button>

      {/* Fullscreen Chat Assistant Modal */}
      {isChatOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(20, 33, 61, 0.8)',
          backdropFilter: 'blur(10px)',
          WebkitBackdropFilter: 'blur(10px)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '1.25rem',
          boxSizing: 'border-box'
        }}>
          <div style={{
            width: '100%',
            maxWidth: '1200px',
            height: '92vh',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <PatientChat
              user={user}
              onAppointmentChange={loadAppointments}
              isFullScreen={true}
              onClose={() => setIsChatOpen(false)}
            />
          </div>
        </div>
      )}

      {/* 7. Main Grid: "Your Consultations" (Left) & Schedule Appointment (Right) */}
      <div className="patient-main-grid">
        
        {/* Left Column: Your Consultations & History */}
        <div style={{ display: 'grid', gap: '1.5rem' }}>
          
          <div id="section-appointments" className="card">
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1.15rem',
              borderBottom: '1px solid var(--border-light)',
              paddingBottom: '0.75rem'
            }}>
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--navy)' }}>
                  <Calendar size={18} color="var(--navy)" /> Your Consultations
                </h3>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Scheduled doctor appointments and ophthalmic reviews
                </span>
              </div>
              <span className="badge badge-primary">
                {activeBookings.length} Active
              </span>
            </div>

            {activeBookings.length === 0 ? (
              <div style={{
                textAlign: 'center',
                padding: '2rem 1rem',
                color: 'var(--text-muted)',
                background: 'var(--cream-surface)',
                borderRadius: '6px',
                border: '1px dashed var(--border)'
              }}>
                <Calendar size={32} style={{ opacity: 0.35, marginBottom: '0.5rem', color: 'var(--navy)' }} />
                <p style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--navy)' }}>No upcoming consultations scheduled</p>
                <p style={{ fontSize: '0.8rem', marginTop: '0.2rem' }}>Book a slot with our specialists on the right or ask the clinical assistant.</p>
              </div>
            ) : (
              <div style={{ display: 'grid', gap: '0.75rem' }}>
                {activeBookings.map(a => (
                  <div key={a.appointment_id} style={{
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    padding: '1.15rem',
                    background: '#ffffff',
                    boxShadow: 'var(--shadow-xs)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '1rem'
                  }}>
                    <div style={{ display: 'grid', gap: '0.35rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <span className="badge badge-primary">{a.speciality}</span>
                        <span className="badge badge-neutral">
                          {a.visit_type === 'new' ? 'New (20m)' : 'Follow-up (10m)'}
                        </span>
                        {a.approval_status && (
                          <span className="badge badge-warning" style={{ fontWeight: 600 }}>
                            {a.approval_status === 'cancel_pending' ? 'Cancellation Pending Staff Review' : 'Reschedule Pending Staff Review'}
                          </span>
                        )}
                      </div>

                      <div style={{ fontWeight: 600, fontSize: '1.05rem', color: 'var(--navy)' }}>
                        {a.doctor_name}
                      </div>

                      <div style={{
                        fontSize: '0.84rem',
                        color: 'var(--text-muted)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        fontWeight: 500
                      }}>
                        <Clock size={14} color="var(--navy)" />
                        <span style={{ color: 'var(--navy)' }}>{a.appointment_date}</span>
                        <span>•</span>
                        <span>{a.start_time} - {a.end_time}</span>
                      </div>

                      {a.reason && (
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                          Reason: "{a.reason}"
                        </div>
                      )}
                    </div>

                    <button
                      onClick={() => handleCancel(a.appointment_id)}
                      className="btn btn-danger btn-sm"
                      title="Cancel consultation"
                      style={{ flexShrink: 0, padding: '0.45rem 0.85rem', borderRadius: '6px' }}
                    >
                      Cancel Visit
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Past History Timeline */}
          {pastBookings.length > 0 && (
            <div className="card">
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: '0.85rem', color: 'var(--navy)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Clock size={16} color="var(--navy)" /> Past Consultation Records ({pastBookings.length})
              </h3>
              <div style={{ display: 'grid', gap: '0.5rem' }}>
                {pastBookings.slice(0, 5).map(a => (
                  <div key={a.appointment_id} style={{
                    fontSize: '0.86rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.65rem 0.25rem',
                    borderBottom: '1px solid var(--border-light)'
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--navy)' }}>
                        {a.speciality} with {a.doctor_name}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                        {a.appointment_date} at {a.start_time}
                      </div>
                    </div>
                    <div>
                      <span className={`badge ${a.status === 'completed' ? 'badge-primary' : 'badge-neutral'}`}>
                        {a.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Clinic Guidelines & Timing Notice */}
          <div style={{
            background: 'var(--cream-surface)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            padding: '1.25rem',
            display: 'grid',
            gap: '0.45rem'
          }}>
            <div style={{ fontWeight: 600, color: 'var(--navy)', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <ShieldCheck size={16} color="var(--navy)" /> Clinic Consultation Standards
            </div>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-body)', margin: 0, lineHeight: 1.55 }}>
              • <b>New Visits:</b> Allocated 20 minutes for full slit-lamp & dilated evaluation.<br />
              • <b>Follow-ups:</b> Focused 10-minute progress checks and IOP monitoring.<br />
              • <b>2-Hour Cancellation Rule:</b> Automatic cancellation is accepted up to 2 hours prior to your scheduled slot. Inside 2 hours, requests go to Clinic Staff approval.
            </p>
          </div>
        </div>

        {/* Right Column: Schedule an Appointment Form */}
        <div id="section-booking" className="card" style={{ padding: '2rem 2.25rem' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1.25rem',
            borderBottom: '1px solid var(--border-light)',
            paddingBottom: '0.85rem'
          }}>
            <div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.65rem', color: 'var(--navy)' }}>
                <Clock size={20} color="var(--navy)" /> Schedule Consultation
              </h3>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                OPD appointment booking engine
              </span>
            </div>
            <span className="badge badge-primary">
              Live Engine
            </span>
          </div>

          <div style={{ display: 'grid', gap: '1.25rem' }}>
            
            {/* Step 1: Speciality */}
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: 'var(--navy)', marginBottom: '0.45rem' }}>
                1. Select Eye Speciality
              </label>
              <select
                value={selectedSpeciality}
                onChange={(e) => setSelectedSpeciality(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: '#fff',
                  outline: 'none',
                  fontWeight: 400,
                  fontSize: '15px',
                  color: 'var(--navy)'
                }}
              >
                {specialities.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            {/* Step 2: Doctor */}
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: 'var(--navy)', marginBottom: '0.45rem' }}>
                2. Select Ophthalmologist
              </label>
              <select
                value={selectedDoctorId}
                onChange={(e) => setSelectedDoctorId(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: '#fff',
                  outline: 'none',
                  fontWeight: 400,
                  fontSize: '15px',
                  color: 'var(--navy)'
                }}
              >
                {eligibleDoctors.map(d => (
                  <option key={d.doctor_id} value={d.doctor_id}>
                    {d.name} ({d.specialities.join(', ')})
                  </option>
                ))}
              </select>
            </div>

            {/* Step 3: Visit Type & Date */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: 'var(--navy)', marginBottom: '0.45rem' }}>
                  3. Visit Type
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', background: 'var(--cream-surface)', padding: '4px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                  <button
                    type="button"
                    onClick={() => setVisitType('new')}
                    style={{
                      padding: '0.6rem 0.45rem',
                      borderRadius: '4px',
                      fontSize: '14px',
                      fontWeight: visitType === 'new' ? 600 : 500,
                      background: visitType === 'new' ? 'var(--navy)' : 'transparent',
                      color: visitType === 'new' ? 'var(--cream-text)' : 'var(--text-muted)'
                    }}
                  >
                    New (20m)
                  </button>
                  <button
                    type="button"
                    onClick={() => setVisitType('follow_up')}
                    style={{
                      padding: '0.6rem 0.45rem',
                      borderRadius: '4px',
                      fontSize: '14px',
                      fontWeight: visitType === 'follow_up' ? 600 : 500,
                      background: visitType === 'follow_up' ? 'var(--navy)' : 'transparent',
                      color: visitType === 'follow_up' ? 'var(--cream-text)' : 'var(--text-muted)'
                    }}
                  >
                    Follow-up (10m)
                  </button>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: 'var(--navy)', marginBottom: '0.45rem' }}>
                  4. Consultation Date
                </label>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.72rem 0.95rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    outline: 'none',
                    fontWeight: 400,
                    fontSize: '15px',
                    color: 'var(--navy)',
                    background: '#ffffff'
                  }}
                />
              </div>
            </div>

            {/* Step 4: Available Free Slots */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem' }}>
                <label style={{ fontSize: '14px', fontWeight: 500, color: 'var(--navy)' }}>
                  5. Choose Slot
                </label>
                {availableSlots.length > 0 && (
                  <span style={{ fontSize: '13.5px', color: 'var(--navy)', fontWeight: 500 }}>
                    {availableSlots.length} available slots
                  </span>
                )}
              </div>

              {slotsLoading ? (
                <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14.5px' }}>
                  <span className="spin">⏳</span> Checking doctor OPD schedule and available slots...
                </div>
              ) : availableSlots.length === 0 ? (
                <div style={{
                  padding: '1.5rem',
                  background: 'var(--cream-surface)',
                  borderRadius: '6px',
                  color: 'var(--text-muted)',
                  fontSize: '14px',
                  textAlign: 'center',
                  border: '1px dashed var(--border)'
                }}>
                  No bookable slots on this date (check surgery sessions, doctor days off, holidays, or clinic Sunday closure).
                </div>
              ) : (
                <div className="slot-grid" style={{ maxHeight: '200px', overflowY: 'auto', paddingRight: '4px' }}>
                  {availableSlots.map(timeStr => (
                    <button
                      key={timeStr}
                      type="button"
                      className={`slot-chip ${selectedSlot === timeStr ? 'selected' : ''}`}
                      onClick={() => setSelectedSlot(timeStr)}
                    >
                      {timeStr}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Step 5: Reason for Visit (R3) */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem' }}>
                <label style={{ fontSize: '14px', fontWeight: 500, color: 'var(--navy)' }}>
                  6. Reason for Visit <span style={{ color: 'var(--danger)' }}>*</span>
                </label>
                <span style={{ fontSize: '13px', color: visitReason.length > 300 ? 'var(--danger)' : 'var(--text-muted)', fontWeight: 400 }}>
                  {visitReason.length}/300
                </span>
              </div>
              <textarea
                value={visitReason}
                onChange={(e) => setVisitReason(e.target.value)}
                placeholder="Describe your eye symptoms or consultation purpose (e.g., routine vision check, sudden blurry vision, eye pain, redness)..."
                rows={3}
                maxLength={300}
                style={{
                  width: '100%',
                  padding: '0.85rem 1rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  outline: 'none',
                  resize: 'vertical',
                  fontSize: '15px',
                  lineHeight: 1.6,
                  color: 'var(--navy)'
                }}
              />
            </div>

            <button
              onClick={handleBook}
              disabled={!selectedSlot || !visitReason.trim() || actionLoading}
              className="btn btn-primary"
              style={{
                marginTop: '0.5rem',
                width: '100%',
                padding: '0.85rem 1.5rem',
                fontSize: '15px',
                fontWeight: 600,
                borderRadius: '6px'
              }}
            >
              {actionLoading ? 'Screening Red Flags & Rules...' : `Book Consultation at ${selectedSlot || '...'}`}
              {!actionLoading && <ArrowRight size={17} />}
            </button>
          </div>
        </div>

      </div>

      {/* 8. Frequently Asked Questions (FAQ) */}
      <div id="section-faq" className="card" style={{
        padding: '2.5rem 2.5rem',
        background: '#ffffff',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-xs)',
        marginTop: '0.5rem'
      }}>
        <div style={{ marginBottom: '1.75rem', textAlign: 'center' }}>
          <div className="ref-eyebrow" style={{ justifyContent: 'center', marginBottom: '0.5rem' }}>
            <HelpCircle size={15} /> Patient Help Center & Clinic FAQs
          </div>
          <h2 className="ref-section-title" style={{ fontSize: '24px', color: 'var(--navy)', marginBottom: '0.5rem' }}>
            Frequently Asked Questions
          </h2>
          <p className="ref-section-sub" style={{ maxWidth: '680px', margin: '0 auto', fontSize: '15px' }}>
            Information regarding ophthalmic consultations, LASIK suitability screening, the 2-hour cancellation rule, and emergency protocols.
          </p>
        </div>

        <div style={{ display: 'grid', gap: '0.75rem', maxWidth: '920px', margin: '0 auto' }}>
          {faqItems.map((faq, idx) => {
            const isOpen = openFaq === idx;
            return (
              <div
                key={idx}
                style={{
                  border: '1px solid',
                  borderColor: isOpen ? 'var(--navy)' : 'var(--border)',
                  borderRadius: '6px',
                  background: isOpen ? 'var(--cream-surface)' : '#ffffff',
                  overflow: 'hidden',
                  transition: 'border-color 0.15s ease'
                }}
              >
                <button
                  type="button"
                  onClick={() => setOpenFaq(isOpen ? null : idx)}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    padding: '1.15rem 1.45rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '1rem',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontFamily: 'var(--font-heading)',
                    fontSize: '16px',
                    color: isOpen ? 'var(--navy)' : 'var(--navy)'
                  }}
                >
                  <span>{faq.q}</span>
                  <ChevronDown
                    size={17}
                    style={{
                      transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s ease',
                      flexShrink: 0,
                      color: 'var(--navy)'
                    }}
                  />
                </button>

                {isOpen && (
                  <div style={{
                    padding: '0 1.45rem 1.25rem 1.45rem',
                    fontSize: '15px',
                    lineHeight: 1.65,
                    color: 'var(--text-body)',
                    borderTop: '1px solid var(--cream-border)',
                    paddingTop: '0.95rem'
                  }}>
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
