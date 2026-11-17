ALTER TABLE apple_metrics_schedules ADD COLUMN stop_at REAL CHECK (stop_at IS NULL OR stop_at > 0);
