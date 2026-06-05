/* Rezepte-App – React Frontend
 * Basiert auf dem Prototyp von Sabines Claude.
 * Datenspeicherung: Django REST API statt localStorage.
 * Öffentlich lesbar; Schreiben nur für eingeloggte User. */

const { useState, useEffect, useMemo } = React;

/* ─── Konfiguration (aus Django-Template) ─── */
const CFG = window.REZEPTE_CONFIG || { isAuthenticated: false, csrfToken: '' };

/* ─── API-Layer ─── */
const BASE = '/rezepte/api';

function getCsrf() {
  const fromConfig = CFG.csrfToken;
  if (fromConfig) return fromConfig;
  const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
  return cookie ? cookie.split('=')[1] : '';
}
const jsonHeaders = () => ({ 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() });

const api = {
  list:      ()       => fetch(`${BASE}/rezepte/`).then(r => { if (!r.ok) throw r; return r.json(); }),
  create:    (data)   => fetch(`${BASE}/rezepte/`, { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(data) }).then(r => { if (!r.ok) throw r; return r.json(); }),
  update:    (id, d)  => fetch(`${BASE}/rezepte/${id}/`, { method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify(d) }).then(r => { if (!r.ok) throw r; return r.json(); }),
  remove:    (id)     => fetch(`${BASE}/rezepte/${id}/`, { method: 'DELETE', headers: jsonHeaders() }).then(r => { if (!r.ok && r.status !== 204) throw r; }),
  exportCsv: ()       => window.open(`${BASE}/rezepte/export_csv/`),
};

/* ─── Konstanten ─── */
const KATEGORIEN = [
  { key: 'fruehstueck', label: 'Frühstück' },
  { key: 'vorspeisen',  label: 'Vorspeisen' },
  { key: 'suppen',      label: 'Suppen' },
  { key: 'vegetarisch', label: 'Vegetarisch' },
  { key: 'fleisch',     label: 'Fleisch' },
  { key: 'fisch',       label: 'Fisch & Meeresfrüchte' },
  { key: 'kartoffeln',  label: 'Kartoffeln' },
  { key: 'pasta',       label: 'Pasta & Reis' },
  { key: 'backen',      label: 'Backen' },
  { key: 'dessert',     label: 'Desserts' },
  { key: 'snacks',      label: 'Snacks & Dips' },
  { key: 'getraenke',   label: 'Getränke' },
];
const AUFWAND = ['niedrig', 'mittel', 'hoch'];
const QUELLEN = ['OneNote', 'Chefkoch', 'Papier', 'Screenshot', 'Buch', 'Familie', 'Eigenes'];
const SAISONS = ['Frühling', 'Sommer', 'Herbst', 'Winter', 'Ganzjährig'];

const LEER = { id: null, name: '', kategorie: 'vegetarisch', aufwand: 'niedrig', saison: 'Ganzjährig', quelle: 'Eigenes', zutaten: '', notiz: '', link: '', liebling: false };
const katLabel = k => KATEGORIEN.find(x => x.key === k)?.label || k;
const katClass = k => `badge kat-${k || 'default'}`;

/* ─── App ─── */
function App() {
  const [rezepte,  setRezepte]  = useState([]);
  const [laden,    setLaden]    = useState(true);
  const [fehler,   setFehler]   = useState(null);
  const [suche,    setSuche]    = useState('');
  const [katFilter,setKat]      = useState('');
  const [aufwandF, setAufwand]  = useState('');
  const [saisonF,  setSaison]   = useState('');
  const [nurLiebling, setNurL]  = useState(false);
  const [sortierung, setSort]   = useState('name');
  const [ansicht,  setAnsicht]  = useState('liste');
  const [aktiv,    setAktiv]    = useState(null);
  const [formular, setFormular] = useState(null);
  const [saving,   setSaving]   = useState(false);

  /* Laden beim Start */
  useEffect(() => {
    api.list()
      .then(data => { setRezepte(Array.isArray(data) ? data : (data.results || [])); setLaden(false); })
      .catch(() => { setFehler('Rezepte konnten nicht geladen werden.'); setLaden(false); });
  }, []);

  /* Filter + Sort */
  const gefiltert = useMemo(() => {
    let r = rezepte;
    if (suche)       r = r.filter(x => x.name.toLowerCase().includes(suche.toLowerCase()) || (x.zutaten || '').toLowerCase().includes(suche.toLowerCase()));
    if (katFilter)   r = r.filter(x => x.kategorie === katFilter);
    if (aufwandF)    r = r.filter(x => x.aufwand   === aufwandF);
    if (saisonF)     r = r.filter(x => x.saison    === saisonF);
    if (nurLiebling) r = r.filter(x => x.liebling);
    return sortierung === 'name'
      ? [...r].sort((a, b) => a.name.localeCompare(b.name, 'de'))
      : [...r].sort((a, b) => b.id - a.id);
  }, [rezepte, suche, katFilter, aufwandF, saisonF, nurLiebling, sortierung]);

  /* Aktionen */
  useEffect(() => { window.scrollTo(0, 0); }, [ansicht]);

  function oeffneNeu() { setFormular({ ...LEER }); setAnsicht('formular'); }
  function oeffneBearbeiten(r) { setFormular({ ...r }); setAnsicht('formular'); }

  async function speichereFormular() {
    if (!formular.name.trim()) return;
    if (!CFG.isAuthenticated) { alert('Bitte einloggen um Rezepte zu speichern.'); return; }
    setSaving(true);
    try {
      const payload = { ...formular };
      if (formular.id) {
        const updated = await api.update(formular.id, payload);
        setRezepte(prev => prev.map(r => r.id === updated.id ? updated : r));
        setAktiv(updated);
        setAnsicht('detail');
      } else {
        const created = await api.create(payload);
        setRezepte(prev => [...prev, created]);
        setAnsicht('liste');
      }
      setFormular(null);
    } catch { alert('Fehler beim Speichern. Bitte erneut versuchen.'); }
    finally { setSaving(false); }
  }

  async function loescheRezept(id) {
    if (!window.confirm('Rezept wirklich löschen?')) return;
    try {
      await api.remove(id);
      setRezepte(prev => prev.filter(r => r.id !== id));
      setAnsicht('liste');
    } catch { alert('Fehler beim Löschen.'); }
  }

  async function toggleLiebling(id, e) {
    e && e.stopPropagation();
    if (!CFG.isAuthenticated) return;
    const r = rezepte.find(x => x.id === id);
    if (!r) return;
    try {
      const updated = await api.update(id, { liebling: !r.liebling });
      setRezepte(prev => prev.map(x => x.id === id ? updated : x));
      if (aktiv && aktiv.id === id) setAktiv(updated);
    } catch { /* still update locally */ }
  }

  /* ── Lade-Zustand ── */
  if (laden) return (
    <>
      <Header onNeu={oeffneNeu} />
      <div className="rz-container" style={{ textAlign: 'center', padding: '4rem', color: '#78716c', fontFamily: 'Georgia, serif' }}>
        Rezepte werden geladen …
      </div>
    </>
  );

  if (fehler) return (
    <>
      <Header onNeu={oeffneNeu} />
      <div className="rz-container" style={{ textAlign: 'center', padding: '4rem', color: '#ef4444' }}>{fehler}</div>
    </>
  );

  /* ── Detail-Ansicht ── */
  if (ansicht === 'detail' && aktiv) {
    const r = rezepte.find(x => x.id === aktiv.id) || aktiv;
    return (
      <>
        <Header onNeu={oeffneNeu} />
        <div className="rz-container">
          <button className="detail-back" onClick={() => setAnsicht('liste')}>← Zurück zur Liste</button>
          {r.foto_url && (
            <img src={r.foto_url} alt={r.name}
              style={{ width: '100%', maxHeight: '320px', objectFit: 'cover', borderRadius: '10px', marginBottom: '1.25rem' }}
              onError={e => e.target.style.display='none'} />
          )}
          <div className="detail-header">
            <div className="detail-title">{r.liebling ? '⭐ ' : ''}{r.name}</div>
            {CFG.isAuthenticated && (
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn btn-ghost btn-sm" style={{ background: '#f5f5f4', color: '#44403c', border: '1px solid #d6d3d1' }} onClick={() => oeffneBearbeiten(r)}>Bearbeiten</button>
                <button className="btn btn-danger btn-sm" onClick={() => loescheRezept(r.id)}>Löschen</button>
              </div>
            )}
          </div>
          <div className="detail-meta">
            <span className={katClass(r.kategorie)}>{katLabel(r.kategorie)}</span>
            <span className="chip">🔥 {r.aufwand}</span>
            
            <span className="chip">🌿 {r.saison}</span>
            {r.quelle && <span className="badge badge-akzent">{r.quelle}</span>}
          </div>
          {r.zutaten && (
            <div className="detail-section">
              <h3>Zutaten</h3>
              <ul className="zutaten-list">
                {r.zutaten.split(',').map((z, i) => <li key={i}>{z.trim()}</li>)}
              </ul>
            </div>
          )}
          {r.notiz && (
            <div className="detail-section">
              <h3>Zubereitung</h3>
              <p className="notiz-text">{r.notiz}</p>
            </div>
          )}
          {r.link && (
            <div className="detail-section">
              <h3>Quelle</h3>
              <a href={r.link} target="_blank" rel="noopener noreferrer" style={{ color: '#92400e' }}>{r.link}</a>
            </div>
          )}
        </div>
      </>
    );
  }

  /* ── Formular ── */
  if (ansicht === 'formular' && formular) {
    const set = k => e => setFormular(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
    return (
      <>
        <Header onNeu={oeffneNeu} />
        <div className="rz-container">
          <div className="modal" style={{ maxWidth: '660px', margin: '0 auto' }}>
            <h2>{formular.id ? 'Rezept bearbeiten' : 'Neues Rezept'}</h2>
            <div className="form-grid">
              <div className="form-group full"><label>Titel *</label><input type="text" value={formular.name} onChange={set('name')} placeholder="Rezeptname" /></div>
              <div className="form-group"><label>Kategorie</label><select className="form-select" value={formular.kategorie} onChange={set('kategorie')}>{KATEGORIEN.map(k => <option key={k.key} value={k.key}>{k.label}</option>)}</select></div>
              <div className="form-group"><label>Aufwand</label><select className="form-select" value={formular.aufwand} onChange={set('aufwand')}>{AUFWAND.map(a => <option key={a}>{a}</option>)}</select></div>
              <div className="form-group"><label>Quelle</label><select className="form-select" value={formular.quelle} onChange={set('quelle')}>{QUELLEN.map(q => <option key={q}>{q}</option>)}</select></div>
              <div className="form-group"><label>Link (optional)</label><input type="url" value={formular.link} onChange={set('link')} placeholder="https://…" /></div>
              <div className="form-group"><label>Foto-URL (optional)</label><input type="url" value={formular.foto_url || ''} onChange={set('foto_url')} placeholder="https://drive.google.com/uc?id=…" /></div>
              <div className="form-group full"><label>Zutaten (kommagetrennt)</label><input type="text" value={formular.zutaten} onChange={set('zutaten')} placeholder="Linsen, Karotten, Zwiebel, …" /></div>
              <div className="form-group full"><label>Zubereitung</label><textarea value={formular.notiz} onChange={set('notiz')} placeholder="Schritt-für-Schritt oder freie Notizen …" rows={5} /></div>
              <div className="form-group full"><label className="liebling-toggle"><input type="checkbox" checked={formular.liebling} onChange={set('liebling')} /> ⭐ Als Lieblingsrezept markieren</label></div>
            </div>
            <div className="form-actions">
              <button className="btn btn-cancel" onClick={() => { setAnsicht(formular.id ? 'detail' : 'liste'); setFormular(null); }}>Abbrechen</button>
              <button className="btn btn-primary" onClick={speichereFormular} disabled={saving}>{saving ? 'Speichert …' : 'Speichern'}</button>
            </div>
          </div>
        </div>
      </>
    );
  }

  /* ── Liste ── */
  return (
    <>
      <Header onNeu={oeffneNeu} />
      <div className="rz-container">
        <div className="toolbar">
          <div className="search-wrap">
            <span className="search-icon">🔍</span>
            <input type="text" placeholder="Rezept oder Zutat suchen …" value={suche} onChange={e => setSuche(e.target.value)} />
          </div>
          <select className="rz-select" value={sortierung} onChange={e => setSort(e.target.value)}>
            <option value="name">A – Z</option>
            <option value="datum">Neueste zuerst</option>
          </select>
          {CFG.isAuthenticated && (
            <button className="btn btn-ghost btn-sm" style={{ background: '#f5f5f4', color: '#44403c', border: '1px solid #d6d3d1' }} onClick={api.exportCsv}>⬇ CSV</button>
          )}
        </div>
        <div className="filter-row">
          <span>Filter:</span>
          <button className={`tag-btn ${nurLiebling ? 'active' : ''}`} onClick={() => setNurL(v => !v)}>⭐ Lieblinge</button>
          <select className="rz-select" value={katFilter} onChange={e => setKat(e.target.value)} style={{ fontSize: '0.82rem', padding: '0.25rem 0.6rem' }}>
            <option value="">Alle Kategorien</option>
            {KATEGORIEN.map(k => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
          <select className="rz-select" value={aufwandF} onChange={e => setAufwand(e.target.value)} style={{ fontSize: '0.82rem', padding: '0.25rem 0.6rem' }}>
            <option value="">Alle Aufwände</option>
            {AUFWAND.map(a => <option key={a}>{a}</option>)}
          </select>
          <select className="rz-select" value={saisonF} onChange={e => setSaison(e.target.value)} style={{ fontSize: '0.82rem', padding: '0.25rem 0.6rem' }}>
            <option value="">Alle Saisons</option>
            {SAISONS.map(s => <option key={s}>{s}</option>)}
          </select>
          {(katFilter || aufwandF || saisonF || nurLiebling || suche) && (
            <button className="tag-btn" onClick={() => { setKat(''); setAufwand(''); setSaison(''); setNurL(false); setSuche(''); }}>✕ Reset</button>
          )}
        </div>
        <div className="count-bar">{gefiltert.length} Rezept{gefiltert.length !== 1 ? 'e' : ''}</div>
        {gefiltert.length === 0
          ? <div className="empty-state">Keine Rezepte gefunden.<br /><span style={{ fontSize: '0.9rem', color: '#a8a29e' }}>Füge ein neues Rezept hinzu oder ändere die Filter.</span></div>
          : <div className="rezept-list">
              {gefiltert.map(r => (
                <div className="rezept-card" key={r.id} onClick={() => { setAktiv(r); setAnsicht('detail'); }}>
                  <span className="star">{r.liebling ? '⭐' : '·'}</span>
                  <div className="card-body">
                    <div className="card-title">{r.name}</div>
                    <div className="card-meta">
                      <span className={katClass(r.kategorie)}>{katLabel(r.kategorie)}</span>
                      <span className="chip">🔥 {r.aufwand}</span>
                      <span className="chip">🌿 {r.saison}</span>
                    </div>
                  </div>
                  {CFG.isAuthenticated && (
                    <div className="card-actions" onClick={e => e.stopPropagation()}>
                      <button className="btn btn-ghost btn-sm" style={{ background: '#f5f5f4', color: '#44403c', border: '1px solid #d6d3d1' }} onClick={e => toggleLiebling(r.id, e)}>{r.liebling ? '★' : '☆'}</button>
                      <button className="btn btn-ghost btn-sm" style={{ background: '#f5f5f4', color: '#44403c', border: '1px solid #d6d3d1' }} onClick={e => { e.stopPropagation(); oeffneBearbeiten(r); }}>✏</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
        }
      </div>
    </>
  );
}

function Header({ onNeu }) {
  return (
    <header className="rezepte-header">
      <h1>Meine <span>Rezepte</span></h1>
      {CFG.isAuthenticated && (
        <button className="btn btn-primary" onClick={onNeu}>+ Neues Rezept</button>
      )}
    </header>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
