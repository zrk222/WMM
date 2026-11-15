"""Append-only discovery research history schema."""

SCHEMA = """\
CREATE TABLE IF NOT EXISTS discovery_documents(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,version INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('REVIEW','COLLECTION','WATCH','ATTEMPT')),data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id,version));
CREATE TRIGGER IF NOT EXISTS discovery_no_replace BEFORE INSERT ON discovery_documents WHEN EXISTS(SELECT 1 FROM discovery_documents WHERE app_id=NEW.app_id AND id=NEW.id AND version=NEW.version) BEGIN SELECT RAISE(ABORT,'Research history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_no_rowid_replace BEFORE INSERT ON discovery_documents WHEN EXISTS(SELECT 1 FROM discovery_documents WHERE rowid=NEW.rowid) BEGIN SELECT RAISE(ABORT,'Research history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_no_update BEFORE UPDATE ON discovery_documents BEGIN SELECT RAISE(ABORT,'Research history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS discovery_no_delete BEFORE DELETE ON discovery_documents BEGIN SELECT RAISE(ABORT,'Research history is immutable'); END;
"""
