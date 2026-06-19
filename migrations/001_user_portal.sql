-- Copyright Anton Langhoff
-- SPDX-License-Identifier: MIT

-- SQLite schema for the TrendRadar IA private user portal.
-- Existing deployments that already created user_profiles before
-- contract_preference was added can run the ALTER TABLE statement below.

ALTER TABLE user_profiles ADD COLUMN contract_preference TEXT;
