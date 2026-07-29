#!/usr/bin/env bash
set -u

scripts_dir=$(cd "$(dirname "$0")" && pwd)

include_command_lines=false
if [[ "${1:-}" == "--include-command-lines" ]]; then
  include_command_lines=true
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--include-command-lines]\n' "$0" >&2
  exit 2
fi

section() {
  printf '\n[%s]\n' "$1"
}

run_if_present() {
  local command_name="$1"
  shift
  if command -v "${command_name}" >/dev/null 2>&1; then
    "$@" 2>&1 || true
  else
    printf '%s is not installed\n' "${command_name}"
  fi
}

section "timestamp"
date --iso-8601=seconds 2>/dev/null || date

section "operating-system"
if [[ -r /etc/os-release ]]; then
  sed -n '1,80p' /etc/os-release
fi
uname -a

section "cpu"
run_if_present lscpu lscpu
printf 'logical_cpus='
getconf _NPROCESSORS_ONLN 2>/dev/null || true

section "memory-and-swap"
run_if_present free free -h
if [[ -r /proc/swaps ]]; then
  sed -n '1,40p' /proc/swaps
fi

section "filesystems"
df -hT 2>&1 || true
df -hi 2>&1 || true

section "load-and-cpu-snapshot"
uptime 2>&1 || true
run_if_present vmstat vmstat 1 2

section "largest-memory-processes"
ps -eo pid,ppid,user,comm,%cpu,%mem,rss --sort=-rss 2>&1 | sed -n '1,21p'

section "possible-proxy-processes"
ps -eo pid,user,comm,%cpu,%mem,rss 2>&1 | grep -Eai 'xray|v2ray|sing-box|hysteria|tuic|trojan|shadowsocks|ss-server|clash|naive|brook' | grep -Ev 'grep -Ea' || true

if [[ "${include_command_lines}" == true ]]; then
  section "redacted-command-lines-explicitly-requested"
  printf 'WARNING: command-line redaction is best-effort and may miss secrets. Keep this output private.\n'
  ps -eo pid,user,args 2>&1 | awk -f "${scripts_dir}/redact-command-lines.awk"
fi

section "listening-ports"
run_if_present ss ss -lntup

section "local-addresses-and-routes"
run_if_present ip ip -brief address
run_if_present ip ip route

section "guest-firewall-read-only"
if command -v ufw >/dev/null 2>&1; then
  ufw status verbose 2>&1 || true
fi
if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --state 2>&1 || true
  firewall-cmd --list-all 2>&1 || true
fi
if command -v nft >/dev/null 2>&1; then
  nft list ruleset 2>&1 || true
fi

section "recent-oom-events"
if command -v journalctl >/dev/null 2>&1; then
  journalctl -k --since '7 days ago' --no-pager 2>&1 | grep -Eai 'out of memory|oom-killer|killed process' | tail -n 40 || true
fi

printf '\nCloud security groups, public IP, provider bandwidth/traffic limits, and player-region latency must be checked separately.\n'
