#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT"

command -v docker >/dev/null
command -v ssh-keygen >/dev/null
[[ -S /var/run/docker.sock ]]

remove_workers() {
  while read -r container; do
    if [[ -n "$container" ]]; then
      docker rm -f "$container" >/dev/null
    fi
  done < <(docker ps -aq --filter label=htcondor.autoscaler=true)
}

rm -rf .demo
mkdir -p .demo/ssh
ssh-keygen -q -t ed25519 -N '' -f .demo/ssh/id_ed25519
export CONDOR_SSH_PUBLIC_KEY
CONDOR_SSH_PUBLIC_KEY=$(<.demo/ssh/id_ed25519.pub)
export DOCKER_UID
DOCKER_UID=$(id -u)
export DOCKER_GID
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)

cleanup() {
  remove_workers
  docker compose down --volumes --remove-orphans
  rm -rf .demo
}
remove_workers
docker compose down --volumes --remove-orphans
trap cleanup EXIT

docker compose build condor-manager condor-autoscaler condor-worker
docker compose up -d condor-manager
for _ in $(seq 1 30); do
  if docker compose exec -T condor-manager test -s /etc/ssh/ssh_host_ed25519_key.pub; then
    break
  fi
  sleep 2
done
docker compose exec -T condor-manager ssh-keyscan condor-manager > .demo/ssh/known_hosts
chmod 0644 .demo/ssh/known_hosts
docker compose up -d condor-autoscaler

docker compose exec -T -u demo condor-manager sh -c 'cd /workload_demo && condor_submit -name condor-manager@condor-manager job.sub'

completed=0
for _ in $(seq 1 60); do
  completed=1
  for job_id in 1 2 3 4; do
    if ! docker compose exec -T condor-manager test -s "/out/pi-${job_id}.json"; then
      completed=0
    fi
  done
  if [[ "$completed" == 1 ]]; then
    break
  fi
  sleep 5
done

if [[ "$completed" != 1 ]]; then
  docker compose ps
  docker compose logs --no-color condor-manager condor-autoscaler
  exit 1
fi

docker compose exec -T condor-manager ls -l /out
printf '%s\n' 'HTCondor demo completed successfully.'
