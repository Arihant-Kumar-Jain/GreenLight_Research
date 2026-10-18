# Deploy GreenLight Research on Nebius

One CPU VM runs the app container plus Caddy (HTTPS for your domain). The models run on Token Factory.

| Piece | Nebius service |
|---|---|
| Nemotron Nano / Super / Ultra, Qwen3-Embedding-8B | **Token Factory** (`NEBIUS_API_KEY`) |
| App (FastAPI + built React UI, one container) | **Compute** CPU VM with a **static public IP** |
| Image | **Container Registry** |
| SQLite backups | **Object Storage** (`deploy/backup.sh`) |
| API keys (optional) | **SecretStash** |

**Why a VM and not a Serverless AI endpoint.** Each research run (~10 min) is an asyncio task inside the API process,
and the database is SQLite in WAL mode. Both need one long-lived process on a real disk. An endpoint's container disk
is wiped when it stops, a bucket mount can't do SQLite's random writes, and the docs show no way to put your own
domain on the endpoint's managed URL.

Commands are from docs.nebius.com (Container Registry quickstart, Compute "public IP addresses", Object Storage
"AWS CLI"), checked 2026-10-18. Re-check flags with `--help`.

## 0. Before you deploy

- **Token Factory catalog.** Verified live: Nemotron 3 Nano / Super / Ultra and Qwen3-Embedding-8B resolve on Token
  Factory and full research runs complete in 6-7 min. With the Nebius key in `.env`, open
  `http://localhost:8100/api/health` and check that `models` shows all four roles with no `models_error`.
- **Google OAuth client.** In Google Cloud console → Credentials → your Web client, add the Authorized JavaScript origins
  `https://<your-domain>`, `http://localhost`, `http://localhost:5180` and `http://localhost:8100`.

## 1. CLI

```bash
curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash
nebius profile create        # opens the browser to sign in, choose the project
```

## 2. Image → Container Registry

```bash
export REGION_ID=eu-north1   # your project's region
export REGISTRY_PATH=$(nebius registry create --name glr --format json | jq -r ".metadata.id" | cut -d- -f 2)
nebius registry configure-helper              # docker auth; run docker as your user, not root
export GLR_IMAGE=cr.$REGION_ID.nebius.cloud/$REGISTRY_PATH/glr:latest
docker build --platform linux/amd64 -t $GLR_IMAGE .
docker push $GLR_IMAGE
```

## 3. VM

Console: **Compute → Virtual machines → Create**. Use:
- Platform: non-GPU (`cpu-d3`, or `cpu-e2` in eu-north1). Preset: the smallest one with 2+ vCPUs and 8 GiB.
  List what your project has with
  [these steps](https://docs.nebius.com/compute/virtual-machines/list-platforms).
- Image: a plain Ubuntu 24.04 image (no CUDA needed). Boot disk: 30 GiB.
- Public IP: **Auto assign static IP**. A dynamic IP is released after an hour stopped, which breaks the DNS record.
- Your SSH key.

CLI equivalent for the network part: `--network-interfaces '[{"name":"eth0","ip_address":{},"public_ip_address":{"static":true},"subnet_id":"<subnet_ID>"}]'`.

The default security group allows all traffic. The compose file publishes only 80/443 (the app port is bound to
127.0.0.1). Optionally, add a security group that allows only 22, 80 and 443.

## 4. DNS (at your registrar)

Nebius DNS zones are private to a VPC, so public DNS stays with your registrar:

```
A    research.<your-domain>    <VM static IP>     (or @ for the bare domain)
```

## 5. Run on the VM

```bash
ssh <user>@<VM IP>
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER && exit   # log in again after this
curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash && nebius profile create && nebius registry configure-helper
git clone <repo> GreenLight_Research && cd GreenLight_Research
nano .env      # see below
docker compose pull app && docker compose --profile prod up -d
docker compose logs -f
```

Production `.env` (start from `.env.example`):

```bash
NEBIUS_API_KEY=...            # only this LLM key: no OPENROUTER_API_KEY, so every call goes to Token Factory
TAVILY_API_KEY=...
OPENALEX_API_KEY=... / OPENALEX_MAILTO=...    # strongly recommended (shared keyless budget is tiny)
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
GLR_ALLOWED_EMAILS=you@gmail.com,teammate@gmail.com   # invite-only; empty = any Google account
GLR_PUBLIC_BASE_URL=https://research.<your-domain>
GLR_CORS_ORIGINS=https://research.<your-domain>
GLR_DOMAIN=research.<your-domain>
GLR_IMAGE=cr.<region>.nebius.cloud/<registry>/glr:latest
GLR_MAX_USD_PER_DAY=5
GLR_MAX_RUNS_PER_DAY=20
GLR_TAVILY_BUDGET=300
```

Caddy gets the certificate on first request once DNS points at the VM. Update: build + push a new image, then
`docker compose pull app && docker compose --profile prod up -d`. **This kills runs in progress** (they show
"Interrupted by a server restart"). Deploy between runs.

## 6. Backups → Object Storage

```bash
# Console: Object Storage → create bucket glr-backups; IAM → service account + access key (AWS-compatible).
sudo apt install -y awscli
aws configure set aws_access_key_id <key_id>
aws configure set aws_secret_access_key <secret>
aws configure set region $REGION_ID
aws configure set endpoint_url https://storage.$REGION_ID.nebius.cloud
GLR_BACKUP_BUCKET=glr-backups deploy/backup.sh
crontab -e   # 0 3 * * * cd ~/GreenLight_Research && GLR_BACKUP_BUCKET=glr-backups deploy/backup.sh
```

## Known limits

- With `GLR_ALLOWED_EMAILS` empty, any Google account can sign in and spend up to the daily caps. Set the allowlist
  and the caps.
- One process, one VM. No horizontal scaling. That's fine for a demo.
- Runs can't be cancelled, and a restart drops runs in flight.
