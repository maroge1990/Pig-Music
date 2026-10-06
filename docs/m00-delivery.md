# M00: additive SQLite migration foundation

7 October 2026. Store startup now applies an explicit versioned migration ledger before projecting the library. Baseline 0001 creates the existing tables on fresh installations and leaves all existing rows unchanged. Every pending migration and its ledger entry run in a single immediate transaction; failure rolls back both DDL and data. Unknown future versions and incomplete ledgers fail closed rather than silently downgrading state.

Connections retain WAL and now enable foreign-key enforcement. The stopped-state verifier allows only the validated version-1 ledger as an additive exception; existing durable rows still have to match exactly.

Validation: 133 backend tests pass, including fresh/legacy schema parity, preservation of preference/selection/playlist fixtures, repeated startup idempotence, DDL failure rollback, future-schema rejection and connection pragmas. Existing artwork, HTTP, queue, download and recovery tests remain passing. No account or personal-library migration is applied by this package.

Container and real stopped-state verification passed and M00 was deployed with brand-https-20261007-v1; all 1395 tracks and existing durable rows were retained. An earlier container cannot detect a future schema itself; rollback must always restore the matching stopped-state backup as the existing deployment tool does. Never run a downgraded image against migrated live state.
