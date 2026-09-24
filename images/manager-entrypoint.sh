#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /run/sshd
ssh-keygen -A
mkdir -p /etc/ssh/sshd_config.d
printf '%s\n' 'PubkeyAuthentication yes' 'PasswordAuthentication no' 'PermitEmptyPasswords no' 'PermitRootLogin no' 'AllowUsers condor' 'AuthorizedKeysFile /home/condor/.ssh/authorized_keys' 'X11Forwarding no' > /etc/ssh/sshd_config.d/condor-demo.conf
if [[ -n "${CONDOR_SSH_PUBLIC_KEY:-}" ]]; then
  install -d -m 0700 -o condor -g condor /home/condor/.ssh
  printf '%s\n' "$CONDOR_SSH_PUBLIC_KEY" > /home/condor/.ssh/authorized_keys
  chown condor:condor /home/condor/.ssh/authorized_keys
  chmod 0600 /home/condor/.ssh/authorized_keys
fi
chmod 0777 /out
/usr/sbin/sshd
exec /start.sh
