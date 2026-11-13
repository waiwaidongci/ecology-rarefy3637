-- 002_upload_batches.sql
-- 离线整批回传与冲突处置。
-- SQLAlchemy metadata 会在启动时 create_all 补齐这些表与列；本文件记录结构口径，
-- 已部署库需按下列语句显式增量迁移（PostgreSQL 16）。

-- 样线增加修订号、内容指纹与更新时间；旧数据修订号从1开始，content_hash 首次回传比对时惰性补算。
ALTER TABLE transects ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE transects ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE transects ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS upload_batches (
 id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 batch_ref VARCHAR(80) NOT NULL UNIQUE,
 survey_id INTEGER NOT NULL REFERENCES surveys(id),
 source VARCHAR(120) NOT NULL DEFAULT '',
 payload_hash VARCHAR(64) NOT NULL,
 status VARCHAR(20) NOT NULL DEFAULT 'open',
 redeliveries INTEGER NOT NULL DEFAULT 0,
 creator_id INTEGER NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS upload_items (
 id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 batch_id INTEGER NOT NULL REFERENCES upload_batches(id),
 line_no INTEGER NOT NULL,
 reference VARCHAR(50),
 transect_id INTEGER REFERENCES transects(id),
 status VARCHAR(20) NOT NULL,
 reason VARCHAR(500) NOT NULL DEFAULT '',
 incoming JSON NOT NULL DEFAULT '{}'::json,
 existing_snapshot JSON,
 diff JSON,
 content_hash VARCHAR(64),
 recheck_required BOOLEAN NOT NULL DEFAULT false,
 resolution VARCHAR(20),
 resolved_by VARCHAR(120),
 resolved_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE (batch_id,line_no)
);

CREATE INDEX IF NOT EXISTS ix_upload_items_batch ON upload_items(batch_id);
CREATE INDEX IF NOT EXISTS ix_upload_items_status ON upload_items(status);
