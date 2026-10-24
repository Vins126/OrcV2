// Sito di riferimento del compito 684, scritto a mano: serve solo a provare che
// lo script di valutazione da' 100 su un sito che rispetta contratto e marcatori.
const http = require('http');
const fs = require('fs');
const path = require('path');
const DATI = 'data', META = path.join(DATI, 'files.json'), UP = path.join(DATI, 'uploads');
fs.mkdirSync(UP, { recursive: true });
const leggi = () => (fs.existsSync(META) ? JSON.parse(fs.readFileSync(META, 'utf8')) : { next: 1, files: [] });
const salva = (d) => fs.writeFileSync(META, JSON.stringify(d));
const pubblico = (f) => ({ id: f.id, name: f.name, size: f.size, tags: f.tags });
const json = (s, code, v) => { s.statusCode = code; s.setHeader('content-type', 'application/json'); s.end(v === undefined ? '' : JSON.stringify(v)); };
const corpo = (q) => new Promise((ok) => { const p = []; q.on('data', (c) => p.push(c)); q.on('end', () => ok(Buffer.concat(p))); });

function multipart(buf, tipo) {
  const m = /boundary=(.+)$/.exec(tipo || ''); if (!m) return null;
  const sep = Buffer.from('--' + m[1]); let i = buf.indexOf(sep);
  while (i !== -1) {
    const j = buf.indexOf(sep, i + sep.length); if (j === -1) break;
    const parte = buf.slice(i + sep.length + 2, j - 2); const fine = parte.indexOf('\r\n\r\n');
    const testa = parte.slice(0, fine).toString();
    const nome = /name="file"; filename="([^"]*)"/.exec(testa);
    if (nome) return { filename: nome[1], data: parte.slice(fine + 4) };
    i = j;
  }
  return null;
}

const PAGINA = `<!doctype html><html lang="it"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Etichette dei file</title>
<style>body{font-family:sans-serif;margin:0;padding:16px;max-width:900px}li{list-style:none;border:1px solid #ccc;border-radius:6px;padding:8px;margin:8px 0}
.tag{display:inline-block;background:#1f4e79;color:#fff;border-radius:10px;padding:2px 8px;margin:2px}
.tag button{background:none;border:0;color:#fff;cursor:pointer}nav button.attivo{font-weight:bold}</style>
<main><h1>Gestione file</h1>
<label>File <input type="file" data-testid="upload-input"></label> <button data-testid="upload-submit">Carica</button>
<nav aria-label="filtri" id="filtri"></nav><ul id="lista"></ul></main>
<script>
let filtro = null;
async function disegna() {
  const files = await (await fetch('/api/files')).json();
  const tutte = [...new Set(files.flatMap(f => f.tags))].sort();
  document.getElementById('filtri').innerHTML = tutte.map(t =>
    '<button data-testid="filter-tag" class="' + (t === filtro ? 'attivo' : '') + '">' + t + '</button>').join(' ') +
    ' <button data-testid="filter-clear">Tutti</button>';
  document.querySelectorAll('[data-testid=filter-tag]').forEach(b => b.onclick = () => { filtro = b.textContent; disegna(); });
  document.querySelector('[data-testid=filter-clear]').onclick = () => { filtro = null; disegna(); };
  const visibili = filtro ? files.filter(f => f.tags.includes(filtro)) : files;
  document.getElementById('lista').innerHTML = visibili.map(f =>
    '<li data-testid="file-item" data-id="' + f.id + '"><span data-testid="file-name">' + f.name + '</span> ' +
    f.tags.map(t => '<span class="tag" data-testid="file-tag">' + t + '<button data-testid="tag-remove" aria-label="togli ' + t + '">x</button></span>').join('') +
    ' <input data-testid="tag-input" aria-label="nuova etichetta"> <button data-testid="tag-add">Aggiungi</button>' +
    ' <button data-testid="file-delete">Elimina</button></li>').join('');
  document.querySelectorAll('[data-testid=file-item]').forEach(li => {
    const id = li.dataset.id, f = files.find(x => String(x.id) === id);
    const metti = async (tags) => { await fetch('/api/files/' + id + '/tags', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ tags }) }); disegna(); };
    li.querySelector('[data-testid=tag-add]').onclick = () => { const v = li.querySelector('[data-testid=tag-input]').value.trim(); if (v) metti([...f.tags, v]); };
    li.querySelectorAll('[data-testid=tag-remove]').forEach((b, k) => b.onclick = () => metti(f.tags.filter((_, n) => n !== k)));
    li.querySelector('[data-testid=file-delete]').onclick = async () => { await fetch('/api/files/' + id, { method: 'DELETE' }); disegna(); };
  });
}
document.querySelector('[data-testid=upload-submit]').onclick = async () => {
  const input = document.querySelector('[data-testid=upload-input]'); if (!input.files[0]) return;
  const fd = new FormData(); fd.append('file', input.files[0]); await fetch('/api/files', { method: 'POST', body: fd });
  input.value = ''; disegna();
};
disegna();
</script></html>`;

http.createServer(async (q, s) => {
  const url = new URL(q.url, 'http://x'); const parti = url.pathname.split('/').filter(Boolean);
  if (parti[0] !== 'api' || parti[1] !== 'files') { s.setHeader('content-type', 'text/html'); return s.end(PAGINA); }
  const d = leggi(); const id = parti[2]; const f = id && d.files.find((x) => String(x.id) === id);
  if (!id && q.method === 'GET') { const t = url.searchParams.get('tag'); return json(s, 200, d.files.filter((x) => !t || x.tags.includes(t)).map(pubblico)); }
  if (!id && q.method === 'POST') {
    const up = multipart(await corpo(q), q.headers['content-type']); if (!up) return json(s, 400, { error: 'file mancante' });
    const nuovo = { id: d.next++, name: up.filename, size: up.data.length, tags: [] };
    fs.writeFileSync(path.join(UP, String(nuovo.id)), up.data); d.files.push(nuovo); salva(d); return json(s, 201, pubblico(nuovo));
  }
  if (!f) return json(s, 404, { error: 'non trovato' });
  if (parti[3] === 'content' && q.method === 'GET') return s.end(fs.readFileSync(path.join(UP, String(f.id))));
  if (parti[3] === 'tags' && q.method === 'PUT') {
    let b; try { b = JSON.parse((await corpo(q)).toString()); } catch { b = {}; }
    if (!Array.isArray(b.tags) || b.tags.some((t) => typeof t !== 'string' || !t.trim())) return json(s, 400, { error: 'tags' });
    f.tags = [...new Set(b.tags.map((t) => t.trim()))]; salva(d); return json(s, 200, pubblico(f));
  }
  if (!parti[3] && q.method === 'GET') return json(s, 200, pubblico(f));
  if (!parti[3] && q.method === 'DELETE') { d.files = d.files.filter((x) => x !== f); fs.rmSync(path.join(UP, String(f.id)), { force: true }); salva(d); return json(s, 204); }
  json(s, 405, { error: 'metodo' });
}).listen(8080);
