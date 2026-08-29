#!/usr/bin/env bash
set -Eeuo pipefail

qgc_host="${QGC_HOST:-host.docker.internal}"
qgc_port="${QGC_PORT:-14550}"
failures=0

if [[ ! "${qgc_port}" =~ ^[0-9]+$ ]] ||
  (( qgc_port < 1 || qgc_port > 65535 )); then
  echo "Invalid QGC_PORT '${qgc_port}'; expected an integer from 1 through 65535." >&2
  exit 2
fi

echo "QGroundControl connectivity diagnostic"
echo "Configured PX4 destination: ${qgc_host}:${qgc_port}/udp"
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "FAIL: Docker CLI was not found." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "FAIL: Docker's Linux daemon is unavailable." >&2
  exit 1
fi

container_id="$({
  docker ps \
    --filter 'label=com.docker.compose.project=drn-stack' \
    --filter 'label=com.docker.compose.service=ros-viz' \
    --format '{{.ID}}'
} | awk 'NR == 1 { print; exit }')"
if [[ -z "${container_id}" ]]; then
  echo "FAIL: the drn-stack ros-viz container is not running." >&2
  echo "Start it with: bash ./scripts/run-sim.sh" >&2
  exit 1
fi
echo "PASS: drn-stack ros-viz container is running (${container_id})."

network_details="$(docker inspect --format \
  '{{range $name, $settings := .NetworkSettings.Networks}}{{$name}} {{$settings.IPAddress}} {{$settings.Gateway}}{{end}}' \
  "${container_id}")"
read -r network_name container_ip gateway_ip <<<"${network_details}"
if [[ -z "${network_name}" || -z "${container_ip}" || -z "${gateway_ip}" ]]; then
  echo "FAIL: could not resolve the container network path." >&2
  exit 1
fi
network_subnet="$(docker network inspect --format \
  '{{(index .IPAM.Config 0).Subnet}}' "${network_name}")"
if [[ -z "${network_subnet}" ]]; then
  echo "FAIL: could not resolve the subnet for Docker network ${network_name}." >&2
  exit 1
fi
echo "Docker path: ${container_ip} -> ${gateway_ip} on ${network_name} (${network_subnet})"

if [[ "${qgc_host}" != "host.docker.internal" ]]; then
  echo
  echo "INFO: QGC_HOST is remote or custom, so local listener and host-firewall checks are skipped."
  echo "Verify UDP ${qgc_port} on '${qgc_host}' from that host."
  exit 0
fi

if command -v ss >/dev/null 2>&1; then
  socket_table="$(ss -H -lun "sport = :${qgc_port}" 2>/dev/null || true)"
  if [[ -z "${socket_table}" ]]; then
    echo "FAIL: no host process is listening on UDP ${qgc_port}." >&2
    echo "Start QGroundControl and keep UDP autoconnect enabled on port ${qgc_port}." >&2
    failures=1
  elif awk -v port="${qgc_port}" -v gateway="${gateway_ip}" '
    $4 == "0.0.0.0:" port || $4 == "*:" port ||
      $4 == "[::]:" port || $4 == gateway ":" port { found = 1 }
    END { exit !found }
  ' <<<"${socket_table}"; then
    echo "PASS: a host process is listening on UDP ${qgc_port}."
  else
    echo "FAIL: UDP ${qgc_port} is listening only on an address Docker cannot reach." >&2
    echo "Enable QGroundControl UDP autoconnect so it binds a wildcard or ${gateway_ip}." >&2
    failures=1
  fi
else
  echo "WARN: 'ss' is unavailable; the QGroundControl UDP listener was not checked."
fi

ufw_active=0
if command -v systemctl >/dev/null 2>&1 &&
  systemctl is-active --quiet ufw 2>/dev/null; then
  ufw_active=1
  echo "INFO: UFW is active on this host."
fi

recent_blocks=""
if command -v journalctl >/dev/null 2>&1; then
  recent_blocks="$(journalctl -k --since '-10 minutes' --no-pager 2>/dev/null |
    awk -v source="SRC=${container_ip}" -v port="DPT=${qgc_port}" \
      'index($0, "[UFW BLOCK]") && index($0, source) && index($0, port)' || true)"
fi
if [[ -n "${recent_blocks}" ]]; then
  echo "FAIL: recent kernel logs show UFW blocking this MAVLink stream:" >&2
  printf '%s\n' "${recent_blocks}" | tail -n 3 >&2
  failures=1
elif (( ufw_active )); then
  echo "WARN: no readable recent UFW block was found; restricted journal access may hide it."
fi

if (( ufw_active )); then
  echo
  echo "If UFW is blocking QGC, review and explicitly apply this rule:"
  printf "  sudo ufw allow in from %q to %q port %q proto udp comment 'DRN QGC from Docker'\n" \
    "${network_subnet}" "${gateway_ip}" "${qgc_port}"
  echo "The command is not executed by this script. It trusts containers on the current"
  echo "DRN Docker subnet only; rerun this diagnostic if Docker assigns a new subnet."
fi

echo
if (( failures )); then
  echo "QGroundControl connectivity checks found a problem." >&2
  exit 1
fi
echo "No locally observable QGroundControl connectivity problem was found."
