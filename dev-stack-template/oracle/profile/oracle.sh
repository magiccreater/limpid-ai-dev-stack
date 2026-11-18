#!/usr/bin/env bash
set -euo pipefail
profile=$(cd "$(dirname "$0")" && pwd)
state="$HOME/.local/state/god-oracle"
mkdir -p -m 700 "$state"
tf() {
  docker run --rm -u "$(id -u):$(id -g)" -e HOME="$HOME" \
    -v "$HOME/.oci:$HOME/.oci:ro" -v "$state:/infra" -w /infra \
    hashicorp/terraform:1.11.4 "$@"
}
session() {
  ssh -i "$state/ssh" -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile="$state/known_hosts" "$@"
}
case "${1:-help}" in
  auth)
    command -v oci >/dev/null || { echo "Install in WSL: uv tool install oci-cli --python 3.12"; exit 1; }
    if [[ ! -s "$HOME/.oci/config" ]]; then oci setup config; fi
    echo "Upload only the generated PUBLIC PEM to your OCI user's API Keys. Keep the private PEM in WSL."
    ;;
  up)
    [[ -s "$HOME/.oci/config" ]] || { echo "Run god oracle auth first."; exit 1; }
    cidr="${2:-}"
    if [[ -z "$cidr" ]]; then
      cidr="$(curl -4fsS --max-time 8 https://checkip.amazonaws.com)/32" || {
        echo "Pass your public IPv4 address explicitly: god oracle up YOUR_PUBLIC_IPV4/32"; exit 1; }
    fi
    tenancy=$(python3 -c 'import configparser,sys; c=configparser.ConfigParser(); c.read(sys.argv[1]); print(c["DEFAULT"]["tenancy"])' "$HOME/.oci/config")
    oci iam availability-domain list --compartment-id "${3:-$tenancy}" >/dev/null || {
      echo "Check the DEFAULT profile, tenancy, region and that the matching API public key was uploaded."; exit 1; }
    [[ -e "$state/ssh" ]] || ssh-keygen -q -t ed25519 -N '' -f "$state/ssh"
    cp "$profile/main.tf" "$state/main.tf"
    cp "$profile/terraform.lock.hcl" "$state/.terraform.lock.hcl"
    tf init -input=false
    tf plan -out=planned -var "compartment=${3:-$tenancy}" -var "ssh_cidr=$cidr" \
      -var "ssh_public_key=$(cat "$state/ssh.pub")" -var "ad_index=${GOD_AD_INDEX:-0}"
    read -r -p "Create/update these OCI resources in your account? Type apply: " answer
    [[ "$answer" == apply ]] || exit 0
    tf apply planned
    tf output -raw ip > "$state/ip"
    bash "$0" deploy
    ;;
  deploy)
    [[ -s "$state/ip" ]] || { echo "Run god oracle up first."; exit 1; }
    host="ubuntu@$(cat "$state/ip")"
    ready=0
    for ((i=0;i<40;i++)); do
      if session "$host" true 2>/dev/null; then ready=1; break; fi
      sleep 4
    done
    [[ "$ready" == 1 ]] || { echo "SSH unavailable. Check your source /32 and instance status, then run god oracle deploy."; exit 1; }
    tar -C "$profile" -cf - gateway.py install-vm.sh | session "$host" \
      'sudo mkdir -p /opt/god-inference && sudo tar -xf - -C /opt/god-inference && sudo bash /opt/god-inference/install-vm.sh'
    bash "$0" tunnel
    ;;
  tunnel)
    [[ -s "$state/ip" ]] || { echo "Run god oracle up first."; exit 1; }
    host="ubuntu@$(cat "$state/ip")"
    if ! session -S "$state/control" -O check "$host" >/dev/null 2>&1; then
      session -M -S "$state/control" -fNT -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 -L 127.0.0.1:18182:127.0.0.1:8182 "$host"
    fi
    echo "WSL tunnel ready. Run god doctor to check model readiness."
    ;;
  logs)
    [[ -s "$state/ip" ]] || { echo "Run god oracle up first."; exit 1; }
    session "ubuntu@$(cat "$state/ip")" 'sudo journalctl -u god-inference -u god-router -n 50 --no-pager'
    ;;
  *) echo "god oracle auth | up YOUR_PUBLIC_IPV4/32 [compartment_OCID] | deploy | tunnel | logs";;
esac
