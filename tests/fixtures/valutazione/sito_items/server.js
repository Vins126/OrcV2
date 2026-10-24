// Mini applicazione d'esempio per le prove reali dell'interprete: un elenco di
// voci salvato in data/items.json, con interfaccia e due rotte.
const http = require('http');
const fs = require('fs');
const FILE = 'data/items.json';
const leggi = () => (fs.existsSync(FILE) ? JSON.parse(fs.readFileSync(FILE, 'utf8')) : []);
const salva = (v) => { fs.mkdirSync('data', { recursive: true }); fs.writeFileSync(FILE, JSON.stringify(v)); };
const PAGINA = `<!doctype html><html lang="it"><meta charset="utf-8"><title>Voci</title>
<main><input data-testid="item-input" aria-label="voce"><button data-testid="item-add">Aggiungi</button>
<ul data-testid="item-list"></ul></main>
<script>
async function disegna() {
  const voci = await (await fetch('/api/items')).json();
  document.querySelector('[data-testid=item-list]').innerHTML =
    voci.map(v => '<li data-testid="item">' + v.name + '</li>').join('');
}
document.querySelector('[data-testid=item-add]').onclick = async () => {
  const name = document.querySelector('[data-testid=item-input]').value;
  await fetch('/api/items', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({name})});
  disegna();
};
disegna();
</script></html>`;
http.createServer((q, s) => {
  if (q.url === '/api/items' && q.method === 'GET') { s.setHeader('content-type', 'application/json'); return s.end(JSON.stringify(leggi())); }
  if (q.url === '/api/items' && q.method === 'POST') {
    let corpo = ''; q.on('data', (c) => (corpo += c));
    return q.on('end', () => {
      let d; try { d = JSON.parse(corpo); } catch { d = {}; }
      if (!d.name) { s.statusCode = 400; return s.end('{}'); }
      const v = leggi(); const voce = { id: v.length + 1, name: d.name }; v.push(voce); salva(v);
      s.statusCode = 201; s.setHeader('content-type', 'application/json'); s.end(JSON.stringify(voce));
    });
  }
  s.setHeader('content-type', 'text/html'); s.end(PAGINA);
}).listen(8080);
