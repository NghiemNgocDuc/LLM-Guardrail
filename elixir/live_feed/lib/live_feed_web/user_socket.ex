defmodule LiveFeedWeb.UserSocket do
  @moduledoc """
  Websocket transport for the live request feed.

  connect/3 verifies the Bearer JWT exactly like the Python API
  (app/deps.py — Clerk RS256 first, local HS256 fallback) via
  LiveFeed.Auth and assigns the caller's org_id. A socket may only join
  the topic for its own org; RequestChannel enforces that.
  """

  use Phoenix.Socket

  channel "requests:*", LiveFeedWeb.RequestChannel

  @impl true
  def connect(params, socket, _connect_info) do
    token = params["token"] || bearer_token(params["authorization"])

    case LiveFeed.Auth.verify(token) do
      {:ok, org_id} -> {:ok, assign(socket, :org_id, org_id)}
      _ -> :error
    end
  end

  @impl true
  def id(_socket), do: nil

  defp bearer_token(nil), do: nil

  defp bearer_token(header) when is_binary(header) do
    case String.split(String.trim(header), " ", parts: 2) do
      ["Bearer", token] -> token
      _ -> nil
    end
  end
end
