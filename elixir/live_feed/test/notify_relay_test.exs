defmodule LiveFeed.NotifyRelayTest do
  use ExUnit.Case, async: false

  alias LiveFeed.TestHelpers

  setup do
    TestHelpers.setup_schema!()
    :ok
  end

  test "broadcasts new request_log rows to the per-org topic, scoped by org" do
    topic_a = "requests:org_a"
    topic_b = "requests:org_b"

    :ok = Phoenix.PubSub.subscribe(LiveFeed.PubSub, topic_a)
    :ok = Phoenix.PubSub.subscribe(LiveFeed.PubSub, topic_b)

    TestHelpers.insert_log!("elixir-feed-1", "org_a", "delivered", nil)

    assert_receive %Phoenix.Socket.Broadcast{
                     topic: ^topic_a,
                     event: "new_request",
                     payload: payload
                   },
                   1_000

    assert payload["id"] == "elixir-feed-1"
    assert payload["status"] == "delivered"
    assert payload["fired_rule"] == nil
    refute_receive %Phoenix.Socket.Broadcast{topic: ^topic_b, event: "new_request"}, 300

    TestHelpers.insert_log!("elixir-feed-2", "org_b", "input_blocked", "pii_detected")

    assert_receive %Phoenix.Socket.Broadcast{
                     topic: ^topic_b,
                     event: "new_request",
                     payload: payload_b
                   },
                   1_000

    assert payload_b["fired_rule"] == "pii_detected"
    refute_receive %Phoenix.Socket.Broadcast{topic: ^topic_a, event: "new_request"}, 300
  end

  test "rows without an org are not broadcast (no dashboard audience)" do
    topic = "requests:org_a"
    :ok = Phoenix.PubSub.subscribe(LiveFeed.PubSub, topic)

    TestHelpers.insert_log!("elixir-feed-3", nil, "error", nil)

    refute_receive %Phoenix.Socket.Broadcast{topic: ^topic, event: "new_request"}, 300
  end
end
