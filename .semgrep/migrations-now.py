# Fixture per `semgrep --test` (regola generic; non eseguita).
# ruleid: menu-bare-now-in-migrations
op.execute("INSERT INTO t (created_at) VALUES (now())")
# ruleid: menu-bare-now-in-migrations
op.execute("INSERT INTO t (created_at) VALUES (CURRENT_TIMESTAMP)")
# ok: menu-bare-now-in-migrations
op.execute("INSERT INTO t (created_at) VALUES (app.now_utc())")
