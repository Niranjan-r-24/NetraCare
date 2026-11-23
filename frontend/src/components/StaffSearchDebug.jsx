import React, { useState } from 'react';
import { api } from '../api';
import { Search, Sliders, Database, Layers, FileText, Sparkles, HelpCircle } from 'lucide-react';

export default function StaffSearchDebug() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const handleSearch = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    const cleanQ = query.trim();
    if (!cleanQ || loading) return;

    setLoading(true);
    setErrorMsg('');
    try {
      const data = await api.getSearchDebug(cleanQ);
      setResults(data);
    } catch (err) {
      setErrorMsg(err.detail || 'Search debug query failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickQuery = (q) => {
    setQuery(q);
  };

  const renderChunkCard = (chunk, idx) => (
    <div
      key={chunk.chunk_id || idx}
      style={{
        background: '#ffffff',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '0.95rem',
        display: 'grid',
        gap: '0.4rem',
        fontSize: '0.84rem',
        boxShadow: 'var(--shadow-xs)'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
        <span style={{ fontWeight: '600', color: 'var(--navy)' }}>
          {chunk.source} › {chunk.section}
        </span>
        <span style={{
          background: 'var(--cream-surface)',
          padding: '2px 8px',
          borderRadius: '4px',
          fontFamily: 'monospace',
          fontSize: '0.72rem',
          fontWeight: '600',
          color: 'var(--navy)',
          border: '1px solid var(--cream-border)'
        }}>
          Score: {chunk.score}
        </span>
      </div>
      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
        Chunk ID: {chunk.chunk_id}
      </div>
      <div style={{
        color: 'var(--navy)',
        lineHeight: 1.5,
        maxHeight: '130px',
        overflowY: 'auto',
        fontSize: '0.82rem',
        background: 'var(--cream-surface)',
        padding: '0.55rem 0.75rem',
        borderRadius: '6px',
        border: '1px solid var(--border)'
      }}>
        {chunk.content}
      </div>
    </div>
  );

  return (
    <div className="card" style={{ display: 'grid', gap: '1.35rem', borderRadius: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        <div style={{
          background: 'var(--navy)',
          color: '#ffffff',
          padding: '8px',
          borderRadius: '6px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <Sliders size={20} />
        </div>
        <div>
          <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', fontWeight: 600, margin: 0, color: 'var(--navy)' }}>
            Staff Knowledge-Base Search Debugger
          </h3>
          <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
            Compare keyword (BM25), vector (Chroma), and equal-weight hybrid rankings across clinic documentation
          </span>
        </div>
      </div>

      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Try: 'Should I bring my HbA1c report?' or 'Can my child have breakfast before squint surgery?'"
          style={{
            flex: 1,
            minWidth: '280px',
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            fontSize: '15px',
            outline: 'none'
          }}
        />
        <button
          type="submit"
          disabled={!query.trim() || loading}
          className="btn btn-primary"
          style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '0.75rem 1.45rem', borderRadius: '6px', fontSize: '14.5px' }}
        >
          <Search size={16} /> {loading ? 'Querying...' : 'Search Debug'}
        </button>
      </form>

      {/* Suggested queries */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '13.5px', color: '#64748b', fontWeight: 500 }}>Quick probes:</span>
        <button
          type="button"
          onClick={() => handleQuickQuery('Should I bring my HbA1c report?')}
          className="btn btn-secondary btn-sm"
          style={{ fontSize: '13.5px', padding: '0.4rem 0.95rem', borderRadius: '6px' }}
        >
          HbA1c report requirement
        </button>
        <button
          type="button"
          onClick={() => handleQuickQuery('Can my kid have breakfast before squint surgery?')}
          className="btn btn-secondary btn-sm"
          style={{ fontSize: '13.5px', padding: '0.4rem 0.95rem', borderRadius: '6px' }}
        >
          Fasting before surgery
        </button>
        <button
          type="button"
          onClick={() => handleQuickQuery('LASIK refractive screening suitability')}
          className="btn btn-secondary btn-sm"
          style={{ fontSize: '13.5px', padding: '0.4rem 0.95rem', borderRadius: '6px' }}
        >
          LASIK suitability
        </button>
      </div>

      {errorMsg && (
        <div style={{ fontSize: '0.85rem', color: '#dc2626', fontWeight: '600' }}>
          {errorMsg}
        </div>
      )}

      {results && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginTop: '0.5rem' }}>
          {/* Column 1: Keyword Only (BM25) */}
          <div style={{
            background: 'var(--cream-surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            padding: '1.25rem',
            display: 'grid',
            gap: '0.85rem',
            alignContent: 'start'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: '600', fontSize: '0.9rem', color: 'var(--navy)' }}>
              <FileText size={16} color="var(--navy)" /> Keyword Only (BM25)
            </div>
            {results.keyword_only.length === 0 ? (
              <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No keyword matches.</div>
            ) : (
              results.keyword_only.map((c, i) => renderChunkCard(c, i))
            )}
          </div>

          {/* Column 2: Vector Only */}
          <div style={{
            background: 'var(--cream-surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            padding: '1.25rem',
            display: 'grid',
            gap: '0.85rem',
            alignContent: 'start'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: '600', fontSize: '0.9rem', color: 'var(--navy)' }}>
              <Database size={16} color="var(--navy)" /> Vector Only (Embeddings)
            </div>
            {results.vector_only.length === 0 ? (
              <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No vector matches.</div>
            ) : (
              results.vector_only.map((c, i) => renderChunkCard(c, i))
            )}
          </div>

          {/* Column 3: Hybrid (Equal Weight) */}
          <div style={{
            background: '#ffffff',
            border: '1.5px solid var(--navy)',
            borderRadius: '8px',
            padding: '1.25rem',
            display: 'grid',
            gap: '0.85rem',
            alignContent: 'start',
            boxShadow: 'var(--shadow-card)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: '600', fontSize: '0.9rem', color: 'var(--navy)' }}>
              <Layers size={16} color="var(--navy)" /> Hybrid (50% BM25 + 50% Vector)
            </div>
            {results.hybrid.length === 0 ? (
              <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No hybrid matches.</div>
            ) : (
              results.hybrid.map((c, i) => renderChunkCard(c, i))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
