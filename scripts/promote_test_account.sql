-- Promote test account cs@umass.edu to admin
-- Run this SQL directly in Supabase SQL Editor

-- First, check if the account exists
SELECT id, email, full_name, is_admin, org_id FROM users WHERE email = 'cs@umass.edu';

-- Update to make admin (only if account exists)
-- Uncomment and run the line below after confirming the account exists:
-- UPDATE users SET is_admin = TRUE WHERE email = 'cs@umass.edu';

-- Verify the update
-- SELECT id, email, full_name, is_admin, org_id FROM users WHERE email = 'cs@umass.edu';
