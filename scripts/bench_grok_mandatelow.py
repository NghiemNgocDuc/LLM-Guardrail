"""Grok (xAI / SpaceX) + MandateLow bench — replaces Groq.

Set:
  $env:XAI_API_KEY="xai-..."   # or GROK_API_KEY alias, from https://console.x.ai
  python scripts/bench_grok_mandatelow.py

If no key, falls back to in-process MandateLow bench (no API call).
Also supports OPENAI_COMPATIBLE for AgentDojo with Grok.

Grok API is OpenAI-compatible at https://api.x.ai/v1 (model grok-3, grok-4, grok-3-mini).
"""
import os, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from app.config import get_settings
    s=get_settings()
    xai_key=s.XAI_API_KEY or s.GROK_API_KEY or s.OPENAI_COMPATIBLE_API_KEY or os.getenv("XAI_API_KEY","") or os.getenv("GROK_API_KEY","")
    xai_base=s.XAI_BASE_URL or s.GROK_BASE_URL or "https://api.x.ai/v1"
except:
    xai_key=os.getenv("XAI_API_KEY","") or os.getenv("GROK_API_KEY","")
    xai_base="https://api.x.ai/v1"

print(f"Grok (xAI) key: {'SET' if xai_key else 'NOT SET (mock)'}  base={xai_base}")

# 1. In-process bench
import subprocess as _sp
_sp.run([sys.executable, str(pathlib.Path(__file__).parent/"bench_agentdojo_mandatelow.py")], check=False)
print("\n[1] MandateLow in-process done")

# 2. Full AgentDojo + Grok (requires xAI key)
if xai_key:
    os.environ["OPENAI_COMPATIBLE_BASE_URL"]=xai_base
    os.environ["OPENAI_COMPATIBLE_API_KEY"]=xai_key
    model_id="grok-3"
    print(f"\n[2] AgentDojo + Grok (xAI) + mandatelow — 2 workspace tasks via {model_id}")
    print(f"CMD: OPENAI_COMPATIBLE_BASE_URL={xai_base} OPENAI_COMPATIBLE_API_KEY=xai-... python -m agentdojo.scripts.benchmark --model OPENAI_COMPATIBLE --model-id {model_id} --defense mandatelow -s workspace -ut user_task_0 -ut user_task_1")
    import subprocess
    env=os.environ.copy()
    env["OPENAI_COMPATIBLE_BASE_URL"]=xai_base
    env["OPENAI_COMPATIBLE_API_KEY"]=xai_key
    result=subprocess.run(
        [sys.executable, "-m", "agentdojo.scripts.benchmark",
         "--model", "OPENAI_COMPATIBLE", "--model-id", model_id,
         "--defense", "mandatelow", "-s", "workspace", "-ut", "user_task_0", "-ut", "user_task_1"],
        capture_output=True, text=True, timeout=180, env=env
    )
    print(result.stdout[-3000:])
    print(result.stderr[-3000:])
    print("✓ done" if result.returncode==0 else f"exit {result.returncode} — check XAI_API_KEY / quota")
    # also test gateway path via xai adapter
    print("\n[3] Testing Grok adapter via gateway (POST /chat backend=grok)")
    try:
        import asyncio
        from app.services.llm import call_llm
        async def _call():
            t0=time.perf_counter()
            r=await call_llm(prompt="Say hello in 5 words", temperature=0.7, max_tokens=20, request_backend="grok", request_model="grok-3")
            print(f"Grok gate {(time.perf_counter()-t0)*1000:.0f}ms backend={r.backend} model={r.model} text={r.text[:100]}")
        asyncio.run(_call())
    except Exception as e:
        print(f"Grok gate err: {e}")
else:
    print("\n[2] Skipped Grok AgentDojo (no XAI_API_KEY/GROK_API_KEY) — set then rerun")
    print("    PowerShell: $env:XAI_API_KEY='xai-...'; python scripts/bench_grok_mandatelow.py")
    print("    Or .env: XAI_API_KEY=xai-...  (alias GROK_API_KEY)")
    print("    Get key: https://console.x.ai -> API Keys")
    print("    Also works: $env:GROK_API_KEY='xai-...'")

# 3. Ping Grok raw if key
if xai_key:
    import asyncio, httpx
    async def _ping():
        t0=time.perf_counter()
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.post(f"{xai_base}/chat/completions",
                headers={"Authorization": f"Bearer {xai_key}"},
                json={"model": "grok-3-mini","messages":[{"role":"user","content":"Say hello in 5 words"}],"max_tokens":20})
            print(f"Grok raw {r.status_code} {(time.perf_counter()-t0)*1000:.0f}ms {r.text[:300]}")
        # vs provenance
        t0=time.perf_counter()
        from app.services.mandate_service import evaluate_pinned_policy
        evaluate_pinned_policy("crm.resolve_customer","PAYMENT_AGGREGATE_ONLY")
        print(f"Mandate provenance {(time.perf_counter()-t0)*1000*1000:.1f}us")
    try:
        asyncio.run(_ping())
    except Exception as e:
        print(f"Grok ping err: {e}")

print("\nDone. For accuracy harness: geh run --dataset xstest --model mock  |  Grok: set XAI_API_KEY")
print("Docs: app/services/llm/xai.py (XAIAdapter), app/config.py XAI_* for Grok (SpaceX xAI)")
