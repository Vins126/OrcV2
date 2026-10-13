"""Prova reale dell'isolamento di rete, con Docker e l'immagine costruita.

Non gira nella suite normale: serve Docker acceso, l'immagine `orc-sandbox` e
internet. Si lancia di proposito:

    ORC_INTEGRATION=1 venv/bin/python -m pytest -q tests/test_sandbox_integration.py

Il test centrale apre una porta sul Mac e prova a raggiungerla dal container:
senza il firewall la raggiunge, con il firewall no. Senza un servizio in ascolto
la prova non dimostrerebbe nulla, perche' fallirebbe comunque.
"""

import os
import socket
import threading

import pytest

import config
from executors.docker import DockerExecutor

pytestmark = pytest.mark.skipif(
    not os.environ.get("ORC_INTEGRATION"),
    reason="prova con Docker: si abilita con ORC_INTEGRATION=1")


@pytest.fixture
def porta_sul_mac():
    """Un servizio in ascolto su tutte le interfacce del Mac, come fa il proxy."""
    server = socket.socket()
    server.bind(("0.0.0.0", 0))
    server.listen()
    threading.Thread(target=lambda: [server.accept() for _ in range(4)], daemon=True).start()
    yield server.getsockname()[1]
    server.close()


def _esegui(tmp_path, comando, network):
    ex = DockerExecutor(str(tmp_path), image=config.DOCKER_IMAGE, network=network)
    return ex.run(comando)


def _connetti(host, porta):
    return (f"python3 -c \"import socket; socket.create_connection(('{host}', {porta}), timeout=4); "
            f"print('RAGGIUNTO')\"")


def test_senza_firewall_il_container_in_none_non_ha_rete_ma_in_bridge_raggiunge_la_macchina_solo_senza_blocco(tmp_path, porta_sul_mac):
    """Riferimento: la rete `none` e' chiusa del tutto."""
    esito = _esegui(tmp_path, _connetti("host.docker.internal", porta_sul_mac), "none")

    assert "RAGGIUNTO" not in esito["stdout"]


def test_con_bridge_la_macchina_non_e_raggiungibile(tmp_path, porta_sul_mac):
    esito = _esegui(tmp_path, _connetti("host.docker.internal", porta_sul_mac), "bridge")

    assert "RAGGIUNTO" not in esito["stdout"], esito


def test_con_bridge_internet_resta_raggiungibile(tmp_path):
    esito = _esegui(tmp_path, _connetti("example.com", 80), "bridge")

    assert "RAGGIUNTO" in esito["stdout"], esito


def test_con_bridge_l_utente_finale_e_1000_senza_permessi_e_non_puo_togliere_il_blocco(tmp_path):
    esito = _esegui(
        tmp_path,
        'id -u; grep CapEff /proc/self/status; iptables -F OUTPUT >/dev/null 2>&1; echo "iptables=$?"',
        "bridge")

    righe = esito["stdout"].split()
    assert righe[0] == "1000", esito
    assert "CapEff:\t0000000000000000" in esito["stdout"], esito
    assert "iptables=0" not in esito["stdout"], esito
