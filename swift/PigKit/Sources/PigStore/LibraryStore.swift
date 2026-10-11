import Foundation
import GRDB
import PigDomain

/// Each instance is permanently bound to one server/person database.
public actor LibraryStore {
  private let database: DatabaseQueue
  public init(path: String) throws {
    let queue = try DatabaseQueue(path: path)
    var migrator = DatabaseMigrator()
    migrator.registerMigration("library-v1") { db in
      try db.execute(sql: "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
      for kind in LibraryCollection.allCases {
        try db.execute(
          sql:
            "CREATE TABLE \(kind.rawValue) (id TEXT PRIMARY KEY, name TEXT NOT NULL, payload BLOB NOT NULL)"
        )
        try db.execute(
          sql: "CREATE INDEX \(kind.rawValue)_name ON \(kind.rawValue)(name COLLATE NOCASE, id)")
      }
      try db.execute(
        sql:
          "CREATE VIRTUAL TABLE track_search USING fts5(id UNINDEXED, title, artist, album, tokenize='unicode61 remove_diacritics 2')"
      )
      try db.execute(
        sql: "CREATE INDEX tracks_album ON tracks(json_extract(CAST(payload AS TEXT),'$.album_id'))"
      )
      try db.execute(
        sql:
          "CREATE TABLE downloads (track_id TEXT PRIMARY KEY, source_revision TEXT, file_name TEXT NOT NULL, bytes INTEGER NOT NULL)"
      )
    }
    migrator.registerMigration("indexed-search-rowids-v2") { db in
      try db.execute(sql: "DELETE FROM track_search")
      try db.execute(
        sql:
          "INSERT INTO track_search(rowid,id,title,artist,album) SELECT rowid,id,json_extract(CAST(payload AS TEXT),'$.title'),json_extract(CAST(payload AS TEXT),'$.artist'),coalesce(json_extract(CAST(payload AS TEXT),'$.album'),'') FROM tracks"
      )
    }
    migrator.registerMigration("entity-search-v3") { db in
      try db.execute(
        sql:
          "CREATE VIRTUAL TABLE album_search USING fts5(id UNINDEXED, title, artist, tokenize='unicode61 remove_diacritics 2')"
      )
      try db.execute(
        sql:
          "CREATE VIRTUAL TABLE artist_search USING fts5(id UNINDEXED, name, tokenize='unicode61 remove_diacritics 2')"
      )
      try db.execute(
        sql:
          "INSERT INTO album_search(rowid,id,title,artist) SELECT rowid,id,json_extract(CAST(payload AS TEXT),'$.title'),json_extract(CAST(payload AS TEXT),'$.artist') FROM albums"
      )
      try db.execute(
        sql: "INSERT INTO artist_search(rowid,id,name) SELECT rowid,id,name FROM artists")
    }
    try migrator.migrate(queue)
    database = queue
  }

  public func revision() throws -> String? {
    try database.read {
      try String.fetchOne($0, sql: "SELECT value FROM metadata WHERE key='revision'")
    }
  }
  public func count(_ collection: LibraryCollection) throws -> Int {
    try database.read {
      try Int.fetchOne($0, sql: "SELECT count(*) FROM \(collection.rawValue)") ?? 0
    }
  }
  public func track(id: String) throws -> Track? {
    try database.read { db in
      guard
        let data = try Data.fetchOne(
          db, sql: "SELECT payload FROM tracks WHERE id=?", arguments: [id])
      else { return nil }
      return try LibraryCodec.decoder().decode(Track.self, from: data)
    }
  }
  public func tracks(query: String = "", albumId: String? = nil, offset: Int = 0, limit: Int = 100)
    throws -> [Track]
  {
    try database.read { db in
      let rows: [Row]
      if !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        let terms = query.split(whereSeparator: { $0.isWhitespace }).map {
          "\"" + $0.replacingOccurrences(of: "\"", with: "\"\"") + "\"*"
        }.joined(separator: " AND ")
        rows = try Row.fetchAll(
          db,
          sql:
            "SELECT t.payload FROM tracks t JOIN track_search s ON t.id=s.id WHERE track_search MATCH ? ORDER BY rank LIMIT ? OFFSET ?",
          arguments: [terms, limit, offset])
      } else if let albumId {
        rows = try Row.fetchAll(
          db,
          sql:
            "SELECT payload FROM tracks WHERE json_extract(CAST(payload AS TEXT),'$.album_id')=? ORDER BY CAST(json_extract(CAST(payload AS TEXT),'$.disc_number') AS INTEGER), CAST(json_extract(CAST(payload AS TEXT),'$.track_number') AS INTEGER), id",
          arguments: [albumId])
      } else {
        rows = try Row.fetchAll(
          db, sql: "SELECT payload FROM tracks ORDER BY name COLLATE NOCASE, id LIMIT ? OFFSET ?",
          arguments: [limit, offset])
      }
      return try rows.map {
        try LibraryCodec.decoder().decode(Track.self, from: $0["payload"] as Data)
      }
    }
  }
  public func albums(artistId: String, offset: Int = 0, limit: Int = 100) throws -> [Album] {
    guard offset >= 0, (1...200).contains(limit) else { throw StoreSearchFailure.invalidPage }
    return try database.read { db in
      let rows = try Row.fetchAll(
        db,
        sql:
          "SELECT payload FROM albums WHERE id IN (SELECT value FROM artists, json_each(CAST(artists.payload AS TEXT), '$.album_ids') WHERE artists.id=?) ORDER BY name COLLATE NOCASE,id LIMIT ? OFFSET ?",
        arguments: [artistId, limit, offset])
      return try rows.map {
        try LibraryCodec.decoder().decode(Album.self, from: $0["payload"] as Data)
      }
    }
  }

  public func searchPage(query: String, offset: Int = 0, limit: Int = 100) throws
    -> LibrarySearchPage
  {
    guard offset >= 0, offset <= 1_000_000, (1...200).contains(limit) else {
      throw StoreSearchFailure.invalidPage
    }
    let query = SearchText.clean(query)
    guard !query.isEmpty else { return LibrarySearchPage() }
    let terms = query.split(whereSeparator: { $0.isWhitespace }).map {
      "\"" + $0.replacingOccurrences(of: "\"", with: "\"\"") + "\"*"
    }.joined(separator: " AND ")
    return try database.read { db in
      func page<T: Decodable>(_ table: String, _ index: String, _ type: T.Type) throws -> ([T], Int)
      {
        let rows = try Row.fetchAll(
          db,
          sql:
            "SELECT t.payload FROM \(table) t JOIN \(index) s ON t.rowid=s.rowid WHERE \(index) MATCH ? ORDER BY rank, t.id LIMIT ? OFFSET ?",
          arguments: [terms, limit, offset])
        let count =
          try Int.fetchOne(
            db, sql: "SELECT count(*) FROM \(index) WHERE \(index) MATCH ?", arguments: [terms])
          ?? 0
        return (
          try rows.map { try LibraryCodec.decoder().decode(T.self, from: $0["payload"] as Data) },
          count
        )
      }
      let (tracks, trackCount) = try page("tracks", "track_search", Track.self)
      let (albums, albumCount) = try page("albums", "album_search", Album.self)
      let (artists, artistCount) = try page("artists", "artist_search", Artist.self)
      let end = offset + limit
      let revision =
        try String.fetchOne(db, sql: "SELECT value FROM metadata WHERE key='revision'") ?? ""
      return LibrarySearchPage(
        tracks: tracks, albums: albums, artists: artists, offset: offset,
        nextOffset: end < max(trackCount, albumCount, artistCount) ? end : nil, revision: revision)
    }
  }

  public func albums(offset: Int = 0, limit: Int = 100) throws -> [Album] {
    try read(.albums, offset: offset, limit: limit)
  }
  public func artists(offset: Int = 0, limit: Int = 100) throws -> [Artist] {
    try read(.artists, offset: offset, limit: limit)
  }
  public func playlists() throws -> [Playlist] { try read(.playlists, offset: 0, limit: 10000) }

  private func read<T: Decodable>(_ kind: LibraryCollection, offset: Int, limit: Int) throws -> [T]
  {
    try database.read { db in
      try Row.fetchAll(
        db,
        sql:
          "SELECT payload FROM \(kind.rawValue) ORDER BY name COLLATE NOCASE, id LIMIT ? OFFSET ?",
        arguments: [limit, offset]
      )
      .map { try LibraryCodec.decoder().decode(T.self, from: $0["payload"] as Data) }
    }
  }

  /// Transactional replacement preserves the old valid cache if any row fails.
  public func replace(_ snapshot: LibrarySnapshot) throws {
    try database.write { db in
      for kind in LibraryCollection.allCases { try db.execute(sql: "DELETE FROM \(kind.rawValue)") }
      for index in ["track_search", "album_search", "artist_search"] {
        try db.execute(sql: "DELETE FROM \(index)")
      }
      try Self.upsert(snapshot, db: db)
    }
  }
  public func apply(_ delta: LibraryDelta) throws {
    try database.write { db in
      for (kind, ids) in [
        (LibraryCollection.tracks, delta.deletes.tracks), (.albums, delta.deletes.albums),
        (.artists, delta.deletes.artists), (.playlists, delta.deletes.playlists),
      ] {
        for id in ids {
          let index: String? =
            switch kind {
            case .tracks: "track_search"
            case .albums: "album_search"
            case .artists: "artist_search"
            case .playlists: nil
            }
          if let index {
            try db.execute(
              sql:
                "DELETE FROM \(index) WHERE rowid=(SELECT rowid FROM \(kind.rawValue) WHERE id=?)",
              arguments: [id])
          }
          try db.execute(sql: "DELETE FROM \(kind.rawValue) WHERE id=?", arguments: [id])
        }
      }
      try Self.upsert(
        .init(
          revision: delta.revision, tracks: delta.upserts.tracks, albums: delta.upserts.albums,
          artists: delta.upserts.artists, playlists: delta.upserts.playlists), db: db)
    }
  }
  private static func upsert(_ snapshot: LibrarySnapshot, db: Database) throws {
    for track in snapshot.tracks {
      try save(track, kind: .tracks, name: track.title, db: db)
      try db.execute(
        sql: "DELETE FROM track_search WHERE rowid=(SELECT rowid FROM tracks WHERE id=?)",
        arguments: [track.id])
      try db.execute(
        sql:
          "INSERT INTO track_search(rowid,id,title,artist,album) VALUES ((SELECT rowid FROM tracks WHERE id=?),?,?,?,?)",
        arguments: [track.id, track.id, track.title, track.artist, track.album ?? ""])
    }
    for album in snapshot.albums {
      try save(album, kind: .albums, name: album.title, db: db)
      try db.execute(
        sql: "DELETE FROM album_search WHERE rowid=(SELECT rowid FROM albums WHERE id=?)",
        arguments: [album.id])
      try db.execute(
        sql:
          "INSERT INTO album_search(rowid,id,title,artist) VALUES ((SELECT rowid FROM albums WHERE id=?),?,?,?)",
        arguments: [album.id, album.id, album.title, album.artist])
    }
    for artist in snapshot.artists {
      try save(artist, kind: .artists, name: artist.name, db: db)
      try db.execute(
        sql: "DELETE FROM artist_search WHERE rowid=(SELECT rowid FROM artists WHERE id=?)",
        arguments: [artist.id])
      try db.execute(
        sql:
          "INSERT INTO artist_search(rowid,id,name) VALUES ((SELECT rowid FROM artists WHERE id=?),?,?)",
        arguments: [artist.id, artist.id, artist.name])
    }
    for playlist in snapshot.playlists {
      try save(playlist, kind: .playlists, name: playlist.name, db: db)
    }
    try db.execute(
      sql:
        "INSERT INTO metadata(key,value) VALUES ('revision',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      arguments: [snapshot.revision])
  }
  private static func save<T: Encodable & Identifiable>(
    _ value: T, kind: LibraryCollection, name: String, db: Database
  ) throws where T.ID == String {
    let payload = try LibraryCodec.encoder().encode(value)
    try db.execute(
      sql:
        "INSERT INTO \(kind.rawValue)(id,name,payload) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,payload=excluded.payload",
      arguments: [value.id, name, payload])
  }
}

public enum StoreSearchFailure: Error, Sendable { case invalidPage }
