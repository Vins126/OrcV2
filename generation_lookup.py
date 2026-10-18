"""Rilettura del costo di una generazione presso OpenRouter.

Nota di design (tesi):
    Un flusso interrotto non arriva al chunk con l'`usage`, ma il fornitore ha
    fatturato quanto generato fino a li'. Il ledger che registra solo risposte
    arrivate non vedrebbe quella spesa. `GET /generation?id=...` la restituisce,
    di solito dopo circa dieci secondi (misurato il 14 ott 2026 su `minimax/fp8`,
    campione singolo). La documentazione non dice se vale anche per generazioni
    interrotte: la misura dice di si'.

    Questo modulo non solleva mai: il costo di un tentativo fallito e' un
    miglioramento dei conti, non una condizione per proseguire.
"""

import time
from collections.abc import Callable
from math import isfinite
from typing import Any

import httpx

from llm_contracts import GenerationCost


class OpenRouterGenerationLookup:
    """Chiede a OpenRouter il costo di una generazione, ritentando se non e' ancora pronto."""

    def __init__(self, api_key: str, base_url: str, *, client: httpx.Client | None = None,
                 attempts: int = 4, interval_s: float = 5.0,
                 sleep: Callable[[float], None] = time.sleep):
        """Args:
            api_key: chiave di OpenRouter.
            base_url: indirizzo base dell'API (quello del client di chat).
            client: client HTTP; iniettato perche' i test non fanno rete.
            attempts: quante volte chiedere prima di arrendersi: i dati possono
                arrivare in ritardo.
            interval_s: attesa fra un tentativo e il successivo.
            sleep: funzione di attesa, iniettata perche' i test non dormono.
        """
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/generation"
        self._client = client or httpx.Client(timeout=30)
        self._attempts = attempts
        self._interval_s = interval_s
        self._sleep = sleep

    def __call__(self, generation_id: str) -> GenerationCost | None:
        """Restituisce il costo della generazione, o `None` se non si riesce a leggerlo.

        Si ritenta quando i dati potrebbero non essere ancora pronti (404), c'e'
        troppo traffico (429), il servizio ha un guasto (5xx) o la rete cade. Un
        errore di richiesta o di autenticazione non migliora ritentando.
        """
        for tentativo in range(1, self._attempts + 1):
            try:
                risposta = self._client.get(
                    self._url, params={"id": generation_id},
                    headers={"Authorization": f"Bearer {self._api_key}"})
            except httpx.HTTPError:
                risposta = None
            if risposta is not None:
                if risposta.status_code == 200:
                    return self._leggi(generation_id, risposta)
                if risposta.status_code not in (404, 429) and risposta.status_code < 500:
                    return None
            if tentativo < self._attempts:
                self._sleep(self._interval_s)
        return None

    @staticmethod
    def _leggi(generation_id: str, risposta: httpx.Response) -> GenerationCost | None:
        """Estrae il costo da una risposta 200, o `None` se non e' un costo valido."""
        try:
            dati = risposta.json().get("data")
        except (ValueError, AttributeError):
            return None
        if not isinstance(dati, dict):
            return None
        costo = dati.get("total_cost")
        if isinstance(costo, bool) or not isinstance(costo, (int, float)) \
                or not isfinite(costo) or costo < 0:
            return None

        def intero(valore: Any) -> int:
            return int(valore) if isinstance(valore, (int, float)) and not isinstance(valore, bool) else 0

        conteggi = [dati.get(k) for k in ("tokens_prompt", "tokens_completion", "native_tokens_reasoning")]
        if any(intero(c) < 0 for c in conteggi):
            # Un conteggio impossibile rende inaffidabile tutta la risposta: vale come
            # costo non leggibile (evento `interrupted_cost_unknown`), invece di un record
            # non valido che farebbe uscire un errore dal gateway.
            return None
        return GenerationCost(
            generation_id=generation_id, total_cost=float(costo),
            prompt_tokens=intero(dati.get("tokens_prompt")),
            completion_tokens=intero(dati.get("tokens_completion")),
            reasoning_tokens=intero(dati.get("native_tokens_reasoning")),
            finish_reason=dati.get("finish_reason"),
        )
