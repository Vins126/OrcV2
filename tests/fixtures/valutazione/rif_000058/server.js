// Sito di riferimento del compito 000058, scritto a mano: serve solo a provare che
// lo script di valutazione da' 100 su un sito che rispetta contratto e marcatori.
const http = require('http');
const fs = require('fs');
const path = require('path');
const DATI = 'data', DB = path.join(DATI, 'db.json');
fs.mkdirSync(DATI, { recursive: true });

const COACH = [
  { id: 1, name: 'Anna Rossi', specialty: 'Leadership' },
  { id: 2, name: 'Marco Bianchi', specialty: 'Carriera' },
  { id: 3, name: 'Sara Verdi', specialty: 'Benessere' },
  { id: 4, name: 'Luca Neri', specialty: 'Leadership e comunicazione' },
];
const vuoto = () => ({ next: 1, profile: { name: '', bio: '', preferences: '', assessmentResult: null }, sessions: [], goals: [] });
const leggi = () => (fs.existsSync(DB) ? JSON.parse(fs.readFileSync(DB, 'utf8')) : vuoto());
const salva = (d) => fs.writeFileSync(DB, JSON.stringify(d));
const json = (s, code, v) => { s.statusCode = code; s.setHeader('content-type', 'application/json'); s.end(v === undefined ? '' : JSON.stringify(v)); };
const corpo = (q) => new Promise((ok) => { let t = ''; q.on('data', (c) => (t += c)); q.on('end', () => { try { ok(t ? JSON.parse(t) : {}); } catch { ok(null); } }); });
const dataValida = (v) => typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Date.parse(v));
const progressoValido = (v) => Number.isInteger(v) && v >= 0 && v <= 100;
const testoPieno = (v) => typeof v === 'string' && v.trim() !== '';

const TIPI = ['Pianificatore riflessivo', 'Esploratore energico', 'Mediatore empatico'];

const PAGINA = `<!doctype html><html lang="it"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Coaching uno a uno</title>
<style>
body{background:#F5F5DC;font-family:sans-serif;margin:0;padding:16px;max-width:900px}
h1,h2{color:#8B4513}section{border:2px solid #8B4513;border-radius:8px;padding:12px;margin:12px 0}
button{background:#8B4513;color:#fff;border:1px solid #8B4513;border-radius:4px;padding:4px 10px;cursor:pointer}
.coach{border:1px solid #8B4513;border-radius:6px;padding:6px;margin:4px 0;cursor:pointer}.coach.scelto{background:#8B4513;color:#fff}
.barra{display:inline-block;width:120px;height:10px;border:1px solid #8B4513}.barra span{display:block;height:100%;background:#8B4513}
li{margin:6px 0}
</style>
<main><h1>Coaching uno a uno</h1>
<section><h2>Test di personalita'</h2><div id="domande"></div>
<button data-testid="assessment-submit" id="invia-test">Invia il test</button> <span id="msg-test"></span></section>
<section><h2>Profilo</h2>
<label>Nome <input data-testid="profile-name" id="nome"></label><br>
<label>Bio <input id="bio"></label><br><label>Preferenze <input id="pref"></label><br>
<button data-testid="profile-save" id="salva-profilo">Salva profilo</button> <span id="msg-profilo"></span>
<p>Risultato del test: <strong id="risultato"></strong></p></section>
<section><h2>Coach</h2><label>Cerca <input data-testid="coach-search" id="cerca" placeholder="nome o specialita'"></label>
<div id="coach"></div>
<h2>Prenota una sessione</h2><p>Coach scelto: <span id="scelto">nessuno</span></p>
<label>Data e ora <input type="datetime-local" data-testid="session-datetime" id="quando"></label>
<button data-testid="session-submit" id="prenota">Prenota</button> <span id="msg-sessione"></span>
<h2>Le mie sessioni</h2><ul id="sessioni"></ul></section>
<section><h2>Obiettivi</h2><label>Nuovo obiettivo <input data-testid="goal-title" id="titolo"></label>
<button data-testid="goal-add" id="aggiungi">Aggiungi</button><ul id="obiettivi"></ul></section>
</main>
<script>
const DOMANDE = [['Preferisci pianificare o improvvisare?', ['Pianificare', 'Improvvisare']],
  ['Ti ricarichi da solo o in compagnia?', ['Da solo', 'In compagnia']],
  ['Decidi con la logica o con le emozioni?', ['Logica', 'Emozioni']]];
document.getElementById('domande').innerHTML = DOMANDE.map((d, i) => '<p>' + d[0] + '<br>' + d[1].map((o, k) =>
  '<label><input type="radio" name="q' + i + '" value="' + k + '"' + (k === 0 ? ' data-testid="assessment-option"' : '') + '> ' + o + '</label> ').join('') + '</p>').join('');
const api = async (metodo, url, dati) => { const r = await fetch(url, { method: metodo, headers: { 'content-type': 'application/json' }, body: dati === undefined ? undefined : JSON.stringify(dati) }); return r.status === 204 ? null : r.json(); };
let coach = [], scelto = null;
async function profilo() {
  const p = await api('GET', '/api/profile');
  document.getElementById('nome').value = p.name || ''; document.getElementById('bio').value = p.bio || ''; document.getElementById('pref').value = p.preferences || '';
  const r = document.getElementById('risultato');
  if (p.assessmentResult) { r.textContent = p.assessmentResult; r.setAttribute('data-testid', 'assessment-result'); }
}
async function cercaCoach() {
  const q = document.getElementById('cerca').value.trim();
  coach = await api('GET', '/api/coaches' + (q ? '?q=' + encodeURIComponent(q) : ''));
  const box = document.getElementById('coach'); box.innerHTML = '';
  coach.forEach(c => { const d = document.createElement('div'); d.className = 'coach' + (scelto && scelto.id === c.id ? ' scelto' : '');
    d.setAttribute('data-testid', 'coach-card'); d.innerHTML = '<strong>' + c.name + '</strong> - ' + c.specialty;
    d.onclick = () => { scelto = c; document.getElementById('scelto').textContent = c.name; cercaCoach(); }; box.appendChild(d); });
}
async function sessioni() {
  const tutti = await api('GET', '/api/coaches'); const ss = await api('GET', '/api/sessions');
  const ul = document.getElementById('sessioni'); ul.innerHTML = '';
  ss.forEach(s => { const li = document.createElement('li'); const c = tutti.find(x => x.id === s.coachId);
    li.textContent = (c ? c.name : '?') + ' - ' + s.datetime.replace('T', ' ') + ' (' + s.status + ') ';
    const b = document.createElement('button'); b.textContent = 'Annulla'; b.onclick = async () => { await api('DELETE', '/api/sessions/' + s.id); sessioni(); };
    li.appendChild(b); ul.appendChild(li); });
}
async function obiettivi() {
  const gs = await api('GET', '/api/goals'); const ul = document.getElementById('obiettivi'); ul.innerHTML = '';
  gs.forEach(g => { const li = document.createElement('li');
    li.innerHTML = '<span></span> <input type="number" min="0" max="100" data-testid="goal-progress"> % <span class="barra"><span></span></span> <button>Elimina</button>';
    li.children[0].textContent = g.title; const n = li.querySelector('input'); n.value = g.progress; li.querySelector('.barra span').style.width = g.progress + '%';
    const salvaP = async () => { const v = Number(n.value); if (Number.isInteger(v) && v >= 0 && v <= 100 && v !== g.progress) { g.progress = v; await api('PATCH', '/api/goals/' + g.id, { progress: v }); li.querySelector('.barra span').style.width = v + '%'; } };
    n.addEventListener('change', salvaP); n.addEventListener('keydown', e => { if (e.key === 'Enter') salvaP(); });
    li.querySelector('button').onclick = async () => { await api('DELETE', '/api/goals/' + g.id); obiettivi(); };
    ul.appendChild(li); });
}
document.getElementById('invia-test').onclick = async () => {
  const risposte = DOMANDE.map((_, i) => { const x = document.querySelector('input[name=q' + i + ']:checked'); return x ? Number(x.value) : null; });
  if (risposte.includes(null)) { document.getElementById('msg-test').textContent = 'Rispondi a tutte le domande'; return; }
  await api('POST', '/api/assessment', { answers: risposte }); document.getElementById('msg-test').textContent = 'Test salvato nel profilo'; profilo();
};
document.getElementById('salva-profilo').onclick = async () => {
  const r = await fetch('/api/profile', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name: document.getElementById('nome').value, bio: document.getElementById('bio').value, preferences: document.getElementById('pref').value }) });
  document.getElementById('msg-profilo').textContent = r.ok ? 'Profilo salvato' : 'Il nome e\\' obbligatorio';
};
document.getElementById('cerca').addEventListener('input', cercaCoach);
document.getElementById('prenota').onclick = async () => {
  const quando = document.getElementById('quando').value; const m = document.getElementById('msg-sessione');
  if (!scelto || !quando) { m.textContent = 'Scegli un coach e una data'; return; }
  const r = await fetch('/api/sessions', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ coachId: scelto.id, datetime: quando }) });
  m.textContent = r.ok ? 'Sessione confermata con ' + scelto.name : 'Prenotazione non riuscita'; sessioni();
};
document.getElementById('aggiungi').onclick = async () => {
  const t = document.getElementById('titolo'); if (!t.value.trim()) return;
  await api('POST', '/api/goals', { title: t.value }); t.value = ''; obiettivi();
};
profilo(); cercaCoach(); sessioni(); obiettivi();
</script></html>`;

http.createServer(async (q, s) => {
  const url = new URL(q.url, 'http://x'); const parti = url.pathname.split('/').filter(Boolean);
  if (parti[0] !== 'api') { s.setHeader('content-type', 'text/html'); return s.end(PAGINA); }
  const d = leggi(); const m = q.method; const risorsa = parti[1], id = parti[2];
  const b = ['POST', 'PUT', 'PATCH'].includes(m) ? await corpo(q) : {};
  if (b === null) return json(s, 400, { error: 'JSON non valido' });

  if (risorsa === 'profile' && !id) {
    if (m === 'GET') return json(s, 200, d.profile);
    if (m === 'PUT') {
      if (!testoPieno(b.name)) return json(s, 400, { error: 'name obbligatorio' });
      d.profile.name = b.name.trim();
      if (typeof b.bio === 'string') d.profile.bio = b.bio;
      if (typeof b.preferences === 'string') d.profile.preferences = b.preferences;
      salva(d); return json(s, 200, d.profile);
    }
  }
  if (risorsa === 'assessment' && !id && m === 'POST') {
    if (!Array.isArray(b.answers) || b.answers.length === 0) return json(s, 400, { error: 'answers non valido' });
    const somma = b.answers.reduce((a, x) => a + (Number(x) || 0), 0);
    d.profile.assessmentResult = TIPI[somma % TIPI.length] + ': ' + b.answers.length + ' risposte valutate';
    salva(d); return json(s, 201, { assessmentResult: d.profile.assessmentResult });
  }
  if (risorsa === 'coaches' && !id && m === 'GET') {
    const t = (url.searchParams.get('q') || '').toLowerCase();
    return json(s, 200, COACH.filter((c) => !t || c.name.toLowerCase().includes(t) || c.specialty.toLowerCase().includes(t)));
  }
  if (risorsa === 'sessions') {
    if (!id && m === 'GET') return json(s, 200, d.sessions);
    if (!id && m === 'POST') {
      const c = COACH.find((x) => String(x.id) === String(b.coachId));
      if (!c || !dataValida(b.datetime)) return json(s, 400, { error: 'coachId o datetime non validi' });
      const nuova = { id: d.next++, coachId: c.id, datetime: b.datetime, status: 'confirmed' };
      d.sessions.push(nuova); salva(d); return json(s, 201, nuova);
    }
    const x = id && d.sessions.find((v) => String(v.id) === id);
    if (id && m === 'PATCH') {
      if (!x) return json(s, 404, { error: 'non trovata' });
      if (!dataValida(b.datetime)) return json(s, 400, { error: 'datetime non valida' });
      x.datetime = b.datetime; salva(d); return json(s, 200, x);
    }
    if (id && m === 'DELETE') {
      if (!x) return json(s, 404, { error: 'non trovata' });
      d.sessions = d.sessions.filter((v) => v !== x); salva(d); return json(s, 204);
    }
  }
  if (risorsa === 'goals') {
    if (!id && m === 'GET') return json(s, 200, d.goals);
    if (!id && m === 'POST') {
      const p = b.progress === undefined ? 0 : b.progress;
      if (!testoPieno(b.title) || !progressoValido(p)) return json(s, 400, { error: 'title o progress non validi' });
      const nuovo = { id: d.next++, title: b.title.trim(), progress: p };
      d.goals.push(nuovo); salva(d); return json(s, 201, nuovo);
    }
    const g = id && d.goals.find((v) => String(v.id) === id);
    if (id && m === 'PATCH') {
      if (!g) return json(s, 404, { error: 'non trovato' });
      if (b.progress !== undefined && !progressoValido(b.progress)) return json(s, 400, { error: 'progress non valido' });
      if (b.title !== undefined && !testoPieno(b.title)) return json(s, 400, { error: 'title vuoto' });
      if (b.progress !== undefined) g.progress = b.progress;
      if (b.title !== undefined) g.title = b.title.trim();
      salva(d); return json(s, 200, g);
    }
    if (id && m === 'DELETE') {
      if (!g) return json(s, 404, { error: 'non trovato' });
      d.goals = d.goals.filter((v) => v !== g); salva(d); return json(s, 204);
    }
  }
  return json(s, 404, { error: 'rotta inesistente' });
}).listen(8080);
