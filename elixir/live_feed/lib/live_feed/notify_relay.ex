defmodule LiveFeed.NotifyRelay do
  @moduledoc """
  Bridges Postgres LISTEN/NOTIFY to Phoenix PubSub.

  Holds the Postgrex.Notifications LISTEN connection (started in the
  application supervision tree as LiveFeed.Notify) and fans every
  request_log_events payload out to the per-org Phoenix topic
  "requests:org_<org_id>". Rows without an org (API-key-less traffic)
  have no dashboard audience and are skipped.
  """

  use GenServer

  @channel "request_log_events"
  @topic_prefix "requests:"

  def start_link(opts \\ []) do
    GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(_opts) do
    {:ok, ref} = Postgrex.Notifications.listen(LiveFeed.Notify, @channel)
    {:ok, %{ref: ref}}
  end

  @impl true
  def handle_info({:notification, _pid, ref, @channel, payload}, %{ref: ref} = state) do
    case Jason.decode(payload) do
      {:ok, %{"org_id" => org_id} = event} when is_binary(org_id) ->
        LiveFeedWeb.Endpoint.broadcast(@topic_prefix <> org_id, "new_request", event)

      _ ->
        :ok
    end

    {:noreply, state}
  end

  def handle_info(_message, state), do: {:noreply, state}
end
