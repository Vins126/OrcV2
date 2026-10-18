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


@pytest.fixture(autouse=True)
def limitatore_container_pulito(monkeypatch, tmp_path):
    """Il limitatore dei container e' di modulo: ogni test riparte da uno nuovo, con i
    posti in una cartella temporanea (mai in quella vera, condivisa con le campagne)."""
    import config
    from executors import docker
    monkeypatch.setattr(config, "DOCKER_SLOTS_DIR", str(tmp_path / "docker-slots"))
    docker.reset_shared_limiter()
    yield
    docker.reset_shared_limiter()
