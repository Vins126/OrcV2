"""Suite di test del progetto.

Nessun test tocca la rete e nessuno costa denaro: provider, executor e registro
sono sostituiti da finti costruiti nel test stesso. E' l'iniezione delle
dipendenze a renderlo possibile, ed e' una proprieta' necessaria — non comoda —
in un progetto dove ogni chiamata vera consuma budget della tesi.

Il package esiste perche' i test importino i moduli dalla radice del progetto
senza manipolare `sys.path`.
"""
