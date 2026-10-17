"""Radio skips and likes steer each person's own station; nothing is shared."""


def up(conn):
    conn.execute(
        """CREATE TABLE radio_feedback (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL, artist TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('skip','like')),
            at INTEGER NOT NULL)"""
    )
    conn.execute("CREATE INDEX radio_feedback_user ON radio_feedback(user_id,at)")
