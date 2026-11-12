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
- [ ] Revisit OPay merchant API integration after merchant onboarding.

## Admin console
- [x] Protect admin routes with environment-configured login and CSRF validation.
- [x] Replace sample dashboard figures and orders with live store metrics.
- [x] Add payment review with receipt links and audit attribution.
- [x] Add product catalog creation, pricing, and stock editing.
- [x] Add customer rollup view from order history.
- [x] Add persistent admin profile personalization and database-backed password changes.
