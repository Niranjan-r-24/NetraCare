import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import {
  MessageSquare,
  Send,
  RefreshCw,
  AlertTriangle,
  FileText,
  CheckCircle2,
  Calendar,
  Bot,
  User,
  Sparkles,
  ArrowRight,
  ShieldAlert,
  HelpCircle,
  X
} from 'lucide-react';

export default function PatientChat({ user, onAppointmentChange, isFullScreen, onClose }) {
  // In-memory conversation history only - strictly NOT saved to localStorage or DB
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [threadId, setThreadId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const messagesEndRef = useRef(null);

  // Clear in-memory state on unmount or user change
  useEffect(() => {
    handleNewChat();
    return () => {
      setMessages([]);
      setInputMessage('');
      setThreadId(null);
    };
  }, [user?.user_id]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleNewChat = () => {
    setMessages([]);
    setInputMessage('');
    setErrorMsg('');
    setThreadId(null);
  };

  const handleSuggestionClick = (text) => {
    setInputMessage(text);
  };

  const handleSendMessage = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    const cleanMsg = inputMessage.trim();
    if (!cleanMsg || loading) return;

    if (cleanMsg.length > 500) {
      setErrorMsg('Message exceeds 500 characters limit.');
      return;
    }

    setErrorMsg('');
    const userMsg = {
      id: Date.now(),
      role: 'patient',
      content: cleanMsg,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    // If an action was pending, mark it as superseded/decided because user sent new message
    const updatedHistory = messages.map(m => (m.pending_action ? { ...m, action_decided: true } : m));
    const newHistory = [...updatedHistory, userMsg];
    setMessages(newHistory);
    setInputMessage('');
    setLoading(true);

    try {
      const res = await api.sendChatMessage(cleanMsg, threadId);
      if (res.thread_id) {
        setThreadId(res.thread_id);
      }
      const assistantMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: res.answer,
        sources: res.sources || [],
        is_emergency: !!res.is_emergency,
        is_error: !!res.is_error,
        pending_action: res.pending_action,
        action_decided: false,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages([...newHistory, assistantMsg]);
    } catch (err) {
      const detail = err.detail || 'Failed to communicate with assistant. Please try again.';
      setErrorMsg(typeof detail === 'object' ? (detail.message || 'Chat error') : detail);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmAction = async (msgId, confirm) => {
    if (loading || !threadId) return;
    setErrorMsg('');
    setLoading(true);

    // Mark card as decided to prevent double submission
    setMessages(prev => prev.map(m => (m.id === msgId ? { ...m, action_decided: true } : m)));

    try {
      const res = await api.confirmChatAction(threadId, confirm);
      if (res.thread_id) {
        setThreadId(res.thread_id);
      }
      const assistantMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: res.answer,
        sources: res.sources || [],
        is_emergency: !!res.is_emergency,
        is_error: !!res.is_error,
        pending_action: res.pending_action,
        action_decided: false,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, assistantMsg]);

      // Refresh appointment list in parent portal if action was confirmed
      if (confirm && onAppointmentChange) {
        onAppointmentChange();
      }
    } catch (err) {
      const detail = err.detail || 'Failed to process confirmation.';
      setErrorMsg(typeof detail === 'object' ? (detail.message || 'Confirmation error') : detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div id="section-chat" className="card" style={{
      display: 'flex',
      flexDirection: 'column',
      height: isFullScreen ? '100%' : '560px',
      maxHeight: isFullScreen ? '100%' : '560px',
      padding: isFullScreen ? '1.5rem' : '1.25rem',
      borderRadius: '8px',
      border: '1px solid var(--border)',
      background: '#ffffff',
      boxShadow: isFullScreen ? 'var(--shadow-floating)' : 'var(--shadow-xs)',
      position: 'relative'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottom: '1px solid var(--border-light)',
        paddingBottom: '0.85rem',
        marginBottom: '0.65rem',
        flexWrap: 'wrap',
        gap: '0.75rem'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            background: 'var(--navy-light)',
            color: 'var(--cream-text)',
            padding: '8px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid rgba(244, 237, 224, 0.2)'
          }}>
            <Bot size={20} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--navy)', margin: 0 }}>
                NetraCare Clinical Assistant
              </h3>
              <span className="badge badge-primary" style={{ padding: '0.12rem 0.5rem', fontSize: '0.68rem', borderRadius: '4px' }}>
                Online & Screened
              </span>
            </div>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 500 }}>
              LASIK suitability, cataract care, doctor OPD schedules, or book & cancel consultations
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            onClick={handleNewChat}
            className="btn btn-secondary btn-sm"
            style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.8rem', borderRadius: '6px' }}
            title="Clear current in-memory conversation"
          >
            <RefreshCw size={12} /> New Chat
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="btn btn-secondary btn-sm"
              style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.8rem', background: 'var(--cream-surface)', borderRadius: '6px' }}
              title="Close Full Screen Assistant"
            >
              <X size={14} /> Close
            </button>
          )}
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.85rem',
        paddingRight: '6px',
        paddingTop: '0.4rem'
      }}>
        {messages.length === 0 ? (
          <div style={{
            margin: 'auto',
            textAlign: 'center',
            color: 'var(--text-muted)',
            padding: '1.5rem 1rem',
            maxWidth: '540px'
          }}>
            <div style={{
              width: '46px',
              height: '46px',
              borderRadius: '6px',
              background: 'var(--navy-light)',
              color: 'var(--cream-text)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '0.75rem',
              border: '1px solid rgba(244, 237, 224, 0.2)'
            }}>
              <Sparkles size={22} />
            </div>
            <h4 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--navy)', marginBottom: '0.35rem', letterSpacing: '-0.015em' }}>
              How can I help with your eye care today, {user?.name || 'Patient'}?
            </h4>
            <p style={{ fontSize: '0.88rem', lineHeight: 1.55, color: 'var(--text-muted)' }}>
              I can check doctor timings, book or reschedule visits with human confirmation, or guide you through LASIK suitability and cataract surgery recovery.
            </p>

            {/* Quick Suggestion Chips */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', justifyContent: 'center', marginTop: '1.25rem' }}>
              <button
                type="button"
                onClick={() => handleSuggestionClick('Book my retina follow-up consultation with Dr. Shah next week')}
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '0.8rem', background: '#ffffff', padding: '0.4rem 0.85rem', borderRadius: '6px', borderColor: 'var(--border)' }}
              >
                📅 Book Retina consultation
              </button>
              <button
                type="button"
                onClick={() => handleSuggestionClick('What are the consultation fees and timings for LASIK assessment?')}
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '0.8rem', background: '#ffffff', padding: '0.4rem 0.85rem', borderRadius: '6px', borderColor: 'var(--border)' }}
              >
                👁️ LASIK assessment & fees
              </button>
              <button
                type="button"
                onClick={() => handleSuggestionClick('What is the clinic appointment cancellation policy?')}
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '0.8rem', background: '#ffffff', padding: '0.4rem 0.85rem', borderRadius: '6px', borderColor: 'var(--border)' }}
              >
                ℹ️ 2-Hour cancellation rules
              </button>
              <button
                type="button"
                onClick={() => handleSuggestionClick('Can my child have breakfast before squint eye surgery?')}
                className="btn btn-secondary btn-sm"
                style={{ fontSize: '0.8rem', background: '#ffffff', padding: '0.4rem 0.85rem', borderRadius: '6px', borderColor: 'var(--border)' }}
              >
                🏥 Pre-surgery fasting instructions
              </button>
            </div>
          </div>
        ) : (
          messages.map(m => (
            <div
              key={m.id}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: m.role === 'patient' ? 'flex-end' : 'flex-start'
              }}
            >
              <div style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.55rem',
                flexDirection: m.role === 'patient' ? 'row-reverse' : 'row',
                maxWidth: '85%'
              }}>
                {/* Avatar Icon */}
                <div style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '4px',
                  background: m.role === 'patient'
                    ? 'var(--navy)'
                    : (m.is_emergency ? '#fee2e2' : 'var(--navy-light)'),
                  color: m.role === 'patient' ? 'var(--cream-text)' : (m.is_emergency ? '#ef4444' : 'var(--cream-text)'),
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  marginTop: '2px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  border: m.role === 'patient' ? 'none' : '1px solid rgba(244, 237, 224, 0.2)'
                }}>
                  {m.role === 'patient' ? <User size={14} /> : <Bot size={15} />}
                </div>

                {/* Message Bubble */}
                <div style={{
                  padding: '0.85rem 1.15rem',
                  borderRadius: '6px',
                  fontSize: '0.9rem',
                  lineHeight: 1.55,
                  background: m.is_emergency
                    ? '#fef2f2'
                    : (m.role === 'patient'
                        ? 'var(--navy)'
                        : 'var(--cream-surface)'),
                  color: m.is_emergency
                    ? '#991b1b'
                    : (m.role === 'patient' ? 'var(--cream-text)' : 'var(--navy)'),
                  border: m.is_emergency
                    ? '1px solid #ef4444'
                    : (m.role === 'patient' ? '1px solid var(--navy)' : '1px solid var(--border)')
                }}>
                  {m.is_emergency && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: '#b91c1c', marginBottom: '6px', fontSize: '0.92rem' }}>
                      <AlertTriangle size={18} /> Urgent Attention Required (Red Flag Protocol)
                    </div>
                  )}
                  <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>

                  {/* Confirmation Card */}
                  {m.pending_action && (
                    <div style={{
                      marginTop: '0.85rem',
                      padding: '1rem',
                      borderRadius: '6px',
                      background: '#ffffff',
                      border: '1px solid var(--border)'
                    }}>
                      <div style={{
                        fontWeight: 600,
                        color: 'var(--navy)',
                        marginBottom: '0.4rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '0.86rem'
                      }}>
                        <Calendar size={15} color="var(--navy)" /> Action Confirmation Required
                      </div>
                      <div style={{ fontSize: '0.88rem', color: 'var(--navy)', marginBottom: '0.85rem', fontWeight: 500, lineHeight: 1.5 }}>
                        {m.pending_action.summary || 'Please confirm this appointment action.'}
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          disabled={loading || m.action_decided}
                          onClick={() => handleConfirmAction(m.id, true)}
                          style={{ padding: '0.4rem 1rem', borderRadius: '6px' }}
                        >
                          Confirm Action
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={loading || m.action_decided}
                          onClick={() => handleConfirmAction(m.id, false)}
                          style={{ padding: '0.4rem 1rem', borderRadius: '6px' }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Grounded Source Citations */}
                  {m.sources && m.sources.length > 0 && (
                    <div style={{
                      marginTop: '0.65rem',
                      paddingTop: '0.5rem',
                      borderTop: '1px solid rgba(0,0,0,0.06)',
                      fontSize: '0.74rem',
                      color: m.role === 'patient' ? 'var(--cream-text)' : 'var(--navy)',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '4px'
                    }}>
                      <FileText size={12} />
                      <span>Verified Sources:</span>
                      {m.sources.map((s, idx) => (
                        <span
                          key={idx}
                          style={{
                            background: m.role === 'patient' ? 'rgba(244, 237, 224, 0.2)' : 'var(--cream-alt)',
                            color: m.role === 'patient' ? 'var(--cream-text)' : 'var(--navy)',
                            padding: '1px 6px',
                            borderRadius: '4px',
                            fontFamily: 'monospace',
                            fontSize: '0.72rem'
                          }}
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '3px', padding: '0 36px' }}>
                {m.timestamp}
              </span>
            </div>
          ))
        )}

        {loading && (
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            background: 'var(--cream-surface)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            padding: '0.4rem 0.95rem',
            color: 'var(--text-muted)',
            fontSize: '0.82rem',
            margin: '0.2rem 0'
          }}>
            <span className="spin">⏳</span> NetraCare AI is coordinating clinic rules & schedule...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {errorMsg && (
        <div style={{ fontSize: '0.84rem', color: '#dc2626', marginTop: '0.4rem', fontWeight: 500 }}>
          {errorMsg}
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleSendMessage} style={{ marginTop: '0.75rem', display: 'grid', gap: '3px' }}>
        <div style={{
          display: 'flex',
          gap: '0.5rem',
          alignItems: 'center',
          background: 'var(--cream-surface)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          padding: '3px 6px 3px 12px'
        }}>
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Type your booking request, symptoms, or inquiry (up to 500 characters)..."
            maxLength={500}
            disabled={loading}
            style={{
              flex: 1,
              padding: '0.5rem 0',
              border: 'none',
              background: 'transparent',
              fontSize: '0.9rem',
              outline: 'none',
              color: 'var(--navy)'
            }}
          />
          <button
            type="submit"
            disabled={!inputMessage.trim() || loading}
            className="btn btn-primary btn-sm"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              fontWeight: 600
            }}
          >
            <Send size={13} /> Send
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0 4px', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
          <span>In-memory private conversation session</span>
          <span style={{ color: inputMessage.length >= 480 ? '#ef4444' : 'inherit' }}>
            {inputMessage.length}/500
          </span>
        </div>
      </form>
    </div>
  );
}
