"""Esecutori di comandi shell, intercambiabili.

Il package espone il contratto `CommandExecutor` e due implementazioni che si
distinguono per *dove* eseguono: `DockerExecutor` in un container effimero e
isolato, `LocalExecutor` nel processo corrente.

Nota di design (tesi):
    La separazione non e' pedanteria: l'esecuzione locale serve allo sviluppo e
    ai test, quella in container e' l'unica accettabile quando i comandi li
    decide un modello. Sceglierne una e' una riga in `tools/__init__.py`, e
    questo rende l'isolamento una **variabile dichiarata** dell'esperimento
    invece di un dettaglio implicito.
"""
