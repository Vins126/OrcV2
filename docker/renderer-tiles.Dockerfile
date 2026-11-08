# Immagine dei riquadri per il giudizio di sensibilita' (MH-4): l'immagine del
# renderer della campagna, identica, con in piu' lo script dei riquadri.
# `orc-renderer:r1` (view_site, cancello, valutazione) non si ricostruisce.
#
#   docker build -f docker/renderer-tiles.Dockerfile -t orc-renderer:r1t docker
ARG BASE=orc-renderer:r1
FROM ${BASE}

COPY --chmod=0755 render_tiles.py /opt/orc/render_tiles.py
