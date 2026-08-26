defmodule LiveFeedWeb.UserSocketTest do
  use LiveFeedWeb.ChannelCase

  alias LiveFeed.TestHelpers

  setup do
    TestHelpers.setup_schema!()
    :ok
  end

  test "rejects sockets without a token" do
    assert :error = connect(LiveFeedWeb.UserSocket, %{})
  end

  test "rejects sockets with a garbage token" do
    assert :error = connect(LiveFeedWeb.UserSocket, %{"token" => "not.a.jwt"})
  end

  test "rejects sockets with an expired local token" do
    expired = expired_token("u_a")
    assert :error = connect(LiveFeedWeb.UserSocket, %{"token" => expired})
  end

  test "org A token joins only its own org topic" do
    token = TestHelpers.local_token("u_a")
    assert {:ok, socket} = connect(LiveFeedWeb.UserSocket, %{"token" => token})
    assert socket.assigns.org_id == "org_a"

    assert {:ok, _resp, _socket} = join(socket, "requests:org_a", %{})
    assert {:error, :forbidden} = join(socket, "requests:org_b", %{})
  end

  test "org B token cannot join org A topic — and vice versa" do
    token_b = TestHelpers.local_token("u_b")
    assert {:ok, socket_b} = connect(LiveFeedWeb.UserSocket, %{"token" => token_b})
    assert socket_b.assigns.org_id == "org_b"

    assert {:ok, _resp, _socket} = join(socket_b, "requests:org_b", %{})
    assert {:error, :forbidden} = join(socket_b, "requests:org_a", %{})
  end

  defp expired_token(user_id) do
    key = JOSE.JWK.from_oct(LiveFeed.Auth.config()[:secret_key])

    jwt = %JOSE.JWT{
      fields: %{"sub" => user_id, "type" => "access", "exp" => System.system_time(:second) - 60}
    }

    {_header, %{"payload" => payload, "protected" => protected, "signature" => signature}} =
      JOSE.JWT.sign(key, jwt)

    Enum.join([protected, payload, signature], ".")
  end
end
