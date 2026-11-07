"""Avvia il sito nel container e inoltra la porta locale verso Docker."""

import argparse
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path


def stop_process(process: subprocess.Popen[str]) -> None:
    """Ferma tutto il gruppo, compresi i figli lanciati da start.sh."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def print_log(process: subprocess.Popen[str]) -> None:
    """Riporta su stdout sia l'output sia gli errori dello script del sito."""
    if process.stdout is not None:
        for line in process.stdout:
            print(line, end="", flush=True)


def wait_for_site(process: subprocess.Popen[str], port: int, timeout: float,
                  stopped: threading.Event) -> str | None:
    """Aspetta la porta entro il termine, osservando anche il processo e i segnali."""
    deadline = time.monotonic() + timeout
    while not stopped.is_set() and time.monotonic() < deadline:
        if process.poll() is not None:
            return f"start.sh e' terminato con codice {process.returncode} senza aprire la porta {port}"
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return None
        except OSError:
            stopped.wait(0.1)
    return None if stopped.is_set() else f"porta {port} non aperta entro {timeout:g} s"


def forward(source: socket.socket, target: socket.socket) -> None:
    """Inoltra una direzione; chiude solo la scrittura per lasciare passare la risposta."""
    try:
        while data := source.recv(65536):
            target.sendall(data)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def relay(client: socket.socket, port: int) -> None:
    """Gestisce una connessione con un thread per ciascuna direzione."""
    with client:
        try:
            upstream = socket.create_connection(("127.0.0.1", port), timeout=5)
        except OSError:
            return
        with upstream:
            upstream.settimeout(None)
            outgoing = threading.Thread(target=forward, args=(client, upstream), daemon=True)
            outgoing.start()
            forward(upstream, client)
            outgoing.join()


def main() -> int:
    """Serve fino a SIGTERM o SIGINT; un mancato avvio restituisce codice 1."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--public-port", type=int, required=True)
    parser.add_argument("--start-timeout", type=float, required=True)
    args = parser.parse_args()
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    process = None
    logger = None
    try:
        process = subprocess.Popen(["bash", "start.sh"], cwd=args.site,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, errors="replace", start_new_session=True)
        logger = threading.Thread(target=print_log, args=(process,), daemon=True)
        logger.start()
        reason = wait_for_site(process, args.port, args.start_timeout, stopped)
        if reason is not None:
            print(reason, flush=True)
            return 1
        if stopped.is_set():
            return 0
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("0.0.0.0", args.public_port))
            listener.listen()
            listener.settimeout(0.2)
            while not stopped.is_set():
                try:
                    client, _ = listener.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=relay, args=(client, args.port), daemon=True).start()
        return 0
    except OSError as error:
        print(f"avvio o inoltro non riuscito: {error}", flush=True)
        return 1
    finally:
        if process is not None:
            stop_process(process)
        if logger is not None:
            logger.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
