defmodule LiveFeed.TestHelpers do
  @moduledoc """
  Shared helpers for the feed integration tests.

  Creates (idempotently) the minimal users / request_logs tables plus the
  request_log_events notify trigger — the same trigger alembic migration
  0013 installs on the real schema — so tests are self-contained and never
  depend on which other scratch tests touched the database.
  """
  def setup_schema! do
    {:ok, _} =
      Postgrex.query(
        LiveFeed.Pg,
        "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, clerk_id TEXT, org_id TEXT)",
        []
      )

    {:ok, _} =
      Postgrex.query(
        LiveFeed.Pg,
        """
        CREATE TABLE IF NOT EXISTS request_logs (
          id TEXT PRIMARY KEY, org_id TEXT, status TEXT, fired_rule TEXT,
          created_at TIMESTAMPTZ
        )
        """,
        []
      )

    {:ok, _} =
      Postgrex.query(
        LiveFeed.Pg,
        """
        CREATE OR REPLACE FUNCTION request_logs_notify() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE payload text;
        BEGIN
          payload := json_build_object(
            'id', NEW.id::text, 'org_id', NEW.org_id, 'status', NEW.status,
            'fired_rule', NEW.fired_rule, 'created_at', NEW.created_at
          )::text;
          PERFORM pg_notify('request_log_events', payload);
          RETURN NEW;
        END;
        $$;
        """,
        []
      )

    {:ok, _} =
      Postgrex.query(
        LiveFeed.Pg,
        "DROP TRIGGER IF EXISTS trg_request_logs_notify ON request_logs",
        []
      )

    {:ok, _} = Postgrex.query(LiveFeed.Pg, "DELETE FROM request_logs", [])

    {:ok, _} =
      Postgrex.query(
        LiveFeed.Pg,
        "CREATE TRIGGER trg_request_logs_notify AFTER INSERT ON request_logs FOR EACH ROW EXECUTE FUNCTION request_logs_notify()",
        []
      )

    {:ok, _} =
      Postgrex.query(
        LiveFeed.Pg,
        """
        INSERT INTO users (id, clerk_id, org_id) VALUES
          ('u_a', 'clerk_a', 'org_a'),
          ('u_b', 'clerk_b', 'org_b')
        ON CONFLICT (id) DO NOTHING
        """,
        []
      )

    :ok
  end

  def local_token(user_id) do
    key = JOSE.JWK.from_oct(LiveFeed.Auth.config()[:secret_key])

    jwt = %JOSE.JWT{
      fields: %{
        "sub" => user_id,
        "type" => "access",
        "exp" => System.system_time(:second) + 3600
      }
    }

    {_header, %{"payload" => payload, "protected" => protected, "signature" => signature}} =
      JOSE.JWT.sign(key, jwt)

    Enum.join([protected, payload, signature], ".")
  end

  def insert_log!(id, org_id, status, fired_rule) do
    {:ok, _} =
      Postgrex.query(
        LiveFeed.Pg,
        "INSERT INTO request_logs (id, org_id, status, fired_rule, created_at) " <>
          "VALUES ($1, $2, $3, $4, now())",
        [id, org_id, status, fired_rule]
      )

    :ok
  end
end
