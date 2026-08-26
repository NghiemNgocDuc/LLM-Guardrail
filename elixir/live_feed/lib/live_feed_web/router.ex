defmodule LiveFeedWeb.Router do
  use LiveFeedWeb, :router

  pipeline :api do
    plug :accepts, ["json"]
  end

  scope "/api", LiveFeedWeb do
    pipe_through :api
  end
end
