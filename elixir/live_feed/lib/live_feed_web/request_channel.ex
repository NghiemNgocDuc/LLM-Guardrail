defmodule LiveFeedWeb.RequestChannel do
  @moduledoc """
  Per-org live request channel.

  Topic shape: "requests:org_<org_id>". The topic's org suffix must
  equal the org the verified token resolved to — a token for org A can
  never join org B's topic (and thus never receives org B's events).
  """

  use Phoenix.Channel

  @impl true
  def join("requests:" <> org_id, _payload, socket) do
    if socket.assigns.org_id == org_id do
      {:ok, socket}
    else
      {:error, :forbidden}
    end
  end

  def join(_topic, _payload, _socket), do: {:error, :forbidden}
end
