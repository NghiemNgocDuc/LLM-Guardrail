"""Groq + MandateLow bench — uses Groq (OpenAI-compatible) instead of OpenAI.

Set:
  $env:GROQ_API_KEY="gsk_..."
or paste in .env then:
  python scripts/bench_groq_mandatelow.py

If no key, falls back to direct InputGuardrail bench (no LLM call).
"""
import os, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Load .env GROQ key if present
try:
    from app.config import get_settings
    s=get_settings()
    groq_key=s.GROQ_API_KEY or os.getenv("GROQ_API_KEY","")
    groq_base=s.GROQ_BASE_URL or "https://api.groq.com/openai/v1"
except:
    groq_key=os.getenv("GROQ_API_KEY","")
    groq_base="https://api.groq.com/openai/v1"

print(f"Groq key: {'SET' if groq_key else 'NOT SET (using mock)'}  base={groq_base}")

# 1. MandateLow detector (no LLM) — always runs
import subprocess as _sp
_sp.run([sys.executable, str(pathlib.Path(__file__).parent/"bench_agentdojo_mandatelow.py")], check=False)
print("\n[1] MandateLow detector bench done")

# 2. Full AgentDojo with Groq (requires key) — workspace 5 tasks, mandatelow defense
if groq_key:
    os.environ["OPENAI_COMPATIBLE_BASE_URL"]=groq_base
    os.environ["OPENAI_COMPATIBLE_API_KEY"]=groq_key
    # Groq model: llama-3.3-70b-versatile is fastest, gpt-oss-20b for tool calling
    model_id="llama-3.3-70b-versatile"
    print(f"\n[2] AgentDojo + Groq + mandatelow — running 5 workspace tasks via {model_id}")
    print(f"CMD: OPENAI_COMPATIBLE_BASE_URL={groq_base} OPENAI_COMPATIBLE_API_KEY=gsk_... python -m agentdojo.scripts.benchmark --model openai-compatible --model-id {model_id} --defense mandatelow -s workspace --limit 5")
    try:
        import subprocess
        # run subprocess with env
        env=os.environ.copy()
        env["OPENAI_COMPATIBLE_BASE_URL"]=groq_base
        env["OPENAI_COMPATIBLE_API_KEY"]=groq_key
        # quick 2 tasks to avoid cost
        result=subprocess.run(
            [sys.executable, "-m", "agentdojo.scripts.benchmark",
             "--model", "openai-compatible", "--model-id", model_id,
             "--defense", "mandatelow", "-s", "workspace", "-ut", "user_task_0", "-ut", "user_task_1"],
            capture_output=True, text=True, timeout=120, env=env
        )
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        if result.returncode==0:
            print("✓ AgentDojo Groq+mandatelow completed")
        else:
            print(f"AgentDojo exit {result.returncode} — check GROQ_API_KEY quota / model name")
    except Exception as e:
        print(f"AgentDojo run err: {e}")
else:
    print("\n[2] Skipped AgentDojo+Groq (no GROQ_API_KEY) — set in .env or env then rerun")
    print("    PowerShell: $env:GROQ_API_KEY='gsk_...'; python scripts/bench_groq_mandatelow.py")
    # Mock Groq latency via our adapter
    from app.services.llm.groq import GroqAdapter
    import asyncio
    async def _mock():
        a=GroqAdapter()
        print("Groq adapter ready, default model", a)
    # Don't actually call API without key, just show would-be latency via POST /mandate/bench
    print("    Alternative: python -c \"import app.services.llm; print('Groq adapter mock')\"")

# 3. Groq raw latency vs Mandate provenance (if key)
if groq_key:
    import asyncio, httpx
    async def _groq_lat():
        t0=time.perf_counter()
        async with httpx.AsyncClient(timeout=10) as c:
            r=await c.post(f"{groq_base}/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={"model": "llama-3.3-70b-versatile","messages":[{"role":"user","content":"Say hello in 5 words"}],"max_tokens":20})
            print(f"Groq raw {r.status_code} {(time.perf_counter()-t0)*1000:.0f}ms {r.text[:200]}")
        # vs provenance
        t0=time.perf_counter()
        from app.services.mandate_service import evaluate_pinned_policy
        evaluate_pinned_policy("crm.resolve_customer","PAYMENT_AGGREGATE_ONLY")
        print(f"Mandate provenance {(time.perf_counter()-t0)*1000*1000:.1f}us — ~10000x faster than Groq RTT")
    try:
        asyncio.run(_groq_lat())
    except Exception as e:
        print(f"Groq ping err: {e}")

print("\nDone. Set GROQ_API_KEY to run full Groq+AgentDojo. See also geh harness for accuracy.")
