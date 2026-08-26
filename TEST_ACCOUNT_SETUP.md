# Test Account Setup Guide

## Overview
The test account `cs@umass.edu` with password `123456789` has been added to the product for easy testing. The credentials are displayed directly above the login form.

## What Changed

### 1. **Frontend - Login Page Info Box** [OK]
- A blue info box now appears above the login form when on the login tab
- Displays the test credentials: `cs@umass.edu` / `123456789`
- Allows outsiders to test the product without creating their own account

**File:** `frontend.jsx`
- Added a styled test credentials display box above the login form
- Only shows on the login tab to keep the signup/forgot password flows clean

### 2. **Promote Account to Admin**

#### Option A: Via Supabase SQL Editor (Recommended)
1. Go to [Supabase Dashboard](https://supabase.com) → Your Project
2. Click **SQL Editor** in the left sidebar
3. Create a new query and paste:

```sql
-- Check if the account exists
SELECT id, email, full_name, is_admin, org_id FROM users WHERE email = 'cs@umass.edu';

-- If it exists, run this to promote to admin:
UPDATE users SET is_admin = TRUE WHERE email = 'cs@umass.edu';

-- Verify:
SELECT id, email, full_name, is_admin, org_id FROM users WHERE email = 'cs@umass.edu';
```

4. Click **Run** and confirm the account is now admin (`is_admin = TRUE`)

#### Option B: Via Admin Panel
1. Sign in with your admin account (`dnghiem@umass.edu`)
2. Go to **Admin** tab
3. Find `cs@umass.edu` in the users list
4. Click the **"MEMBER" → "ADMIN"** toggle button

#### Option C: Via Python Script (Requires Database Connection)
```bash
cd llm_guardrails_v2_wired
export DATABASE_URL="your_supabase_connection_string"
python scripts/setup_test_account.py
```

## Creating the Test Account (If It Doesn't Exist)

### Via Signup Form
1. Visit the login page
2. Click **Sign up** tab
3. Enter:
   - Full Name: `Test Account`
   - Email: `cs@umass.edu`
   - Password: `123456789`
   - Organization: `(optional)`
4. Click **Create an Account**
5. Verify email (should auto-verify in test mode if `REQUIRE_EMAIL_VERIFICATION=false`)
6. Then promote to admin using one of the methods above

### Via SQL (If You Have Database Access)
```sql
INSERT INTO users (id, email, hashed_password, full_name, is_active, is_admin, email_verified, org_id)
VALUES (
  'test-account-id-here',
  'cs@umass.edu',
  'hashed_password_here',  -- Use bcrypt hash of "123456789"
  'Test Account',
  true,
  true,  -- Make admin
  true,
  null   -- No org initially
);
```

## Testing the Account

1. Go to `https://llm-guardrail.onrender.com` (or your deployment URL)
2. You should see the test credentials info box above the login form
3. Click **Sign in**
4. Enter:
   - Email: `cs@umass.edu`
   - Password: `123456789`
5. You should now be logged in with full admin access

## What Can the Test Account Access?

As an admin account, `cs@umass.edu` can:
- [OK] Access the **Dashboard** (all analytics)
- [OK] Access the **LLM Playground** (chat)
- [OK] Manage **Policy** rules
- [OK] Access **Admin** panel to:
  - Manage users (invite, remove, change roles)
  - Manage API keys
  - View all organization settings

## Security Note

This test account and its credentials are visible in the frontend code. **For production:**
- Remove the test credentials info box from the UI
- Delete or disable the test account
- Use environment-specific feature flags to show/hide test info

## Files Modified

- `frontend.jsx` - Added test credentials info box
- `scripts/setup_test_account.py` - Python helper (requires DB connection)
- `scripts/promote_test_account.py` - Promote existing account (requires DB connection)
- `scripts/promote_test_account.sql` - SQL script for Supabase
