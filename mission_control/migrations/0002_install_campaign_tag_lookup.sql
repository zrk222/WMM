CREATE INDEX IF NOT EXISTS install_attribution_public_tag
ON install_attribution_batches(campaign_token, app_id);
