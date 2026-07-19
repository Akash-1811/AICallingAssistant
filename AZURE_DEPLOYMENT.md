# Deploying to Microsoft Azure

A step-by-step guide to get this project running in production on Azure.

---

## 1. Which Azure approach, and why

There are several ways to run containers on Azure (Container Apps, AKS, App Service,
a plain VM). This project is deliberately **single-instance by design** — the
[Dockerfile](Dockerfile) says so directly: the embedding + reranker models live in
one process's memory, and WebSocket call sessions are held in that same process. It
does not horizontally scale without extra work (sticky sessions, a shared model
server) — that's Phase 4+ territory in [IMPROVEMENTS_ROADMAP.md](IMPROVEMENTS_ROADMAP.md),
not where you are today.

**Recommendation: one Azure Virtual Machine running Docker, using the
`docker-compose.prod.yml` already in this repo.** This is the option that matches
the app's actual current architecture, is the cheapest, is the fastest to stand up,
and is a near-exact copy of what you have already tested locally. Container Apps /
AKS add real value once you need to scale beyond one instance — not before.

This guide also sets up **Caddy**, a reverse proxy that gets you free, auto-renewing
HTTPS with zero manual certificate work — already wired into
[docker-compose.prod.yml](docker-compose.prod.yml) and [Caddyfile](Caddyfile).

### What you're deploying

| Piece | Where it runs | Notes |
|---|---|---|
| Caddy (reverse proxy + TLS) | Container, ports 80/443 | The only thing exposed to the internet |
| Frontend (React, built) | Container, internal only | Static files served by nginx |
| Backend (FastAPI) | Container, internal only | The app itself |
| Postgres, Redis, Qdrant | Containers, internal only | Call data, cache, knowledge base |

Everything runs on **one VM**. Total idle RAM usage is roughly 3–4 GB (embedding +
reranker models are the biggest consumers); size the VM accordingly (§2).

---

## 2. Prerequisites

- An Azure subscription (you already have one, with credit)
- This project pushed to a GitHub repo (already done —
  `github.com/Akash-1811/AICallingAssistant`, private)
- A domain name you can point at the VM (optional but recommended — without one
  you'll run over plain HTTP using the VM's IP address)
- Your API keys ready: `GEMINI_API_KEY` (or `OPENAI_API_KEY`), `DEEPGRAM_API_KEY`
- **5 minutes before you start:** rotate any key that has ever been exposed in a
  screenshot, chat log, or committed file. Assume nothing is safe if it was ever
  visible outside your `.env`.

---

## 3. Create the Virtual Machine

You're already in the Azure Portal, so these steps use the portal UI directly.

1. Click **Create a resource** → **Virtual Machine**.
2. **Basics tab:**
   - **Resource group:** Create new → `ai-calling-assistant-rg`
   - **Virtual machine name:** `ai-calling-assistant-vm`
   - **Region:** pick one close to your users (e.g. `Central India` if your reps are
     in India — lower latency to Deepgram/Gemini's nearest edge and to your reps)
   - **Image:** `Ubuntu Server 22.04 LTS - x64 Gen2`
   - **Size:** click "See all sizes" and pick **Standard_B4ms** (4 vCPU, 16 GB RAM,
     burstable/cost-efficient) as the practical minimum. Don't go below 8 GB RAM —
     the embedding + reranker models alone need real headroom alongside Postgres,
     Redis, and Qdrant on the same box.
   - **Authentication type:** SSH public key (generate a new key pair if you don't
     have one; download the private key and keep it safe — you cannot recover it later)
   - **Inbound port rules:** Allow selected ports → check **SSH (22)**, **HTTP (80)**,
     **HTTPS (443)**
3. **Disks tab:**
   - OS disk size: bump to at least **64 GB** Premium SSD (default 30 GB is tight
     once you add Docker images, the HF model cache, and a growing Postgres/Qdrant
     dataset of real call data)
4. **Networking tab:** leave defaults (a new virtual network + subnet is fine); the
   NSG inbound rules from step 2 already restrict the VM to 22/80/443.
5. Click **Review + create** → **Create**.

Once it's provisioned, open the VM's overview page and copy its **Public IP address**
— you'll need it below.

### Lock down SSH (recommended, do this now)

By default port 22 is open to the whole internet. Go to the VM → **Networking** →
the associated Network Security Group → edit the SSH inbound rule → change **Source**
from "Any" to **your own IP address**. You can always add other IPs later.

### (Optional) Point your domain at the VM

In your domain registrar's DNS settings, add an **A record**:
```
Type: A
Name: app          (or @ for the root domain)
Value: <the VM's public IP>
TTL: 300
```
DNS propagation can take a few minutes to a few hours. You can proceed with the
rest of this guide immediately — Caddy will pick up the domain whenever DNS resolves.

---

## 4. Connect and install Docker

SSH into the VM (replace with your key path and the VM's IP):

```bash
ssh -i /"C:\Users\Akash Yadav\Downloads\AICallingAssistant_key.pem" azureuser@<40.81.243.12>
```

Install Docker Engine + the Compose plugin (official Docker script — the same
engine used everywhere, not a cut-down distro package):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Log out and back in (so your user picks up the `docker` group), then confirm:

```bash
exit
ssh -i /path/to/your-key.pem azureuser@<VM_PUBLIC_IP>
docker --version
docker compose version
```

---

## 5. Get the code onto the VM

```bash
git clone https://github.com/Akash-1811/AICallingAssistant.git
cd AICallingAssistant
```

Since the repo is **private**, `git clone` over HTTPS will prompt for credentials.
Use a GitHub Personal Access Token as the password (Settings → Developer settings →
Personal access tokens → generate one with `repo` scope), or install the GitHub CLI
(`sudo apt install gh && gh auth login && gh repo clone Akash-1811/AICallingAssistant`).

---

## 6. Create the production `.env`

This file never gets committed — you create it directly on the VM.

```bash
nano .env
```

Paste this, filling in your real values:

```ini
# --- LLM ---
GEMINI_API_KEY=your-gemini-key-here
# OPENAI_API_KEY=your-openai-key-here     # only if LLM_PROVIDER=openai
GEMINI_MODEL=gemini-3.5-flash
REALTIME_GEMINI_MODEL=gemini-flash-lite-latest

# --- Speech-to-text ---
DEEPGRAM_API_KEY=your-deepgram-key-here

# --- Auth ---
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=paste-a-freshly-generated-64-char-hex-string-here

# --- Database ---
# Any strong random string — this becomes the Postgres password on first boot
POSTGRES_PASSWORD=paste-a-strong-random-password-here

# --- Domain / TLS ---
# Your real domain if you set up DNS in step 3 (Caddy will do automatic HTTPS).
# If you're using the VM public IP (smoke test), include the scheme so Caddy does
# NOT attempt HTTPS redirects:
#   DOMAIN=http://<VM_PUBLIC_IP>
DOMAIN=app.yourdomain.com
ACME_EMAIL=you@yourdomain.com

# --- CORS ---
# Must match exactly how the site will be accessed (with https:// if using a domain)
CORS_ORIGINS=https://app.yourdomain.com
```

Generate the two random values before pasting them in:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"   # -> JWT_SECRET
openssl rand -base64 24                                     # -> POSTGRES_PASSWORD
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

> **Why `ENVIRONMENT=production` isn't in this file:** it's already set inside
> `docker-compose.prod.yml` itself, which is what makes the app enforce a strong
> `JWT_SECRET` and reject wildcard CORS at boot — see `validate_production_settings()`
> in [app/core/config.py](app/core/config.py). If you paste a weak secret above, the
> backend will refuse to start and tell you exactly why in its logs.

---

## 7. Build and start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes roughly 7–8 minutes (downloading base images + Python
dependencies); subsequent builds are much faster due to layer/pip caching.

Watch it come up:

```bash
docker compose -f docker-compose.prod.yml ps
```

Wait until `backend` shows `healthy` (it needs Qdrant, Redis, and Postgres healthy
first, then loads the embedding/reranker models — allow ~1–2 minutes total).

---

## 8. Verify it's live

```bash
curl -s http://localhost/health
```
should return `{"status":"ok"}`. Then from your own browser, visit:
- `http://<VM_PUBLIC_IP>` (or `https://app.yourdomain.com` if DNS has propagated)

If you used a real domain, Caddy will have automatically requested a Let's Encrypt
certificate on first request — the very first page load may take a couple of extra
seconds while that happens, after which it's cached and instant.

---

## 9. Load your knowledge base

Sign up for an account in the app, then go to **Knowledge Base** and upload your
real pricing sheets / FAQs / brochures (PDF, DOCX, TXT, CSV, or JSON) — this is the
live path real customers should use.

If you want to see the app working with sample data first (a demo real-estate
dataset), run:

```bash
docker compose -f docker-compose.prod.yml --profile seed run --rm seed
```

This is safe to run at any time — it never deletes anything you've uploaded through
the Knowledge Base page (see [app/scripts/seed_demo_data.py](app/scripts/seed_demo_data.py)).

---

## 10. Day-two operations

**View logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

**Deploy an update after pushing new code to GitHub:**
```bash
cd AICallingAssistant
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

**Restart everything:**
```bash
docker compose -f docker-compose.prod.yml restart
```

**Back up your data** (do this regularly — nothing here does it automatically yet;
see Phase 4 in [IMPROVEMENTS_ROADMAP.md](IMPROVEMENTS_ROADMAP.md)):
```bash
docker exec ai_postgres pg_dump -U aicall aicall > backup-$(date +%F).sql
```
Copy that file off the VM (e.g. `scp` it to your own machine or to Azure Blob Storage)
— a backup that only exists on the VM you're backing up isn't a backup.

**Check disk usage** (Docker images and volumes accumulate over time):
```bash
docker system df
```

---

## 11. Cost expectations

- **Standard_B4ms VM:** roughly $120–140/month pay-as-you-go in most regions (check
  the exact rate for your chosen region in the Azure Pricing Calculator) — burstable
  VMs are billed partly on CPU credit usage, so a lightly-loaded box costs less.
- **Disk (64 GB Premium SSD):** a few dollars/month.
- **Bandwidth:** negligible at this scale (audio never leaves the browser except as
  compressed PCM to your own server; outbound is small text to Deepgram/Gemini).
- Your visible Azure credit balance covers this comfortably for a good while — keep
  an eye on the **Cost Management** blade so you're not surprised near renewal.

---

## 12. What this guide deliberately does NOT cover

Being direct about the gaps, so you know what's still ahead (all tracked in
[IMPROVEMENTS_ROADMAP.md](IMPROVEMENTS_ROADMAP.md) / [EXECUTION_PLAN.md](EXECUTION_PLAN.md)):

- **Automated backups** — the `pg_dump` command above is manual; schedule it (a cron
  job on the VM, or Azure Automation) before you trust this with real customer data.
- **Zero-downtime deploys** — `up -d --build` briefly restarts the backend; fine for
  a low-traffic pilot, not yet built for a "never drop a live call" guarantee (that's
  Phase 3, session resilience, in the execution plan).
- **Horizontal scaling** — this VM serves one instance. If you outgrow it, the move
  is Azure Container Apps + Azure Database for PostgreSQL (managed) + Azure Cache for
  Redis (managed), with Qdrant either self-hosted with a persistent volume or moved to
  Qdrant Cloud. That's a deliberate later step, not a first-deployment concern.
- **Monitoring/alerting** — nothing pages you if the backend goes down. Azure Monitor
  can watch the VM; wiring real error tracking (Sentry) is Phase 5 in the roadmap.

For a first production deployment serving a real pilot, the setup in this guide is
solid and honest about its limits — which is exactly the point.
