// Sito di riferimento del compito 000098 (noleggio auto), scritto a mano: serve
// solo a provare che lo script di valutazione da' 100 su un sito che rispetta
// contratto, marcatori e testo del compito. Node senza dipendenze npm.
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DATI = 'data', DB = path.join(DATI, 'db.json');
const METODI = ['carta', 'paypal', 'bonifico'];
const CATALOGO = [
  { id: 1, name: 'Fiat Panda', type: 'utilitaria', price_per_day: 35 },
  { id: 2, name: 'Volkswagen Golf', type: 'berlina', price_per_day: 55 },
  { id: 3, name: 'Jeep Compass', type: 'SUV', price_per_day: 80 },
];
fs.mkdirSync(DATI, { recursive: true });
const leggi = () => (fs.existsSync(DB) ? JSON.parse(fs.readFileSync(DB, 'utf8'))
  : { next: 1, cars: CATALOGO, bookings: [] });
const salva = (d) => fs.writeFileSync(DB, JSON.stringify(d));
const json = (s, code, v) => { s.statusCode = code; s.setHeader('content-type', 'application/json'); s.end(v === undefined ? '' : JSON.stringify(v)); };
const corpo = (q) => new Promise((ok) => { const p = []; q.on('data', (c) => p.push(c)); q.on('end', () => ok(Buffer.concat(p).toString())); });

// Data ISO `YYYY-MM-DD` o `YYYY-MM-DDTHH:MM` -> millisecondi (letta come UTC), oppure null.
function istante(v) {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(v)) return null;
  const t = Date.parse((v.length === 10 ? v + 'T00:00' : v) + ':00Z');
  return Number.isNaN(t) ? null : t;
}
const giorni = (a, b) => Math.max(1, Math.ceil((istante(b) - istante(a)) / 86400000));
const sovrapposta = (d, carId, a, b, salvo) => d.bookings.some((x) => x.car_id === carId && x.status !== 'cancelled'
  && x.id !== salvo && istante(x.start_date) < istante(b) && istante(a) < istante(x.end_date));

// Controlla una prenotazione completa; restituisce [codice, messaggio] o null.
function errore(d, p, salvo) {
  if (istante(p.start_date) === null || istante(p.end_date) === null) return [400, 'date mancanti o malformate'];
  if (istante(p.end_date) <= istante(p.start_date)) return [400, 'la fine deve seguire l\'inizio'];
  if (!METODI.includes(p.payment_method)) return [400, 'metodo di pagamento non valido'];
  if (!d.cars.find((c) => c.id === p.car_id)) return [404, 'auto inesistente'];
  if (p.status !== 'cancelled' && sovrapposta(d, p.car_id, p.start_date, p.end_date, salvo)) return [409, 'auto gia\' prenotata'];
  return null;
}

const PAGINA = `<!doctype html><html lang="it"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Noleggio auto</title>
<style>
body{background:#FFEFD5;font-family:sans-serif;margin:0;padding:16px;max-width:900px}
nav{background:#FF8C00;padding:8px;border-radius:6px}nav a{color:#fff;margin-right:12px;text-decoration:none;font-weight:bold}
#nav-bookings{background:#FF8C00}
.card{display:inline-block;border:2px solid #FF8C00;border-radius:8px;padding:10px;margin:6px;cursor:pointer;background:#fff}
.card.scelta{background:#FF8C00;color:#fff}
button{background:#FF8C00;color:#fff;border:0;border-radius:6px;padding:8px 14px;cursor:pointer}
button:disabled{opacity:.5}.si{color:green;font-weight:bold}.no{color:#b00;font-weight:bold}
.vista{display:none}.vista.attiva{display:block}li{margin:6px 0}
</style>
<nav><a href="#" id="nav-home">Catalogo</a><a href="#" id="nav-bookings" data-testid="nav-bookings">Le mie prenotazioni</a></nav>
<main>
<section id="v-catalogo" class="vista attiva"><h1>Scegli un'auto</h1><div id="auto"></div>
<p><label>Ritiro <input type="datetime-local" data-testid="date-start" id="inizio"></label>
<label>Riconsegna <input type="datetime-local" data-testid="date-end" id="fine"></label></p>
<p data-testid="availability-status" id="disp">Scegli auto e date</p>
<button data-testid="book-car" id="prenota" disabled>Prenota</button></section>
<section id="v-riepilogo" class="vista"><h1>Riepilogo</h1><div data-testid="booking-summary" id="riep"></div>
<p>Metodo di pagamento:</p><div id="metodi"></div>
<p><button data-testid="edit-booking" id="modifica">Modifica</button> <button data-testid="confirm-payment" id="paga">Paga</button></p></section>
<section id="v-conferma" class="vista"><h1>Prenotazione confermata</h1><p>Codice: <strong data-testid="booking-reference" id="codice"></strong></p></section>
<section id="v-elenco" class="vista"><h1>Le mie prenotazioni</h1><ul id="elenco"></ul></section>
</main>
<script>
let cars = [], scelta = null, metodo = null;
const $ = (id) => document.getElementById(id);
const fmt = (v) => v.slice(8, 10) + '/' + v.slice(5, 7) + '/' + v.slice(0, 4) + ' ' + (v.slice(11, 16) || '00:00');
function mostra(v) { document.querySelectorAll('.vista').forEach((s) => s.classList.toggle('attiva', s.id === v)); }
function giorni(a, b) { return Math.max(1, Math.ceil((Date.parse(b + ':00Z') - Date.parse(a + ':00Z')) / 86400000)); }
async function controlla() {
  const a = $('inizio').value, b = $('fine').value, disp = $('disp');
  $('prenota').disabled = true;
  if (!scelta || !a || !b) { disp.textContent = 'Scegli auto e date'; disp.className = ''; return; }
  const r = await fetch('/api/cars/' + scelta.id + '/availability?start=' + encodeURIComponent(a) + '&end=' + encodeURIComponent(b));
  if (!r.ok) { disp.textContent = 'Date non valide'; disp.className = 'no'; return; }
  const ok = (await r.json()).available;
  disp.textContent = ok ? 'Disponibile' : 'Non disponibile'; disp.className = ok ? 'si' : 'no';
  $('prenota').disabled = !ok;
}
async function catalogo() {
  cars = await (await fetch('/api/cars')).json();
  $('auto').innerHTML = cars.map((c) => '<div class="card" data-testid="car-card" data-id="' + c.id + '"><b>' + c.name +
    '</b><br>Tipo: ' + c.type + '<br>' + c.price_per_day + ' euro al giorno</div>').join('');
  document.querySelectorAll('[data-testid=car-card]').forEach((el) => el.onclick = () => {
    scelta = cars.find((c) => String(c.id) === el.dataset.id);
    document.querySelectorAll('.card').forEach((x) => x.classList.toggle('scelta', x === el));
    controlla();
  });
}
$('inizio').addEventListener('change', controlla); $('fine').addEventListener('change', controlla);
$('prenota').onclick = async () => {
  const a = $('inizio').value, b = $('fine').value;
  $('riep').innerHTML = '<p>Auto: ' + scelta.name + ' (' + scelta.type + ')</p><p>Dal ' + fmt(a) + ' al ' + fmt(b) +
    '</p><p>Totale: ' + (giorni(a, b) * scelta.price_per_day).toFixed(2) + ' euro</p>';
  const metodi = await (await fetch('/api/payment-methods')).json(); metodo = metodi[0];
  $('metodi').innerHTML = metodi.map((m, i) => '<label data-testid="payment-option"><input type="radio" name="pm" value="' + m + '"' +
    (i === 0 ? ' checked' : '') + '> ' + m + '</label> ').join('');
  document.querySelectorAll('input[name=pm]').forEach((r) => r.onchange = () => { metodo = r.value; });
  mostra('v-riepilogo');
};
$('modifica').onclick = () => mostra('v-catalogo');
$('paga').onclick = async () => {
  const r = await fetch('/api/bookings', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ car_id: scelta.id, start_date: $('inizio').value, end_date: $('fine').value, payment_method: metodo }) });
  if (!r.ok) { alert('Prenotazione non riuscita'); return; }
  $('codice').textContent = (await r.json()).reference; mostra('v-conferma');
};
$('nav-home').onclick = (e) => { e.preventDefault(); mostra('v-catalogo'); };
$('nav-bookings').onclick = async (e) => {
  e.preventDefault();
  const lista = await (await fetch('/api/bookings')).json();
  $('elenco').innerHTML = lista.map((p) => { const c = cars.find((x) => x.id === p.car_id) || { name: '?' };
    return '<li data-testid="booking-row">' + p.reference + ' - ' + c.name + ' - dal ' + fmt(p.start_date) + ' al ' + fmt(p.end_date) +
      ' - ' + p.total_price.toFixed(2) + ' euro - ' + p.status + '</li>'; }).join('') || '<li>Nessuna prenotazione</li>';
  mostra('v-elenco');
};
catalogo();
</script></html>`;

http.createServer(async (q, s) => {
  const url = new URL(q.url, 'http://x'); const parti = url.pathname.split('/').filter(Boolean);
  if (parti[0] !== 'api') { s.setHeader('content-type', 'text/html'); return s.end(PAGINA); }
  const d = leggi();
  if (parti[1] === 'payment-methods' && parti.length === 2 && q.method === 'GET') return json(s, 200, METODI);
  if (parti[1] === 'cars') {
    if (parti.length === 2 && q.method === 'GET') return json(s, 200, d.cars);
    if (parti.length === 4 && parti[3] === 'availability' && q.method === 'GET') {
      const car = d.cars.find((c) => String(c.id) === parti[2]); if (!car) return json(s, 404, { error: 'auto inesistente' });
      const a = url.searchParams.get('start'), b = url.searchParams.get('end');
      if (istante(a) === null || istante(b) === null || istante(b) <= istante(a)) return json(s, 400, { error: 'date non valide' });
      return json(s, 200, { available: !sovrapposta(d, car.id, a, b) });
    }
  }
  if (parti[1] === 'bookings') {
    let p = null;
    if (q.method === 'POST' || q.method === 'PATCH') { try { p = JSON.parse((await corpo(q)) || '{}'); } catch { return json(s, 400, { error: 'JSON non valido' }); } }
    if (p !== null && (typeof p !== 'object' || Array.isArray(p))) return json(s, 400, { error: 'corpo non valido' });
    if (parti.length === 2 && q.method === 'GET') return json(s, 200, d.bookings);
    if (parti.length === 2 && q.method === 'POST') {
      if (typeof p.car_id !== 'number') return json(s, 400, { error: 'car_id mancante' });
      const nuova = { car_id: p.car_id, start_date: p.start_date, end_date: p.end_date, payment_method: p.payment_method, status: 'confirmed' };
      const e = errore(d, nuova); if (e) return json(s, e[0], { error: e[1] });
      const car = d.cars.find((c) => c.id === nuova.car_id);
      Object.assign(nuova, { id: d.next, reference: 'NOL-' + d.next + '-' + crypto.randomBytes(3).toString('hex').toUpperCase(),
        total_price: giorni(nuova.start_date, nuova.end_date) * car.price_per_day });
      d.next++; d.bookings.push(nuova); salva(d); return json(s, 201, nuova);
    }
    const i = d.bookings.findIndex((x) => String(x.id) === parti[2]);
    if (parti.length !== 3 || i === -1) return json(s, 404, { error: 'prenotazione inesistente' });
    if (q.method === 'GET') return json(s, 200, d.bookings[i]);
    if (q.method === 'DELETE') { d.bookings.splice(i, 1); salva(d); s.statusCode = 204; return s.end(); }
    if (q.method === 'PATCH') {
      if ('status' in p && p.status !== 'cancelled') return json(s, 400, { error: 'stato non valido' });
      const nuova = { ...d.bookings[i] };
      for (const k of ['start_date', 'end_date', 'payment_method', 'status']) if (k in p) nuova[k] = p[k];
      const e = errore(d, nuova, nuova.id); if (e) return json(s, e[0], { error: e[1] });
      nuova.total_price = giorni(nuova.start_date, nuova.end_date) * d.cars.find((c) => c.id === nuova.car_id).price_per_day;
      d.bookings[i] = nuova; salva(d); return json(s, 200, nuova);
    }
  }
  return json(s, 404, { error: 'rotta inesistente' });
}).listen(8080);
