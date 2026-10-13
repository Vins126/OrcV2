# Sandbox degli agenti: Python, pytest e Node a versioni fissate.
#
# Costruzione (dalla radice del progetto):
#   docker build -f docker/sandbox.Dockerfile -t orc-sandbox:m2s4 docker/
#
# Le due immagini di base sono bloccate dal loro identificativo (digest): le
# etichette come `3.14-slim-bookworm` cambiano contenuto nel tempo, il digest no.
# Versioni scelte il 9 ottobre 2026 sulle fonti ufficiali:
#   Python 3.14   (fase bugfix, devguide.python.org/versions)
#   Node 24 LTS   (nodejs.org/en/about/previous-releases)
#   pytest 9.1.1  (PyPI)
# Per aggiornare: cambiare i digest e il numero di versione, ricostruire e
# cambiare il tag (`m2s4` -> nuovo), cosi' le misure fatte con l'ambiente vecchio
# restano distinguibili da quelle fatte con il nuovo.

FROM node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS node

FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83

# Node e npm arrivano dall'immagine ufficiale Node.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN pip install --no-cache-dir pytest==9.1.1

# Firewall della condizione "con internet" (vedi sandbox-entrypoint.sh). Il
# pacchetto arriva da `apt` nella versione di Debian del giorno della costruzione:
# e' l'unica parte dell'immagine non bloccata da un numero di versione.
RUN apt-get update \
 && apt-get install -y --no-install-recommends iptables \
 && rm -rf /var/lib/apt/lists/*

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
