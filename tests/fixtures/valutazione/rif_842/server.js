// Sito di riferimento del compito 842, scritto a mano: serve solo a provare che
// lo script di valutazione da' 100 su un sito che rispetta marcatori e testo.
// Tutti i dati sono simulati nel browser: il server consegna una sola pagina.
const http = require('http');

const PAGINA = `<!doctype html><html lang="it"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Security Center 3.7</title>
<style>body{font-family:sans-serif;margin:0;padding:16px;max-width:1100px;background:#fff;color:#111}
section{border:1px solid #ccc;border-radius:6px;padding:12px;margin:12px 0}
table{border-collapse:collapse}td,th{padding:4px 10px;text-align:left}
.online{color:#0a6b2d;font-weight:bold}.offline{color:#a11;font-weight:bold}
.cambiato{background:#fff3cd;border-left:4px solid #e0a800;padding:4px 8px;margin:4px 0}
.prima{text-decoration:line-through;color:#a11}.dopo{color:#0a6b2d;font-weight:bold}
#frame{font-family:monospace;background:#f4f4f4;padding:8px;margin:8px 0}</style>
<h1>Security Center 3.7</h1>
<section><h2>Federated Learning Console</h2>
<h3>Participant status (heartbeat)</h3>
<table><thead><tr><th>Participant</th><th>State</th><th>Last heartbeat</th></tr></thead><tbody id="partecipanti"></tbody></table>
<h3>Paillier encryption time (ms)</h3>
<svg data-testid="encryption-chart" width="600" height="220" viewBox="0 0 600 220" role="img" aria-label="Paillier encryption time">
<line x1="40" y1="190" x2="590" y2="190" stroke="#333"/><line x1="40" y1="10" x2="40" y2="190" stroke="#333"/>
<text x="5" y="20" font-size="11">ms</text><text x="540" y="210" font-size="11">round</text>
<polyline id="curva" fill="none" stroke="#1f4e79" stroke-width="2" points=""/></svg>
</section>
<section><h2>Audit Tracker</h2>
<h3>Operation replay</h3>
<div id="frame" data-testid="replay-frame"></div>
<button data-testid="replay-step">Step</button>
<button data-testid="replay-play">Play</button>
<button data-testid="replay-pause">Pause</button>
<input type="range" data-testid="replay-timeline" id="timeline" min="0" value="0" aria-label="timeline">
<span data-testid="replay-position" id="posizione"></span>
<h3>Configuration diff</h3>
<div id="diff"></div>
</section>
<script>
// Partecipanti simulati: l'heartbeat si aggiorna ogni secondo, lo stato cambia a caso.
const partecipanti = ['node-A', 'node-B', 'node-C', 'node-D'].map((n) => ({ nome: n, online: true, ultimo: Date.now() }));
function disegnaPartecipanti() {
  document.getElementById('partecipanti').innerHTML = partecipanti.map((p) =>
    '<tr><td>' + p.nome + '</td><td data-testid="participant-status" class="' + (p.online ? 'online' : 'offline') + '">' +
    (p.online ? 'online' : 'offline') + '</td><td data-testid="participant-heartbeat">' +
    Math.round((Date.now() - p.ultimo) / 1000) + ' s ago (' + new Date(p.ultimo).toLocaleTimeString('en-GB') + ')</td></tr>').join('');
}
setInterval(() => {
  partecipanti.forEach((p) => { if (Math.random() < 0.1) p.online = !p.online; if (p.online && Math.random() < 0.6) p.ultimo = Date.now(); });
  disegnaPartecipanti();
}, 1000);
disegnaPartecipanti();

// Curva dei tempi di cifratura Paillier (simulati).
const tempi = Array.from({ length: 20 }, (_, i) => 40 + 30 * Math.sin(i / 3) + 20 * Math.random());
document.getElementById('curva').setAttribute('points',
  tempi.map((t, i) => (40 + i * 28) + ',' + (190 - t * 1.5)).join(' '));

// Operazioni registrate e riproduzione fotogramma per fotogramma.
const operazioni = ['10:00:01 admin login', '10:00:15 open config "aggregation"', '10:00:32 set rounds 10 -> 20',
  '10:01:05 set key_size 1024 -> 2048', '10:01:40 add participant node-D', '10:02:10 save config',
  '10:02:30 export audit log', '10:03:00 admin logout'];
let corrente = 0, timer = null;
const timeline = document.getElementById('timeline');
timeline.max = operazioni.length - 1;
function mostra(i) {
  corrente = Math.max(0, Math.min(operazioni.length - 1, i));
  document.getElementById('frame').textContent = '#' + (corrente + 1) + ' ' + operazioni[corrente];
  document.getElementById('posizione').textContent = 'Frame ' + (corrente + 1) + '/' + operazioni.length;
  timeline.value = corrente;
}
function ferma() { clearInterval(timer); timer = null; }
document.querySelector('[data-testid=replay-step]').onclick = () => mostra(corrente + 1);
document.querySelector('[data-testid=replay-play]').onclick = () => {
  ferma();
  if (corrente === operazioni.length - 1) mostra(0);
  timer = setInterval(() => { if (corrente >= operazioni.length - 1) ferma(); else mostra(corrente + 1); }, 1000);
};
document.querySelector('[data-testid=replay-pause]').onclick = ferma;
timeline.oninput = () => mostra(Number(timeline.value));
mostra(0);

// Differenze di configurazione prima/dopo.
const prima = { rounds: 10, key_size: 1024, learning_rate: 0.01, participants: 3 };
const dopo = { rounds: 20, key_size: 2048, learning_rate: 0.01, participants: 4 };
document.getElementById('diff').innerHTML = Object.keys(prima).map((k) => prima[k] === dopo[k]
  ? '<div>' + k + ': ' + prima[k] + '</div>'
  : '<div class="cambiato" data-testid="diff-changed">' + k + ': <span class="prima" data-testid="diff-before">' + prima[k] +
    '</span> &rarr; <span class="dopo" data-testid="diff-after">' + dopo[k] + '</span></div>').join('');
</script></html>`;

http.createServer((q, s) => {
  if (q.method === 'GET' && (q.url === '/' || q.url === '/index.html')) {
    s.setHeader('content-type', 'text/html; charset=utf-8');
    s.end(PAGINA);
  } else { s.statusCode = 404; s.end(); }
}).listen(8080, '0.0.0.0');
