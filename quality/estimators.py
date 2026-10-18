"""Gli stimatori: dato un esempio restituiscono la probabilita' che la soluzione sia corretta."""

import ast
import json
import re
import string
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from accounting.base import Accountant
from budget_guard import BudgetExceeded
from llm_contracts import ChatGateway, TurnOutcome
from quality.dataset import Example


@dataclass(frozen=True)
class Estimate:
    """Il giudizio di uno stimatore su un esempio.

    Attributes:
        probability: probabilita' che la soluzione sia corretta, in [0, 1]; `None`
            se non e' arrivata una risposta valida (l'errore sta in `error`).
        cost_usd: costo del giudizio (per il locale e l'euristica, zero).
        latency_s: durata del giudizio.
        input_tokens: token di input, se lo stimatore li riporta.
        error: perche' non c'e' una risposta valida, altrimenti `None`.
        raw: la risposta grezza, per ricontrollare a mano.
    """

    probability: float | None
    cost_usd: float = 0.0
    latency_s: float = 0.0
    input_tokens: int | None = None
    error: str | None = None
    raw: Any = None


class Estimator(Protocol):
    """Qualunque cosa sappia dare una probabilita' di correttezza a un esempio."""

    name: str

    def estimate(self, example: Example) -> Estimate:
        """Giudica un esempio. Non solleva per un errore del servizio: lo riporta in `Estimate.error`."""
        ...


def render_state(template: str, example: Example) -> str:
    """Il testo che lo stimatore legge: istruzioni dell'esercizio e codice, niente altro.

    Il modello di testo ha solo due segnaposto, `{instructions}` e `{solution}`:
    nessun identificativo, tipo di guasto o etichetta puo' arrivare allo stimatore.

    Raises:
        ValueError: se il modello ha segnaposto diversi da quei due.
    """
    nomi = {nome for _, nome, _, _ in string.Formatter().parse(template) if nome}
    sconosciuti = nomi - {"instructions", "solution"}
    if sconosciuti:
        raise ValueError(f"segnaposto non ammessi nel modello: {', '.join(sorted(sconosciuti))}")
    return template.format(instructions=example.instructions, solution=example.solution)


class HeuristicEstimator:
    """Il pavimento: un controllo banale senza modelli.

    Dice 0,05 se la soluzione e' evidentemente non fatta (contiene
    `NotImplementedError` o una funzione con il solo `pass`), altrimenti 0,5: non ha
    un'opinione. Sui mutanti, che sono tutti codice "fatto", vale quindi circa 0,5 per
    costruzione: e' il limite dichiarato di questo pavimento.
    """

    name = "euristica"

    def estimate(self, example: Example) -> Estimate:
        return Estimate(probability=0.05 if self._non_fatto(example.solution) else 0.5)

    @staticmethod
    def _non_fatto(codice: str) -> bool:
        try:
            albero = ast.parse(codice)
        except SyntaxError:
            return True
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Raise) and nodo.exc is not None:
                esc = nodo.exc.func if isinstance(nodo.exc, ast.Call) else nodo.exc
                if isinstance(esc, ast.Name) and esc.id == "NotImplementedError":
                    return True
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                corpo = [n for n in nodo.body
                         if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                                 and isinstance(n.value.value, str))]       # senza la docstring
                if all(isinstance(n, ast.Pass) or (isinstance(n, ast.Expr)
                       and isinstance(n.value, ast.Constant) and n.value.value is Ellipsis)
                       for n in corpo):
                    return True
        return False


class D1Estimator:
    """Un modello decisionale `d1` (ospitato da Liquid o locale con `llama-server`), domanda sì/no."""

    def __init__(self, name: str, *, url: str, state_template: str, question: str,
                 api_key: str | None = None, model: str | None = None,
                 criteria: tuple[str, str] | None = None, client: httpx.Client | None = None,
                 attempts: int = 3, sleep: Callable[[float], None] = time.sleep):
        """Args:
            name: nome dello stimatore nei risultati.
            url: l'indirizzo di `/systemone` (ospitato) o `/v1/systemone` (locale).
            state_template: modello del testo con `{instructions}` e `{solution}`.
            question: la domanda sì/no.
            api_key: la chiave, se serve (ospitato); non si stampa mai.
            model: il campo `model` della richiesta (`d1` per l'ospitato), se serve.
            criteria: (testo per `true`, testo per `false`) oppure `None`. Solo le chiavi
                `true` e `false` hanno effetto: `yes`/`no` vengono ignorate in silenzio.
            client: client HTTP, iniettato per i test.
            attempts: tentativi su 429 e 5xx.
            sleep: attesa fra i tentativi, iniettata per i test.
        """
        self.name = name
        self._url, self._template, self._question = url, state_template, question
        self._api_key, self._model, self._criteria = api_key, model, criteria
        self._client = client or httpx.Client(timeout=60)
        self._attempts, self._sleep = attempts, sleep

    def estimate(self, example: Example) -> Estimate:
        corpo: dict[str, Any] = {
            "state": render_state(self._template, example),
            "questions": {"corretta": {"type": "noul", "instructions": self._question}},
        }
        if self._criteria is not None:
            corpo["questions"]["corretta"]["criteria"] = {
                "true": self._criteria[0], "false": self._criteria[1]}
        if self._model:
            corpo["model"] = self._model
        intestazioni = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        inizio = time.perf_counter()
        ultimo = "nessun tentativo"
        for tentativo in range(1, self._attempts + 1):
            try:
                risposta = self._client.post(self._url, json=corpo, headers=intestazioni)
            except httpx.HTTPError as errore:
                ultimo = type(errore).__name__
            else:
                if risposta.status_code == 200:
                    return self._leggi(risposta, time.perf_counter() - inizio)
                ultimo = f"HTTP {risposta.status_code}"
                if risposta.status_code != 429 and risposta.status_code < 500:
                    break                      # un errore di richiesta non migliora ritentando
            if tentativo < self._attempts:
                self._sleep(0.5 * tentativo)
        return Estimate(probability=None, latency_s=time.perf_counter() - inizio, error=ultimo)

    @staticmethod
    def _leggi(risposta: httpx.Response, durata: float) -> Estimate:
        try:
            dati = risposta.json()
            risposta_noul = dati["answers"]["corretta"]
            p = risposta_noul["noul"]
        except (ValueError, KeyError, TypeError):
            return Estimate(probability=None, latency_s=durata, error="risposta senza probabilita'")
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0:
            return Estimate(probability=None, latency_s=durata, error=f"probabilita' non valida: {p!r}")
        uso = dati.get("usage") or {}
        costo = uso.get("cost")
        return Estimate(probability=float(p), latency_s=durata, raw=risposta_noul,
                        cost_usd=float(costo) if isinstance(costo, (int, float)) else 0.0,
                        input_tokens=uso.get("input_tokens"))


class FrontierJudge:
    """Un modello forte a cui si chiede una probabilita' da 0 a 100.

    Passa dal gateway del progetto: retry, conteggio dei costi e tetto di budget
    sono quelli di sempre. Ogni thread ha il suo gateway e il suo contabile, cosi' il
    costo di un giudizio si legge senza mescolarsi con quello degli altri.
    """

    def __init__(self, name: str, *, make_gateway: Callable[[], tuple[ChatGateway, Accountant]],
                 system_prompt: str, user_template: str):
        """Args:
            name: nome dello stimatore nei risultati.
            make_gateway: costruisce un gateway e il suo contabile; si chiama una volta per thread.
            system_prompt: istruzioni di sistema del giudice.
            user_template: modello del messaggio con `{instructions}` e `{solution}`.
        """
        self.name = name
        self._make_gateway = make_gateway
        self._system, self._template = system_prompt, user_template
        self._sessione = threading.local()

    def estimate(self, example: Example) -> Estimate:
        """Giudica un esempio.

        Raises:
            BudgetExceeded: il tetto di spesa del gateway e' raggiunto; non e' un errore
                del giudizio ma un ordine di fermarsi, e arriva a chi governa l'esecuzione.
        """
        if not hasattr(self._sessione, "gateway"):
            self._sessione.gateway, self._sessione.contabile = self._make_gateway()
        gateway, contabile = self._sessione.gateway, self._sessione.contabile
        messaggi = [{"role": "system", "content": self._system},
                    {"role": "user", "content": render_state(self._template, example)}]
        prima = contabile.total_cost
        inizio = time.perf_counter()
        try:
            turno = gateway.complete(messaggi, [])
        except BudgetExceeded:
            raise
        except Exception as errore:   # un giudizio mancato non ferma l'esecuzione
            # `LLM irraggiungibile` da solo non dice se e' un 402, un 429 o un guasto di rete:
            # si riportano tipo e codice della causa, mai il suo testo (e' del fornitore).
            causa = errore.__cause__
            if getattr(causa, "status_code", None) == 402:
                # Senza credito ogni richiesta fallisce: e' un ordine di fermarsi, come il tetto di spesa.
                raise BudgetExceeded("credito del fornitore esaurito (HTTP 402)") from errore
            dettaglio = ""
            if causa is not None:
                dettaglio = f" <- {type(causa).__name__}"
                codice = getattr(causa, "status_code", None)
                if isinstance(codice, int):
                    dettaglio += f" HTTP {codice}"
            return Estimate(probability=None, latency_s=time.perf_counter() - inizio,
                            cost_usd=contabile.total_cost - prima,
                            error=f"{type(errore).__name__}: {errore}{dettaglio}"[:200])
        durata, costo = time.perf_counter() - inizio, contabile.total_cost - prima
        if turno.outcome is not TurnOutcome.COMPLETE:
            return Estimate(None, costo, durata, error=f"esito {turno.outcome.name}", raw=turno.content)
        p = self._probabilita(turno.content)
        if p is None:
            return Estimate(None, costo, durata, error="risposta senza probabilita' valida", raw=turno.content)
        return Estimate(probability=p, cost_usd=costo, latency_s=durata, raw=turno.content)

    @staticmethod
    def _probabilita(testo: str | None) -> float | None:
        """La probabilita' (0-100) dentro un oggetto JSON `{"probability": N}`, o `None`."""
        for candidato in re.findall(r"\{[^{}]*\}", testo or ""):
            try:
                valore = json.loads(candidato).get("probability")
            except (ValueError, AttributeError):
                continue
            if isinstance(valore, (int, float)) and not isinstance(valore, bool) and 0 <= valore <= 100:
                return valore / 100
        return None
