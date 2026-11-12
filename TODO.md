# SkinCareWithHappy TODO

## Neon PostgreSQL foundation
- [x] Create Neon project in the requested organization.
- [x] Create PostgreSQL 17 database and application role.
- [x] Select the London (aws-eu-west-2) region.
- [x] Add environment-based Neon configuration to app/config.py.
- [x] Ensure .env files are ignored while allowing .env.example to be committed.
- [x] Add a safe environment-variable template.
- [x] Copy the Neon pooled connection string into local .env as DATABASE_URL.
- [x] Add the Neon direct connection string to local .env as DIRECT_DATABASE_URL.
- [x] Install and pin a PostgreSQL driver.
- [x] Repair and standardize SQLAlchemy models.
- [x] Migrate existing SQLite queries and schema to PostgreSQL-compatible SQLAlchemy models and seeded data.
- [x] Add Flask-Migrate/Alembic migrations.
- [x] Test database connectivity and core product/cart/order flows.
- [x] Establish a regular database export/backup routine.
- [x] Select Vercel as the Flask hosting platform and configure production environment variables.

## Payments (Nigeria launch)
- [x] Implement manual OPay/bank-transfer payment submission.
- [x] Require receipt upload and transaction reference.
- [x] Add admin-side payment verification and audit history.
- [x] Keep payment status separate from order status.
- [x] Validate receipt file type/content and store receipts in private S3-compatible storage.
- [x] Require authenticated admin access to download receipts; block legacy public receipt URLs.
- [x] Calculate checkout totals with Decimal and reserve stock in the order transaction.
- [x] Restore reserved stock when an admin rejects a payment.
- [x] Add a fixed-precision money and inventory-reservation migration with a data preflight.
- [x] Remove request-time schema creation/seeding and add an explicit idempotent product-seed command.
- [x] Add focused SQLite tests and an opt-in fresh PostgreSQL migration test.
- [ ] Configure a private, public-access-blocked receipt bucket in each deployment environment.
- [ ] Apply the checkout-hardening migration to each intended database after reviewing the preflight results.
- [ ] Define a timeout policy for payment-verification orders that are never reviewed, so reserved stock is eventually released.
- [ ] Revisit OPay merchant API integration after merchant onboarding.

## Admin console
- [x] Protect admin routes with environment-configured login and CSRF validation.
- [x] Replace sample dashboard figures and orders with live store metrics.
- [x] Add payment review with receipt links and audit attribution.
- [x] Add product catalog creation, pricing, and stock editing.
- [x] Add customer rollup view from order history.
- [x] Add persistent admin profile personalization and database-backed password changes.

## Customer accounts
- [x] Add CSRF-protected customer sign-up, sign-in, and sign-out.
- [x] Store customer passwords as hashes and normalize account email addresses.
- [x] Add a protected account page with signed-in order history.
- [x] Associate signed-in checkout orders with the customer while retaining guest checkout.
- [x] Keep legacy guest orders unassociated unless ownership can be safely verified.
- [x] Add and validate the customer-account database migration.
- [ ] Add email verification and password recovery before relying on accounts for sensitive ownership claims.

## Second-round security and migration corrections
- [x] Require a unique, sufficiently long production `SECRET_KEY`; reject missing and known insecure values without logging the secret.
- [x] Make online Alembic migrations use `DIRECT_DATABASE_URL`, with an intentional `DATABASE_URL` fallback, and normalize conventional PostgreSQL URLs to Psycopg 3.
- [x] Normalize PostgreSQL test URLs, preserve connection options, and isolate the opt-in migration test in a disposable schema with targeted cleanup.
- [x] Add temporary SQLite upgrade tests for both the initial legacy baseline and the historical `db.create_all()` schema, including data preservation and migration preflight failure behavior.
- [x] Preserve offline Alembic SQL generation and warn that offline output cannot run schema checks or the money preflight.
- [x] Document the tested legacy baseline, the manual backup/rehearsal procedure, and PostgreSQL test setup in `README.md`.
- [x] Run the complete local suite: 37 passed, 1 skipped (38 total); the opt-in PostgreSQL migration test was skipped because no disposable PostgreSQL database was configured.
- [ ] Run the fresh PostgreSQL migration test against a disposable PostgreSQL database; it has not been run unless explicitly configured.
- [ ] Rehearse the legacy migration procedure on a restorable copy of each real database before applying migrations to that database.
- [ ] Apply pending migrations to intended deployment databases only after reviewing the data preflight and verifying the direct migration connection.

Email verification and customer password recovery remain incomplete. Do not treat the second-round corrections or SQLite migration tests as evidence of production readiness.
