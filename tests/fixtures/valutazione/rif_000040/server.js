// Sito di riferimento del compito 000040, scritto a mano: serve solo a provare che
// lo script di valutazione da' 100 su un sito che rispetta contratto e marcatori.
const http = require('http');
const fs = require('fs');
const path = require('path');
const DATI = 'data', STORE = path.join(DATI, 'store.json');
fs.mkdirSync(DATI, { recursive: true });

const CATALOGO = [
  { id: 's1', type: 'service', title: 'Leadership coaching (5 sessions)', price: 900 },
  { id: 's2', type: 'service', title: 'Business strategy review', price: 1500 },
  { id: 'w1', type: 'workshop', title: 'Leading remote teams', price: 250, date: '2026-11-05', speaker: 'Laura Bianchi' },
  { id: 'w2', type: 'workshop', title: 'Negotiation essentials', price: 300, date: '2026-12-03', speaker: 'Marco Rossi' },
  { id: 'c1', type: 'class', title: 'Foundations of management', price: 120 },
  { id: 'c2', type: 'class', title: 'Finance for non-financial managers', price: 140 },
];
const POST_BLOG = [
  { title: 'Five habits of effective team leaders', body: 'Effective leaders set clear goals, give regular feedback and make time to listen. In this article we look at five habits you can start practising this week.' },
  { title: 'Why training budgets pay off', body: 'Companies that invest in structured training for their managers see lower turnover and better project delivery. We review recent evidence and practical ways to measure the return.' },
];
const PODCAST = [
  { title: 'Episode 1: Leading through change', desc: 'How to keep a team focused during a reorganisation.' },
  { title: 'Episode 2: Feedback that works', desc: 'Giving feedback that people can act on.' },
];

const leggi = () => (fs.existsSync(STORE) ? JSON.parse(fs.readFileSync(STORE, 'utf8')) : { next: 1, cart: [], orders: [] });
const salva = (d) => fs.writeFileSync(STORE, JSON.stringify(d));
const json = (s, code, v) => { s.statusCode = code; s.setHeader('content-type', 'application/json'); s.end(v === undefined ? '' : JSON.stringify(v)); };
const corpo = (q) => new Promise((ok) => { const p = []; q.on('data', (c) => p.push(c)); q.on('end', () => { try { ok(JSON.parse(Buffer.concat(p).toString() || '{}')); } catch { ok(null); } }); });
const intero = (q) => Number.isInteger(q) && q >= 1;
const pubblico = (v) => ({ id: v.id, itemId: v.itemId, quantity: v.quantity });

const scheda = (v, tid, extra) => '<div class="card" data-testid="' + tid + '"><h3>' + v.title + '</h3>' + (extra || '') +
  '<p>$' + v.price + '</p><button class="btn" data-testid="add-to-cart" data-id="' + v.id + '">Add to cart</button></div>';
const PAGINA = `<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Lead &amp; Grow Consulting</title>
<style>html,body{background:lightcyan;margin:0;font-family:sans-serif}
nav{background:cadetblue;padding:10px}nav a{color:#fff;margin-right:12px;text-decoration:none}
main{padding:16px;max-width:900px}.card{border:2px solid cadetblue;border-radius:6px;padding:8px;margin:8px 0}
.btn{background:cadetblue;color:#fff;border:0;padding:6px 12px;border-radius:4px;cursor:pointer}
section{display:none}section.on{display:block}</style>
<nav data-testid="site-nav">
<a href="#home" data-testid="nav-link-home">Home</a><a href="#services" data-testid="nav-link-services">Services</a>
<a href="#workshops" data-testid="nav-link-workshops">Workshops</a><a href="#classes" data-testid="nav-link-classes">Online Classes</a>
<a href="#podcasts" data-testid="nav-link-podcasts">Podcasts</a><a href="#blogs" data-testid="nav-link-blogs">Blogs</a>
<a href="#contact" data-testid="nav-link-contact">Contact</a><a href="#cart" data-testid="nav-link-cart">Cart</a></nav>
<main>
<section id="home"><h1>Lead &amp; Grow Consulting</h1><p>Leadership and business training for teams and managers.</p></section>
<section id="services"><h2>Services</h2>${CATALOGO.filter(v => v.type === 'service').map(v => scheda(v, 'service-item')).join('')}</section>
<section id="workshops"><h2>Upcoming workshops</h2>${CATALOGO.filter(v => v.type === 'workshop').map(v => scheda(v, 'workshop-item', '<p>Date: ' + v.date + ' - Topic: ' + v.title + ' - Speaker: ' + v.speaker + '</p>')).join('')}</section>
<section id="classes"><h2>Online classes</h2>${CATALOGO.filter(v => v.type === 'class').map(v => scheda(v, 'class-item')).join('')}</section>
<section id="podcasts"><h2>Podcasts</h2>${PODCAST.map(p => '<div class="card" data-testid="podcast-item"><h3>' + p.title + '</h3><p>' + p.desc + '</p></div>').join('')}</section>
<section id="blogs"><h2>Blog</h2>${POST_BLOG.map(p => '<article class="card" data-testid="blog-post"><h3>' + p.title + '</h3><p>' + p.body + '</p></article>').join('')}</section>
<section id="contact"><h2>Contact</h2><p>Email: info@leadgrow.example - Phone: +39 02 1234 5678</p></section>
<section id="cart"><h2>Cart</h2><div id="righe"></div>
<label>Card number <input data-testid="checkout-card"></label> <button class="btn" data-testid="checkout-submit">Pay</button>
<p id="esito"></p></section>
</main>
<script>
const titoli = ${JSON.stringify(Object.fromEntries(CATALOGO.map(v => [v.id, v.title])))};
async function carrello() {
  const c = await (await fetch('/api/cart')).json();
  document.getElementById('righe').innerHTML = c.items.map(r =>
    '<div class="card" data-testid="cart-item">' + titoli[r.itemId] + ' x ' + r.quantity + '</div>').join('') || '<p>Your cart is empty.</p>';
}
function mostra() {
  const id = (location.hash || '#home').slice(1);
  document.querySelectorAll('section').forEach(s => s.classList.toggle('on', s.id === id));
  if (id === 'cart') carrello();
}
window.addEventListener('hashchange', mostra); mostra();
document.querySelectorAll('[data-testid=add-to-cart]').forEach(b => b.onclick = async () => {
  await fetch('/api/cart', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ itemId: b.dataset.id }) });
  b.textContent = 'Added';
});
document.querySelector('[data-testid=checkout-submit]').onclick = async () => {
  const r = await fetch('/api/orders', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ card: document.querySelector('[data-testid=checkout-card]').value }) });
  const esito = document.getElementById('esito');
  if (r.status === 201) { const o = await r.json(); esito.innerHTML = '<span data-testid="order-confirmation">Thank you! Order ' + o.id + ' confirmed, total $' + o.total + '.</span>'; carrello(); }
  else esito.textContent = 'Payment failed: check the card and the cart.';
};
</script></html>`;

http.createServer(async (q, s) => {
  const url = new URL(q.url, 'http://x'), p = url.pathname;
  if (p === '/' || p === '/index.html') { s.setHeader('content-type', 'text/html; charset=utf-8'); return s.end(PAGINA); }
  if (p === '/api/catalog' && q.method === 'GET') return json(s, 200, CATALOGO);
  const d = leggi();
  if (p === '/api/cart') {
    if (q.method === 'GET') return json(s, 200, { items: d.cart.map(pubblico) });
    if (q.method === 'POST') {
      const b = await corpo(q);
      const quantity = b && b.quantity === undefined ? 1 : b && b.quantity;
      if (!b || !CATALOGO.some(v => v.id === b.itemId) || !intero(quantity)) return json(s, 400, { error: 'bad request' });
      const v = { id: String(d.next++), itemId: b.itemId, quantity };
      d.cart.push(v); salva(d); return json(s, 201, pubblico(v));
    }
  }
  let m = /^\/api\/cart\/([^/]+)$/.exec(p);
  if (m) {
    const v = d.cart.find(x => x.id === m[1]);
    if (q.method === 'PATCH') {
      const b = await corpo(q);
      if (!v) return json(s, 404, { error: 'not found' });
      if (!b || !intero(b.quantity)) return json(s, 400, { error: 'bad quantity' });
      v.quantity = b.quantity; salva(d); return json(s, 200, pubblico(v));
    }
    if (q.method === 'DELETE') {
      if (!v) return json(s, 404, { error: 'not found' });
      d.cart = d.cart.filter(x => x !== v); salva(d); s.statusCode = 204; return s.end();
    }
  }
  if (p === '/api/orders' && q.method === 'POST') {
    const b = await corpo(q);
    if (!b || typeof b.card !== 'string' || !b.card.trim() || !d.cart.length) return json(s, 400, { error: 'bad request' });
    const items = d.cart.map(v => ({ itemId: v.itemId, quantity: v.quantity }));
    const total = items.reduce((t, v) => t + CATALOGO.find(c => c.id === v.itemId).price * v.quantity, 0);
    const o = { id: 'o' + d.next++, items, total };
    d.orders.push(o); d.cart = []; salva(d); return json(s, 201, o);
  }
  m = /^\/api\/orders\/([^/]+)$/.exec(p);
  if (m && q.method === 'GET') {
    const o = d.orders.find(x => x.id === m[1]);
    return o ? json(s, 200, o) : json(s, 404, { error: 'not found' });
  }
  json(s, 404, { error: 'not found' });
}).listen(8080);
