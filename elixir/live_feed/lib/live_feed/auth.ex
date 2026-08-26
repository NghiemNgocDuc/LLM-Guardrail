defmodule LiveFeed.Auth do
  @moduledoc """
  JWT verification for websocket connections — mirrors app/deps.py's
  get_current_user flow:

  1. Clerk token: RS256, key selected by `kid` from the JWKS document at
     FEED_CLERK_JWKS_URL (cached 1h, exactly like Python's `_jwks_cache`),
     or from the FEED_CLERK_JWT_KEY PEM. `verify_aud` is disabled in the
     Python code; claims checks are signature + exp only.
  2. Local token: HS256 with FEED_SECRET_KEY, `type` must be `"access"`.
  3. The `sub` claim is resolved to the user's org via the users table
     (clerk_id for Clerk tokens, id for local tokens) — the feed service
     reuses the gateway's own database rather than trusting a token claim.
  """

  @jwks_cache_key {__MODULE__, :jwks}

  def config, do: Application.get_env(:live_feed, :feed)

  @spec verify(binary()) :: {:ok, String.t()} | :error
  def verify(token) when is_binary(token) do
    with {:ok, payload} <- verify_clerk(token),
         {:ok, org_id} <- org_for_identity(payload["sub"], clerk: true) do
      {:ok, org_id}
    else
      _ -> verify_local(token)
    end
  end

  def verify(_), do: :error

  # ─── Clerk path (RS256) ────────────────────────────────────────────────────

  defp verify_clerk(token) do
    cond do
      jwks_url = config()[:clerk_jwks_url] |> String.trim() ->
        verify_via_jwks(token, jwks_url)

      pem = config()[:clerk_jwt_key] |> String.trim() ->
        verify_via_pem(token, pem)

      true ->
        :error
    end
  end

  defp verify_via_jwks(token, url) do
    with %{"kid" => kid} <- peek_header(token),
         {:ok, key} <- find_jwk(kid, url),
         {:ok, payload} <- verify_with(key, ["RS256"], token),
         :ok <- check_exp(payload) do
      {:ok, payload}
    else
      _ -> :error
    end
  end

  defp verify_via_pem(token, pem) do
    normalized = String.replace(pem, "\\n", "\n")
    key = JOSE.JWK.from_pem(normalized)

    with {:ok, payload} <- verify_with(key, ["RS256"], token),
         :ok <- check_exp(payload) do
      {:ok, payload}
    else
      _ -> :error
    end
  end

  defp peek_header(token) do
    try do
      case JOSE.JWT.peek(token) do
        {jws, _payload} -> jws.fields
        _ -> %{}
      end
    rescue
      _ -> %{}
    end
  end

  defp verify_with(key, algs, token) do
    case JOSE.JWT.verify_strict(key, algs, token) do
      {true, %JOSE.JWT{fields: payload}, _} -> {:ok, payload}
      _ -> :error
    end
  end

  defp find_jwk(kid, url) do
    case Enum.find(jwks(url), fn jwk -> jwk["kid"] == kid end) do
      nil -> :error
      jwk -> {:ok, JOSE.JWK.from_map(jwk)}
    end
  end

  defp jwks(url) do
    case :persistent_term.get(@jwks_cache_key, nil) do
      {ts, keys} when is_integer(ts) ->
        if ts + 3600 > System.system_time(:second), do: keys, else: fetch_and_cache(url)

      _ ->
        fetch_and_cache(url)
    end
  end

  defp fetch_and_cache(url) do
    keys =
      case fetch_jwks(url) do
        {:ok, %{"keys" => keys}} -> keys
        _ -> []
      end

    :persistent_term.put(@jwks_cache_key, {System.system_time(:second), keys})
    keys
  end

  defp fetch_jwks(url) do
    case Req.get(url, timeout: 15_000) do
      {:ok, %{status: 200, body: body}} -> {:ok, body}
      _ -> :error
    end
  rescue
    _ -> :error
  end

  # ─── Local path (HS256) ────────────────────────────────────────────────────

  defp verify_local(token) do
    key = JOSE.JWK.from_oct(config()[:secret_key])

    with {:ok, payload} <- verify_with(key, ["HS256"], token),
         :ok <- check_exp(payload),
         :ok <- check_access_type(payload),
         {:ok, org_id} <- org_for_identity(payload["sub"], clerk: false) do
      {:ok, org_id}
    else
      _ -> :error
    end
  end

  # ─── Shared claim checks ───────────────────────────────────────────────────

  defp check_exp(%{"exp" => exp}) when is_integer(exp) do
    if exp > System.system_time(:second), do: :ok, else: :error
  end

  defp check_exp(_), do: :error

  defp check_access_type(%{"type" => "access"}), do: :ok
  defp check_access_type(_), do: :error

  # ─── Org resolution ────────────────────────────────────────────────────────

  defp org_for_identity(sub, clerk: clerk?) when is_binary(sub) do
    query =
      if clerk?,
        do: "SELECT org_id FROM users WHERE clerk_id = $1",
        else: "SELECT org_id FROM users WHERE id = $1"

    case Postgrex.query(LiveFeed.Pg, query, [sub]) do
      {:ok, %{rows: [[org_id]]}} when is_binary(org_id) -> {:ok, org_id}
      _ -> :error
    end
  end

  defp org_for_identity(_, clerk: _), do: :error
end
