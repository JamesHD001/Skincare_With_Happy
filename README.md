# SkinCareWithHappy

SkinCareWithHappy is a Flask-based skincare storefront project. It provides a web interface for browsing skincare products, learning about skincare, viewing product details, managing a shopping cart, and starting a checkout flow.

> **Project status:** Active development. The application uses Flask, Jinja templates, SQLAlchemy, and Alembic migrations, with Neon PostgreSQL configuration and a SQLite local-development fallback. The storefront supports manual payment review, a protected admin console, and customer accounts. Vercel is the deployment target.

## Current technology

- **Backend:** Python and Flask
- **Templating:** Jinja2
- **Database:** Flask-SQLAlchemy with Alembic migrations; Neon PostgreSQL is supported
- **Payments:** Manual transfer/OPay submission with receipt and reference review by an administrator
- **Customer accounts:** CSRF-protected sign-up/sign-in, guest checkout, and signed-in order history
- **Receipt storage:** Private S3-compatible storage; receipts are not served from the public static directory
- **Configuration:** `python-dotenv` and environment variables
- **PostgreSQL target:** Neon PostgreSQL

## Current application areas

The Flask application currently defines routes for:

- Home, shop, about, contact, and skincare learning pages
- Product listing and skin-type filtering
- Product detail pages
- Shopping cart add, update, and remove actions
- Customer sign-up/sign-in and protected account order history
- Checkout, payment-result pages, and an admin console

Some routes and templates still need to be aligned, and the application has not yet received a complete security and production-readiness review. The presence of a page or helper function does not mean its full workflow is production-ready.

## Repository structure

```text
SkinCare_With_Happy/
├── app/
│   ├── app.py             # Flask application and routes
│   ├── config.py          # Environment-based configuration
│   ├── models.py          # SQLAlchemy data models
│   └── payment.py         # Paystack API helper functions
├── static/
│   ├── css/               # Stylesheets
│   ├── img/               # Image assets
│   └── js/                # Frontend JavaScript
├── templates/             # Jinja2 HTML templates
├── .env.example           # Safe environment-variable template
├── .gitignore
├── requirements.txt
└── TODO.md                # Project roadmap and outstanding work
```

## Getting started

### 1. Requirements

- Python 3
- Git
- A local environment capable of running Flask

### 2. Clone the repository

```bash
git clone https://github.com/JamesHD001/Skincare_With_Happy.git
cd Skincare_With_Happy
```

### 3. Select the development branch

The current database-foundation work is on:

```text
refactor/postgresql-payment-foundation
```

To switch to it:

```bash
git switch refactor/postgresql-payment-foundation
```

### 4. Create and activate a virtual environment

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Configure environment variables

Copy the example file:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Set the values in the project-root `.env` locally; `.env.example` is a template only and is never loaded by the app. Existing process/Vercel environment variables take precedence. When `APP_ENV=test`, the app does not load `.env`, preventing automated tests from inheriting deployment credentials. Never commit `.env` or paste database passwords and payment secrets into source files, screenshots, issues, or chat messages.

- `SECRET_KEY`: set a long, random secret for Flask sessions.
- `APP_ENV`: use `production` for a deployment. Production startup requires a unique `SECRET_KEY` of at least 32 characters and rejects known development defaults; the app fails with an actionable message without printing the secret. Development and test-only fallback keys are environment-specific and must never be used in production.
- `ADMIN_USERNAME` and `ADMIN_PASSWORD`: bootstrap credentials for the protected admin console. Use unique credentials and keep them only in local/Vercel environment settings.
- `DATABASE_URL`: Neon pooled PostgreSQL connection for normal application traffic; when unset, the app uses the configured local SQLite path.
- `DIRECT_DATABASE_URL`: direct PostgreSQL connection preferred for Alembic migrations. Online migrations create a separate Psycopg 3 engine from this URL instead of using the application's pooled engine. If it is absent, migrations intentionally fall back to `DATABASE_URL` (which may be pooled); configure the direct URL for production schema changes.
- `PAYSTACK_PUBLIC_KEY` and `PAYSTACK_SECRET_KEY`: optional payment-provider configuration.
- `RECEIPT_STORAGE_BUCKET`, `RECEIPT_STORAGE_REGION`, `RECEIPT_STORAGE_ACCESS_KEY_ID`, and `RECEIPT_STORAGE_SECRET_ACCESS_KEY`: required for manual checkout receipt uploads. `RECEIPT_STORAGE_ENDPOINT_URL` is optional for S3-compatible providers. Configure the bucket to block public access; uploads use server-side AES256 encryption. Checkout fails safely when private storage is not configured.

The application does not create database tables or seed products during web requests. Apply migrations explicitly, then seed the catalog:

```powershell
$env:DATABASE_URL = "sqlite:///database.db"
$env:DIRECT_DATABASE_URL = ""
flask --app app.app db upgrade
flask --app app.app seed-products
```

Set `DATABASE_URL` to the intended database before running these commands. Do not point local tests or exploratory commands at a production database.

### 7. Run the application

The current development entry point is:

```bash
python app/app.py
```

The application currently enables Flask debug mode in its development entry point. Do not use that setting for production deployment.

### 8. Production hosting and environment settings

This project is configured for a Vercel deployment using a serverless Python function. The deployment target is:

- Hosting platform: Vercel
- Runtime: Python 3.12
- Entry point: `api/index.py`
- Framework: Flask app object exported as `app`

Set these environment variables in the Vercel project settings before deployment:

- `APP_ENV=production`
- `PORT=3000` (Vercel manages this automatically for the runtime; keep the app reading from the environment)
- `SECRET_KEY=<long random secret>`
- `DATABASE_URL=<pooled Neon PostgreSQL URL>`
- `DIRECT_DATABASE_URL=<direct Neon PostgreSQL URL>`
- `ADMIN_USERNAME=<admin username>`
- `ADMIN_PASSWORD=<unique long admin password>`
- `PAYSTACK_PUBLIC_KEY` and `PAYSTACK_SECRET_KEY`

The repository includes a `vercel.json` config to route requests to the Flask app exported from `api/index.py`.

Configure the private receipt-storage variables above in Vercel before enabling manual checkout. The app has no public or local-disk receipt-storage fallback. This work does not run a Vercel deployment.

### Admin console

Configure `ADMIN_USERNAME` and `ADMIN_PASSWORD` for the first sign-in to `/admin/login`. Admin dashboard, order/payment review, product management, customer views, and profile settings require an authenticated session. Profile details are stored in the database; the username remains environment-managed. A password changed from Settings is stored as a password hash and becomes the login authority.

Apply database changes with `flask --app app.app db upgrade` against the target database before deploying code that depends on the new schema. Migrations use `DIRECT_DATABASE_URL` when it is set. To reset a changed password to the environment bootstrap value, clear `password_hash` for the configured username in the `admin_profiles` table using a trusted database console. Do not store or paste actual credentials in the repository.

### Customer accounts

Customers can create an account at `/signup`, sign in at `/signin`, and view orders placed while signed in at `/account`. Passwords are stored as hashes and account forms use CSRF tokens. Checkout remains available to guests; orders placed by signed-in customers are associated with their account. Existing guest orders are not automatically attached to a new account based on email alone.

Apply the customer-account migration with `flask --app app.app db upgrade` before deploying this feature. Email verification and password recovery are not currently provided.

### 9. Database backup routine

Create a local scheduled backup using the Neon direct connection string:

```bash
python scripts/backup_neon_db.py
```

This exports the current PostgreSQL schema and data to a timestamped SQL file in the `backups/` folder. For a regular production routine, schedule this command via GitHub Actions, Cron, or your hosting provider's task scheduler, and keep a copy of the generated dumps in object storage or another offsite location.

## Database migration status

The application uses SQLAlchemy models and Alembic migrations for products, orders, payment audit logs, admin profiles, customer accounts, fixed-precision money, and inventory reservations. Apply pending migrations with `flask --app app.app db upgrade` against the intended database; verify the database target and migration results before a production deployment.

The checkout-hardening migration converts legacy floating-point money values to `Numeric(14, 2)`. Before changing schema, it checks product prices, order totals, and order-item prices. It stops with a row-specific message if it finds non-finite values, values with more than two decimal places, or values outside the supported range; reconcile those rows manually and rerun. Do not bypass this check by rounding production data automatically.

Offline SQL generation (`flask --app app.app db upgrade --sql`) is supported and uses the selected migration URL's dialect without opening a database connection. Since offline generation cannot inspect existing tables or execute the money preflight, it assumes the configured Alembic starting revision and prints a warning. Run the money preflight against the target database and verify the schema before applying generated SQL.

### Legacy database upgrade and baseline

The supported pre-Alembic baseline is the application's historical `db.create_all()` schema: the common `products`, `orders`, `order_items`, and `payment_audit_logs` tables from revision `20261112_initial`, optionally already extended with `admin_profiles`, `customers`, `orders.customer_id`, and a 254-character `orders.user_email`. Later admin/customer migrations detect those existing additions; the checkout-hardening migration converts the legacy floating-point money columns and adds inventory tracking.

For a database without `alembic_version`, first make and verify a restorable backup, then rehearse on an isolated copy. Confirm the shared base tables and columns match revision `20261112_initial`; if admin/customer tables or fields already exist, verify their columns, foreign keys, indexes, and unique constraints against the historical application schema as well. These migrations skip already-present objects; they do not repair a partial or structurally different table. Check that all money values are finite, have at most two decimal places, and fit `Numeric(14, 2)`. Only for that verified legacy shape, stamp the **initial baseline** and upgrade:

```powershell
flask --app app.app db stamp 20261112_initial
flask --app app.app db upgrade head
```

Do not stamp a fresh database or use `stamp head` as a general legacy-upgrade procedure. If the schema differs, stop and determine a specific baseline or manual reconciliation before running migrations. If `alembic_version` already contains a revision, do not stamp it; upgrade from its recorded revision.

The automated legacy checks build disposable SQLite databases for both the initial schema and the historical `db.create_all()` shape, populate products, orders, items, and payment audit rows, then stamp the initial baseline and upgrade to head. Run them with:

```powershell
python -m unittest discover -s tests -p test_legacy_migration.py
```

These tests verify data preservation, customer schema, constraints, indexes, fixed-precision columns, and that an invalid legacy amount stops the checkout-hardening migration before it changes money columns or advances the revision. They do not replace a rehearsal on a restorable copy of each real database.

## Payments and security

Manual payment review currently uses the server-side cart and catalog prices, bounded quantities, a database stock reservation transaction, a unique payment reference, and private receipt storage. Admin receipt downloads require an authenticated admin session. Rejected orders release only inventory reserved by this checkout flow.

The Paystack helper is not wired into checkout, so card/online payment initialization and provider verification are not implemented. Email verification and password recovery are also outstanding. Keep both limitations in mind before using customer accounts or payment workflows for higher-risk production use.

Never store secret keys in the repository. Use environment variables and the hosting provider's secret-management settings.

## Tests

Run the local suite after installing `requirements.txt`:

```powershell
python -m unittest discover -s tests
```

PostgreSQL URLs are normalized to SQLAlchemy's `postgresql+psycopg://` driver while preserving URL query parameters such as `sslmode=require`. To run the opt-in PostgreSQL migration test, configure a reachable, disposable PostgreSQL database whose actual name ends in `_test`, and explicitly enable the test:

```powershell
$env:TEST_DATABASE_URL = "postgresql://<test-user>:<test-password>@<test-host>/<database>_test?sslmode=require"
$env:RUN_POSTGRES_MIGRATION_TESTS = "1"
python -m unittest discover -s tests -p test_postgres_migration.py
```

Use only test credentials and a disposable database, never production credentials or the application database. The test refuses a URL matching `DATABASE_URL` or `DIRECT_DATABASE_URL`, creates a uniquely named temporary schema, migrates and verifies that schema, and drops only that exact schema in cleanup; it never drops or resets a database. Setting `RUN_POSTGRES_MIGRATION_TESTS=1` without a valid `TEST_DATABASE_URL` fails clearly. Without the explicit opt-in, this test is skipped.

## Project roadmap

See [TODO.md](TODO.md) for the live development checklist, including the Neon migration and the Nigeria launch payment workflow.

## Contributing

Work on a feature branch, keep changes focused, test affected workflows, and update `TODO.md` whenever project scope or implementation status changes.

## License

No license has been specified yet. All rights remain with the respective copyright holder unless a license is added to this repository.
