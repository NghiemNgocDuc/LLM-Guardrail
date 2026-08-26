defmodule LiveFeedWeb.ChannelCase do
  use ExUnit.CaseTemplate

  using do
    quote do
      # The default endpoint for testing
      @endpoint LiveFeedWeb.Endpoint

      import Phoenix.ChannelTest
    end
  end
end
