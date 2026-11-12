# SkinCareWithHappy

SkinCareWithHappy is a Flask-based skincare storefront project. It provides a web interface for browsing skincare products, learning about skincare, viewing product details, managing a shopping cart, and starting a checkout flow.

> **Project status:** Active development. The application uses Flask, Jinja templates, SQLAlchemy, and Alembic migrations, with Neon PostgreSQL configuration and a SQLite local-development fallback. The storefront supports manual payment review, a protected admin console, and customer accounts. Vercel is the deployment target.

## Current technology

- **Backend:** Python and Flask
- **Templating:** Jinja2
- **Database:** Flask-SQLAlchemy with Alembic migrations; Neon PostgreSQL is supported
- **Payments:** Manual transfer/OPay submission with receipt and reference review by an administrator
- **Customer accounts:** CSRF-protected sign-up/sign-in, guest checkout, and signed-in order history
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

Set the values in the project-root `.env` locally; `.env.example` is a template only and is never loaded by the app. Existing process/Vercel environment variables take precedence. Never commit `.env` or paste database passwords and payment secrets into source files, screenshots, issues, or chat messages.

- `SECRET_KEY`: set a long, random secret for Flask sessions.
- `ADMIN_USERNAME` and `ADMIN_PASSWORD`: bootstrap credentials for the protected admin console. Use unique credentials and keep them only in local/Vercel environment settings.
- `DATABASE_URL`: Neon pooled PostgreSQL connection; when unset, the app uses the configured local SQLite path.
- `DIRECT_DATABASE_URL`: direct database connection used by migrations and administrative tasks.
- `PAYSTACK_PUBLIC_KEY` and `PAYSTACK_SECRET_KEY`: optional payment-provider configuration.

Run `flask --app app.app db upgrade` after configuring the target database and before deploying code that depends on a new schema. The application creates missing tables for local development, but production schema changes should be applied through migrations.

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

The application uses SQLAlchemy models and Alembic migrations for products, orders, payment audit logs, admin profiles, and customer accounts. Configure `DATABASE_URL` for Neon PostgreSQL or use the SQLite fallback locally. Apply pending migrations with `flask --app app.app db upgrade`; verify connection values and migration results before a production deployment.

For a legacy database already populated by `db.create_all()` but missing `alembic_version`, first verify that its tables match the initial migration, then run `flask --app app.app db stamp 20261112_initial` once and `flask --app app.app db upgrade`. Do not stamp a fresh or structurally different database.

## Payments and security

Payment processing is not production-ready. Before accepting real payments, the project must:

- Calculate order totals on the server using trusted product prices.
- Validate cart items and quantities on the server.
- Initialize payment transactions securely on the server.
- Verify payment status with the payment provider before marking an order as paid.
- Validate payment references and prevent duplicate or forged order submissions.
- Protect administrative routes with authentication and authorization.
- Keep payment status separate from order fulfillment status.
- Validate and safely store any payment evidence if manual transfer payments are introduced.

Never store secret keys in the repository. Use environment variables and the hosting provider's secret-management settings.

## Project roadmap

See [TODO.md](TODO.md) for the live development checklist, including the Neon migration and the Nigeria launch payment workflow.

## Contributing

Work on a feature branch, keep changes focused, test affected workflows, and update `TODO.md` whenever project scope or implementation status changes.

## License

No license has been specified yet. All rights remain with the respective copyright holder unless a license is added to this repository.
