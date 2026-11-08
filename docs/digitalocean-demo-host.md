# Tribal DigitalOcean demo host

Prepared and verified on 2026-11-08 for `https://github.com/Dlang-max/Tribal`, branch
`feat/kubernetes-project-mcp-demo`. The app and React frontend now run over HTTPS with bearer-protected MCP;
server model login and live curator read/write acceptance are verified. See [hosted deployment](hosted-tribal.md)
for current status and the latest verified KB import.

## Host and access

| Resource | Verified value |
| --- | --- |
| Droplet | `tribal-demo`, ID `617079315` |
| Public IPv4 | `157.245.218.183` |
| Private IPv4 | `10.108.0.2` |
| Region and size | NYC3, `s-2vcpu-4gb` |
| Cost at creation | $0.03571/hour, capped at $24/month |
| OS | Ubuntu 24.04.5 LTS, image `252242095` |
| Capacity | 2 vCPU, 4 GiB advertised RAM, 80 GiB advertised disk |
| Observed resources | 3.8 GiB RAM, 77 GiB root filesystem, 2 GiB swap |
| SSH key | Existing key `60709868`, Codex Hackathon Key |
| SSH public-key fingerprint | `SHA256:oM66d8GN3cO24otUmeckvVY9mhI/Gp3+VZfoAVZjGVE` |
| Firewall | `d65fddbe-d655-40ba-bb24-9648ae854140`, `tribal-demo` |
| Monitoring | Enabled; paid backups and extra volumes disabled |

Connect using the existing SSH agent; agent forwarding is unnecessary:

```bash
ssh -o ForwardAgent=no root@157.245.218.183
```

The firewall attaches directly to the Droplet and through tag `tribal-demo`.
Inbound TCP 22 is restricted to the setup laptop's public address,
`172.100.2.173/32`; TCP 80/443 is allowed publicly. Outbound TCP/UDP/ICMP is
allowed. No IPv6 address was provisioned. If the laptop's public IP changes,
update the firewall's SSH source through the DigitalOcean control panel before
reconnecting. The provider console is the recovery path if SSH is unavailable.

SSH requires keys (`PasswordAuthentication no`,
`KbdInteractiveAuthentication no`, root login with keys only), configured in
`/etc/ssh/sshd_config.d/00-tribal-key-only.conf` and checked with `sshd -t`.

Docker Engine `29.9.3` and Compose `v5.7.0` were installed from the
[official Docker Ubuntu apt repository](https://docs.docker.com/engine/install/ubuntu/).
Docker and containerd are active and enabled at boot; `docker run --rm hello-world`
succeeded. `/etc/docker/daemon.json` selects the local log driver with a 10 MB
limit and three files. `/swapfile` is 2 GiB, mode 0600 and recorded in `/etc/fstab`;
`vm.swappiness=10` is configured in `/etc/sysctl.d/90-tribal-demo.conf`.

## Copied storage

The user explicitly requested copying the current local MySQL database and
SeaweedFS object store. Local services, credentials and data were preserved.
The source application still runs locally; this is a snapshot, not replication
or a change of the application's active database.

The destination configuration is under root-only `/opt/tribal/storage`:

- `compose.yaml`: private services and persistent named volumes.
- `.env`: fresh MySQL credentials; mode 0600.
- `s3.json`: fresh S3 credentials; mode 0600, owned by UID/GID 1000 because
  SeaweedFS drops privileges to that user. Parent directories remain root-only.
- `app.env`: storage connection settings for a future app on the same Docker
  network; mode 0600. No Codex login or embedding credentials were transferred.

Compose project `tribal-storage` runs `mysql` and `seaweed` on
`tribal-storage_default`. There are **no published container ports**. The app
must join that network to use `mysql:3306` and `http://seaweed:8333`.
The persistent volumes are `tribal-storage_mysql-data` and
`tribal-storage_seaweed-data`. Never use `docker compose down -v` on this stack.

The destination uses the exact source image digests:

- MySQL 8.4: `mysql@sha256:76f0358884cb92d9a086d24e5671c38048d3fef40f2588703d73eb55392d6b69`
- SeaweedFS 4.13: `chrislusf/seaweedfs@sha256:803e0f9f4a190319e39c2b226e15e75bf0ff78d00fe3e2806c38850ca81eb8a7`

SeaweedFS retains twenty 128 MB volume slots, matching local configuration.

### Snapshot method and verification

Snapshot captured at `2026-11-08T07:19:13.632931+00:00`.

A MySQL global read lock briefly blocked SQL publication while a transactional
`mysqldump`, ordered table-row fingerprints and the S3 export were captured.
The lock was released automatically. Source inspection confirmed Tribal writes
immutable versioned objects before committing their SQL references and has no
object-delete path. Curators could read throughout and wait briefly to publish.
All current and historical catalog references were checked against exported
object content hashes before restore.

The application database `tribal` was imported into an empty destination
application database; local MySQL system accounts were not copied. All objects
from the sole local bucket `tribal` were restored with their original keys,
content types, metadata and bytes. Destination storage credentials are new.

| Snapshot contents | Verified count |
| --- | ---: |
| `tribal_projects` | 1 |
| `tribal_notes` | 11 |
| `tribal_revisions` | 51 |
| `tribal_receipts` | 27 |
| `tribal_chunks` | 108 |
| S3 objects | 51 |
| Object bytes | 507855 |
| Current/history object references checked | 62 |

Every ordered SQL table's row hash and every restored object's SHA-256 matched
the captured snapshot, both immediately after restore and after restarting both
storage containers. Reference hashes matched all 62 current/history entries.
The snapshot includes derived chunks as stored; this does not independently
verify embedding-provider operation. Later local updates are outside this
snapshot and are not automatically copied to the droplet.

A private SQL dump, object export, manifest and compressed archive are retained at
`/opt/tribal/backups/local-storage-2026-11-08`. They contain project data and must
remain private. This is an on-host restore artifact, not an off-host backup
policy. Its manifest holds per-table row counts/hashes and per-object hashes.
`restore-verification.json` records the successful verification after restart.

## Operator commands

Run these over SSH:

```bash
cd /opt/tribal/storage
docker compose ps
docker compose logs --tail 50 mysql seaweed
docker compose restart
systemctl is-active docker containerd
systemctl is-enabled docker
ss -lntup
swapon --show
```

Avoid printing rendered Compose configuration or credential files into shared
logs. The initial external scan found SSH open, HTTP/HTTPS closed (no reverse
proxy yet), and all checked backend ports filtered: 3306, 7333, 8000, 8080,
8333, 8888, 9333, 18080, 18888, 19333 and 33060. Host listener inspection and
container port bindings confirmed no storage publication.

## Current application deployment

The app and React dashboard run at https://tribal-ub-hacking-2026.duckdns.org/.
MCP is at `/mcp` and requires a bearer token. The dashboard and read APIs are
public by explicit user choice. Caddy provides trusted HTTPS, persists certificates
and blocks private curator paths. The app publishes no host port. Operator
configuration and complete acceptance evidence are in [hosted-tribal.md](hosted-tribal.md).

The latest user-requested local KB port supersedes the initial snapshot above:
12 notes, 57 revisions, 32 receipts, 119 chunks and 57 objects, all row/object
hashes verified. The before-port backup and receipt are at
`/opt/tribal/backups/before-local-kb-port-20261108T075102Z`.
The saved local Codex `tribal-project` definition now targets the remote endpoint
with bearer authentication. Current sessions need reconnect/restart to load it.

Server Codex authentication is complete through a fresh device sign-in. Real
hosted retrieval, publication, readback, identical-ID replay and persistence
through app restart succeeded. No model/embedding credentials were copied from
the laptop; embeddings remain optional and unverified.
