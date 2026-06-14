# Ollama Cloudflare Tunnel (persistent URL)

Run this once on your local machine. The URL never changes, even after restarts.

## 1. Install cloudflared
Windows:  winget install Cloudflare.cloudflared
Mac:      brew install cloudflare/cloudflare/cloudflared

## 2. Log in (free account at cloudflare.com)
cloudflared tunnel login

## 3. Create a named tunnel
cloudflared tunnel create ollama-local

## 4. Route a subdomain to it
# Replace YOUR_ZONE with your Cloudflare domain (e.g. yourdomain.com)
# Or skip this and use the free *.cfargotunnel.com hostname below instead.
cloudflared tunnel route dns ollama-local ollama.YOUR_ZONE

## 5. Run the tunnel (points at local Ollama port)
cloudflared tunnel run --url http://localhost:11434 ollama-local

## Alternatively — no domain needed, quick tunnel (URL changes on restart)
cloudflared tunnel --url http://localhost:11434

## After starting, copy the URL and set it in Render dashboard:
## OLLAMA_BASE_URL = https://ollama.YOUR_ZONE  (or the cfargotunnel.com URL)
