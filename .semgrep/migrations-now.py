# Fixture per `semgrep --test` (regola generic; non eseguita).
# ruleid: menu-bare-now-in-migrations
op.execute("INSERT INTO t (created_at) VALUES (now())")
# ruleid: menu-bare-now-in-migrations
op.execute("INSERT INTO t (created_at) VALUES (CURRENT_TIMESTAMP)")
# ok: menu-bare-now-in-migrations
op.execute("INSERT INTO t (created_at) VALUES (app.now_utc())")
# ok: menu-bare-now-in-migrations
NOW_UTC_BODY = "select now()"  # allow-bare-now: corpo di app.now_utc()
# ruleid: menu-bare-now-in-migrations
OTHER_BODY = "select now()"
# ruleid: menu-bare-now-in-migrations
NOW_UTC_BODY = "select now(), now()"
