"""Impostazioni comuni a tutta la suite.

I test non devono dipendere da Docker, dal `.env` ne' dalla rete. La lettura
dell'immagine della sandbox (`docker image inspect`) e' l'unico punto che
chiamerebbe Docker senza che il test lo sappia: qui viene sostituita con un
finto che dichiara l'immagine presente. Un test che vuole l'immagine assente la
sovrascrive con `monkeypatch`.
"""

import pytest


@pytest.fixture(autouse=True)
def immagine_sandbox_presente(monkeypatch):
    monkeypatch.setattr("executors.docker.image_id", lambda image: "sha256:immagine-finta")


@pytest.fixture(autouse=True)
def nessuna_attesa_vera(monkeypatch):
    """Il controllo dell'immagine aspetta l'avvio di Docker: nei test non si dorme davvero."""
    monkeypatch.setattr("executors.docker._attendi", lambda secondi: None)
