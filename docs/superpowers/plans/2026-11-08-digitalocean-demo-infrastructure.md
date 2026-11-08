# DigitalOcean Demo Infrastructure Implementation Plan

> Execute the approved infrastructure setup directly in this session. No application implementation, new tests, or repository integration is required.

**Goal:** Prepare one DigitalOcean VM for the current single-project Tribal demo.

**Architecture:** Ubuntu 24.04 in NYC3, size `s-2vcpu-4gb` (2 vCPU, 4 GiB RAM, 80 GiB disk), Docker Engine and Compose, persistent local disk, SSH key authentication and a cloud firewall. MySQL, SeaweedFS and the app will run privately on the VM when deployed.

**Tech Stack:** DigitalOcean Droplets, Ubuntu, OpenSSH, Docker Compose.

**Spec:** The user explicitly approved the hosting design in this conversation: `tribal-demo`, NYC3, 2 CPUs / 4 GB / 80 GB, $0.03571/hour capped at $24/month, SSH restricted to this machine's public IP, web ports 80/443 allowed. No paid backups, additional disks, managed databases or clusters are selected.

## Global Constraints

- Prepare the VM; public application access still needs HTTPS and server-side Codex authentication.
- Preserve all existing local source, data and credentials. Do not copy Codex authentication or embedding keys to the VM.
- Use the existing SSH-agent-backed public key; do not read or transfer its private key.
- Never publish database, SeaweedFS, raw application or internal curator ports.
- Do not write tests. Verify actual cloud state, SSH access, Docker execution and network exposure.

## Review Focus

- Failed provisioning must not be described as a working VM; record exact provider errors and created resources.
- Firewall tag and Droplet tag must match, and outbound DNS/HTTPS must remain available.
- SSH restriction must match the current public IPv4; document how to recover after an IP change.
- Docker can bypass host firewall rules; leave all backend ports unpublished and check listening ports.
- Prepared infrastructure does not establish deployed application, model authentication or live curation.

## Tasks

- [x] Register the existing public SSH key and create the tagged cloud firewall with SSH from the current public IP, public TCP 80/443, outbound TCP/UDP/ICMP.
- [x] Create exactly one tagged `tribal-demo` Ubuntu 24.04 Droplet with the approved size/region and free monitoring. Confirm resource ID, public IP and active status.
- [x] Connect using the SSH agent. Install Docker Engine/Compose from Docker's official Ubuntu repository; configure automatic startup, bounded Docker logs, a small swap file and a private `/opt/tribal` deployment directory. Do not deploy the unauthenticated app publicly.
- [x] Verify SSH, actual CPU/RAM/disk, active Docker, Compose, a disposable container run, firewall attachment/rules and closed backend ports. Record exact resource details and operator commands in `docs/digitalocean-demo-host.md`.
- [x] Submit verified outcomes and remaining deployment inputs to Tribal's KB agent. No commit or push requested.

## Initial Evidence

DigitalOcean API returned no Droplets, no SSH keys and no firewalls. Available size `s-2vcpu-4gb` costs $24/month / $0.03571/hour and includes NYC3. Distribution image `ubuntu-24-04-x64` is image ID `252242095`, available in NYC3. Existing local SSH key fingerprint is `SHA256:oM66d8GN3cO24otUmeckvVY9mhI/Gp3+VZfoAVZjGVE` and is loaded in the SSH agent. Actual repository branch is `feat/kubernetes-project-mcp-demo`; existing unrelated work is preserved.
