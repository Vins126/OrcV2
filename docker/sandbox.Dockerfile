# Sandbox degli agenti: Python, pytest, Node, skill e programmi dell'harness.
#
# Costruzione (dalla radice del progetto):
#   python fetch_skills.py && docker build -f docker/sandbox.Dockerfile -t orc-sandbox:r3h docker/
#
# Le due immagini di base sono bloccate dal loro identificativo (digest): le
# etichette come `3.14-slim-bookworm` cambiano contenuto nel tempo, il digest no.
# Versioni scelte il 9 ottobre 2026 sulle fonti ufficiali:
#   Python 3.14   (fase bugfix, devguide.python.org/versions)
#   Node 24 LTS   (nodejs.org/en/about/previous-releases)
#   pytest 9.1.1  (PyPI)
# Per aggiornare: cambiare i digest e il numero di versione, ricostruire e
# cambiare il tag (`r3h` -> nuovo), cosi' le misure fatte con l'ambiente vecchio
# restano distinguibili da quelle fatte con il nuovo.

FROM node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS node

FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83

ARG TARGETARCH

# Node e npm arrivano dall'immagine ufficiale Node.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN pip install --no-cache-dir pytest==9.1.1

# Firewall della condizione "con internet" (vedi sandbox-entrypoint.sh).
# Dal 4 nov 2026 Java serve anche al validatore HTML vnu. I pacchetti di sistema
# arrivano da `apt` nella versione di Debian del giorno della costruzione.
RUN apt-get update \
 && apt-get install -y --no-install-recommends iptables default-jre-headless \
 && rm -rf /var/lib/apt/lists/*

# Dal 4 nov 2026 strumenti comuni a tutti i bracci per provare e correggere i
# siti. Versioni fissate pubblicate da almeno due settimane alla scelta.
# Chromium e' scaricato dalla stessa versione di Playwright che lo pilota.
# /usr/bin/chromium e' un lanciatore con --no-sandbox: nel container il sandbox
# di Chrome non puo' partire (niente namespace utente) e Chrome cade subito, come
# visto con gli script di taste-skill. L'isolamento resta quello del container.
RUN pip install --no-cache-dir playwright==1.64.0
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium \
 && chrome="$(find /ms-playwright -type f -path '*/chromium-*/chrome-linux*/chrome' -print -quit)" \
 && test -n "$chrome" \
 && printf '#!/bin/sh\nexec "%s" --no-sandbox "$@"\n' "$chrome" > /usr/bin/chromium \
 && chmod 0755 /usr/bin/chromium \
 && chmod -R a+rX /ms-playwright \
 && rm -rf /var/lib/apt/lists/*
ENV CHROME_PATH=/usr/bin/chromium

# Hurl verifica le risposte HTTP; il pacchetto segue l'architettura di build.
ADD https://github.com/Orange-OpenSource/hurl/releases/download/8.0.1/hurl_8.0.1_${TARGETARCH}.deb /tmp/hurl.deb
RUN apt-get update \
 && apt-get install -y --no-install-recommends /tmp/hurl.deb \
 && rm -f /tmp/hurl.deb \
 && rm -rf /var/lib/apt/lists/*

# Lighthouse misura il sito in Chromium, gli altri programmi controllano codice,
# markup e test. vnu-jar include build/dist/vnu.jar; Java e' gia' installato.
RUN npm install -g lighthouse@13.5.0 @biomejs/biome@2.5.15 htmlhint@1.9.2 vitest@4.1.12 vnu-jar@26.10.12 \
 && test -f "$(npm root -g)/vnu-jar/build/dist/vnu.jar" \
 && rm -f /usr/local/bin/vnu \
 && printf '#!/bin/sh\nexec java -jar "%s/vnu-jar/build/dist/vnu.jar" "$@"\n' "$(npm root -g)" > /usr/local/bin/vnu \
 && chmod 0755 /usr/local/bin/vnu

# Skill fissate dal manifesto il 4 nov 2026; anche l'utente 1000 deve leggerle
# ed eseguire gli script allegati. Il contesto di costruzione e' docker/.
COPY skills/ /opt/skills/
RUN chmod -R a+rX /opt/skills

COPY --chmod=0755 sandbox-entrypoint.sh /usr/local/bin/sandbox-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/sandbox-entrypoint.sh"]

# Il filesystem del container e' in sola lettura: niente file `.pyc` nelle
# cartelle di sistema. Il workspace montato su /workspace resta scrivibile.
ENV PYTHONDONTWRITEBYTECODE=1

# L'utente 1000:1000 non esiste nell'immagine, quindi Docker imposterebbe
# HOME=/, che in sola lettura non e' scrivibile: npm e pip (installazioni
# fatte nella condizione "con internet") fallirebbero. /tmp e' l'unica area
# scrivibile oltre al workspace, ed e' effimera come il container.
ENV HOME=/tmp \
    npm_config_cache=/tmp/.npm \
    PIP_CACHE_DIR=/tmp/.cache/pip
