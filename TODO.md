# SkinCareWithHappy TODO

## Neon PostgreSQL foundation
- [x] Create Neon project in the requested organization.
- [x] Create PostgreSQL 17 database and application role.
- [x] Select the London (aws-eu-west-2) region.
- [x] Add environment-based Neon configuration to app/config.py.
- [x] Ensure .env files are ignored while allowing .env.example to be committed.
- [x] Add a safe environment-variable template.
- [ ] Copy the Neon pooled connection string into local .env as DATABASE_URL.
- [ ] Add the Neon direct connection string to local .env as DIRECT_DATABASE_URL.
- [ ] Install and pin a PostgreSQL driver.
- [ ] Repair and standardize SQLAlchemy models.
- [ ] Migrate existing SQLite queries and schema to PostgreSQL.
- [ ] Add Flask-Migrate/Alembic migrations.
- [ ] Test database connectivity and core product/cart/order flows.
- [ ] Establish a regular database export/backup routine.
- [ ] Select Flask application hosting and configure production environment variables.

## Payments (Nigeria launch)
- [ ] Implement manual OPay/bank-transfer payment submission.
- [ ] Require receipt upload and transaction reference.
- [ ] Add admin-side payment verification and audit history.
- [ ] Keep payment status separate from order status.
- [ ] Revisit OPay merchant API integration after merchant onboarding.
