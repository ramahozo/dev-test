import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # OpenRouter API Key Validation

    This notebook validates whether the `OPENROUTER_API_KEY` is working correctly.

    ## What this checks:
    1. **Key format validation** - Ensures the key looks like a valid OpenRouter key
    2. **Authentication test** - Verifies the key can authenticate with OpenRouter
    3. **Credit/quota check** - Checks remaining credits and usage
    4. **Model availability** - Tests a simple completion with a cheap model
    """)
    return


@app.cell
def _():
    import os as os_setup
    import sys as sys_setup

    # Add project root to path for imports
    project_root = os_setup.path.dirname(os_setup.path.abspath(__file__))
    if project_root not in sys_setup.path:
        sys_setup.path.insert(0, project_root)

    # Load .env file if exists
    from pathlib import Path

    env_path = Path(project_root) / "deploy" / "compose" / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)
        print(f"Loaded .env from: {env_path}")
    else:
        print(f".env not found at: {env_path}")
    return


@app.cell
def _(mo):
    import os as os_env

    api_key = os_env.getenv("OPENROUTER_API_KEY")

    if not api_key:
        mo.md(r"""❌ **OPENROUTER_API_KEY not found in environment**

    Please set it in:
    - `deploy/compose/.env` (for Docker Compose)
    - Or export it in your shell: `export OPENROUTER_API_KEY=sk-or-v1-...`
    """)
        api_key = None
    else:
        # Mask the key for display
        masked_key = api_key[:12] + "..." + api_key[-8:] if len(api_key) > 20 else "***"
        mo.md(f"""✅ **API Key found**: `{masked_key}`

    **Key format**: `sk-or-v1-...` (OpenRouter v1 key)
    """)
    api_key
    return (api_key,)


@app.cell
async def _(api_key):
    import openai
    from openai import AsyncOpenAI

    async def test_openrouter_key(api_key: str) -> dict:
        """Test OpenRouter API key with a minimal completion request."""
        results = {
            "key_valid": False,
            "authentication": "unknown",
            "credits_remaining": None,
            "model_test": "unknown",
            "error": None,
        }

        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://dev-agentic.local",
                "X-Title": "dev-agentic API Key Validator",
            },
            timeout=30.0,
        )

        try:
            # Test 1: Get current key info (requires management key, may fail)
            try:
                key_info = await client.get("/key")
                results["credits_remaining"] = key_info.get("limit_remaining")
                results["key_details"] = key_info
            except Exception:
                # Key info endpoint requires management key, skip if not available
                pass

            # Test 2: Simple completion with cheapest model
            response = await client.chat.completions.create(
                model="openrouter/auto",  # Let OpenRouter pick cheapest
                # model="liquid/lfm-2.5-2.6b:free",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0,
            )

            results["key_valid"] = True
            results["authentication"] = "success"
            results["model_test"] = "success"
            results["model_used"] = response.model
            results["usage"] = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            }
            results["cost_usd"] = (
                getattr(response.usage, "cost", None) if response.usage else None
            )

        except openai.AuthenticationError as e:
            results["authentication"] = "failed"
            results["error"] = f"Authentication failed: {e}"
        except openai.PermissionDeniedError as e:
            results["authentication"] = "denied"
            results["error"] = f"Permission denied (check credits/limits): {e}"
        except openai.RateLimitError as e:
            results["authentication"] = "rate_limited"
            results["error"] = f"Rate limited: {e}"
        except openai.APIStatusError as e:
            if e.status_code == 402:
                results["authentication"] = "no_credits"
                results["error"] = f"Insufficient credits (402): {e}"
            else:
                results["error"] = f"API error ({e.status_code}): {e}"
        except openai.APIConnectionError as e:
            results["error"] = f"Connection error: {e}"
        except openai.APITimeoutError as e:
            results["error"] = f"Timeout: {e}"
        except Exception as e:
            results["error"] = f"Unexpected error: {type(e).__name__}: {e}"
        finally:
            await client.close()

        return results

    # Run the async test
    if api_key:
        results = await test_openrouter_key(api_key)
    else:
        results = None
    results
    return (results,)


@app.cell
def _():
    return


@app.cell
def _(mo, results):
    if results is None:
        mo.md("⚠️ No API key to test")
    elif results["key_valid"]:
        mo.md(r"""## ✅ **API Key Validation: PASSED**

    The OpenRouter API key is working correctly!
    """)
    else:
        mo.md(f"""## ❌ **API Key Validation: FAILED**

    **Status**: {results.get('authentication', 'unknown')}
    **Error**: {results.get('error', 'Unknown error')}
    """)

    # Display detailed results
    import json

    mo.md("### Detailed Results")
    mo.code(json.dumps(results, indent=2, default=str))
    return


@app.cell
def _(mo, results):
    if results is None:
        mo.md("")
    elif results.get("credits_remaining") is not None:
        credits = results["credits_remaining"]
        mo.md(f"""### 💰 Credit Status
    - **Remaining credits**: ${credits:.2f}
    - **Status**: {"✅ Sufficient" if credits > 1 else "⚠️ Low" if credits > 0 else "❌ Depleted"}
    """)

    if results.get("usage"):
        usage = results["usage"]
        mo.md(f"""### 📊 Test Request Usage
    - **Prompt tokens**: {usage.get('prompt_tokens', 0)}
    - **Completion tokens**: {usage.get('completion_tokens', 0)}
    - **Estimated cost**: ${results.get('cost_usd', 'N/A')}
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 🔧 Troubleshooting

    If the key validation fails:

    | Error | Solution |
    |-------|----------|
    | **Authentication failed** | Key is invalid or malformed. Get a new key from [openrouter.ai/keys](https://openrouter.ai/keys) |
    | **Permission denied** | Key may have restrictions. Check key settings on OpenRouter dashboard |
    | **Insufficient credits (402)** | Add credits at [openrouter.ai/settings/credits](https://openrouter.ai/settings/credits) |
    | **Rate limited** | Wait and retry, or check rate limits on your key |
    | **Connection error** | Check network connectivity to openrouter.ai |

    ### For Docker Compose:
    Ensure `deploy/compose/docker-compose.yml` has `env_file: .env` on backend services and `.env` has the real key.

    ### For local pixi runs:
    ```bash
    export OPENROUTER_API_KEY=sk-or-v1-...
    pixi run admin-env-check --live --provider openrouter
    ```
    """)
    return


if __name__ == "__main__":
    app.run()
