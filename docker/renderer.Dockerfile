# Renderer della valutazione (R1.4): l'immagine della sandbox piu' Chromium e
# Playwright, a versione bloccata.
#
# Si parte dalla sandbox e non dall'immagine ufficiale di Playwright perche' il
# sito deve girare nello stesso ambiente in cui l'agente l'ha costruito: stesso
# Debian, stesso Python 3.14, stesso Node 24. Un modulo compilato nella sandbox
# (esbuild, better-sqlite3) potrebbe non girare su un altro sistema.
#
# Costruzione (dalla radice del progetto, con l'immagine sandbox gia' presente):
#   docker build -f docker/renderer.Dockerfile -t orc-renderer:r1 docker/
#
# La costruzione scarica Chromium e le sue librerie (alcune centinaia di MB). Il
# container si usa poi sempre senza rete.

ARG BASE=orc-sandbox:m2s4
FROM ${BASE}

USER root

# I browser in una cartella di sistema leggibile dall'utente 1000, che nel
# container ha HOME=/tmp (effimera).
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

RUN pip install --no-cache-dir playwright==1.64.0 \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* \
 && chmod -R a+rX /opt/ms-playwright

COPY --chmod=0755 render_site.py /opt/orc/render_site.py
# axe-core 4.14.0 (Deque Systems, MPL-2.0), dal pacchetto npm `axe-core` verificato con il suo sha512.
COPY --chmod=0755 axe.min.js axe-core.LICENSE /opt/orc/
