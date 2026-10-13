#!/bin/bash
# Entrypoint della sandbox.
#
# Con la rete `bridge` il container parte come amministratore (solo per questo
# script), applica un firewall che chiude la macchina e la rete locale, poi
# scende a utente 1000 senza alcun permesso prima di eseguire il comando. Da
# quel momento il comando non puo' piu' togliere le regole: servirebbe il
# permesso NET_ADMIN, che e' stato azzerato.
#
# Se una regola non si puo' applicare lo script si ferma (`set -e`) e il comando
# non parte: meglio nessuna esecuzione che una esecuzione senza firewall.
#
# Con la rete `none` (o senza ORC_FIREWALL) non c'e' nulla da fare: il container
# e' gia' utente 1000, senza rete, e il comando parte subito.

set -euo pipefail

if [ "${ORC_FIREWALL:-}" = "1" ]; then
    # iptables prende un blocco in /run, che in sola lettura non si puo' scrivere.
    export XTABLES_LOCKFILE=/tmp/xtables.lock

    # L'unica eccezione dentro le reti private: il DNS del container, porta 53.
    # Senza, nessun nome si risolverebbe e internet sarebbe irraggiungibile.
    for ns in $(awk '/^nameserver/ {print $2}' /etc/resolv.conf | grep -E '^[0-9.]+$' || true); do
        iptables -A OUTPUT -d "$ns" -p udp --dport 53 -j ACCEPT
        iptables -A OUTPUT -d "$ns" -p tcp --dport 53 -j ACCEPT
    done

    # Reti private, link-local (compreso l'indirizzo dei servizi cloud) e
    # CGNAT (Tailscale e simili): la macchina, la LAN, il router.
    for rete in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10; do
        iptables -A OUTPUT -d "$rete" -j REJECT
    done

    # IPv6 solo se il container ha davvero un indirizzo oltre al loopback.
    if grep -qv '^00000000000000000000000000000001' /proc/net/if_inet6 2>/dev/null; then
        for rete in fc00::/7 fe80::/10; do
            ip6tables -A OUTPUT -d "$rete" -j REJECT
        done
    fi
fi

if [ "$(id -u)" = "0" ] && [ -n "${ORC_RUN_AS:-}" ]; then
    exec setpriv --reuid="${ORC_RUN_AS%%:*}" --regid="${ORC_RUN_AS##*:}" \
        --clear-groups --bounding-set=-all --inh-caps=-all --no-new-privs "$@"
fi

exec "$@"
