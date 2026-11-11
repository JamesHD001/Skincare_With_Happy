# SkinCareWithHappy

SkinCareWithHappy is a Flask-based skincare storefront project. It provides a web interface for browsing skincare products, learning about skincare, viewing product details, managing a shopping cart, and starting a checkout flow.

> **Project status:** Active development. The application is currently built around Flask, Jinja templates, and SQLite. A Neon PostgreSQL foundation has been added, but the application routes have **not yet been migrated** from SQLite to PostgreSQL. Do not treat the PostgreSQL setup as a completed database migration.

## Current technology

- **Backend:** Python and Flask
- **Templating:** Jinja2
- **Database in current routes:** SQLite through Python's `sqlite3` module
- **ORM groundwork:** Flask-SQLAlchemy is listed in the dependencies; model definitions need repair and integration
- **Payment groundwork:** Paystack helper functions are present, but the checkout flow still needs secure server-side payment initialization and verification
- **Configuration:** `python-dotenv` and environment variables
- **PostgreSQL target:** Neon PostgreSQL

## Current application areas

The Flask application currently defines routes for:

- Home, shop, about, contact, and skincare learning pages
- Product listing and skin-type filtering
- Product detail pages
- Shopping cart add, update, and remove actions
- Checkout and payment-result pages
- An admin dashboard page

Some routes and templates still need to be aligned, and the application has not yet received a complete security and production-readiness review. The presence of a page or helper function does not mean its full workflow is production-ready.

## Repository structure

```text
SkinCare_With_Happy/
├── app/
│   ├── app.py             # Flask application and routes
│   ├── config.py          # Environment-based configuration
│   ├── models.py          # SQLAlchemy model groundwork
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

Set the values in `.env` locally. Never commit `.env` or paste database passwords and payment secrets into source files, screenshots, issues, or chat messages.

- `SECRET_KEY`: set a long, random secret for Flask sessions.
- `DATABASE_URL`: reserved for the Neon pooled PostgreSQL connection.
- `DIRECT_DATABASE_URL`: reserved for direct database access used by migrations and administrative tasks.
- `PAYSTACK_PUBLIC_KEY` and `PAYSTACK_SECRET_KEY`: optional payment-provider configuration.

**Important:** the current Flask routes still connect through the SQLite helper in `app/app.py`. Setting `DATABASE_URL` alone does not switch the application to Neon. The SQLite schema/initialization workflow also needs to be documented and standardized before a clean local setup can be considered complete.

### 7. Run the application

The current development entry point is:

```bash
python app/app.py
```

The application currently enables Flask debug mode in its development entry point. Do not use that setting for production deployment.

## Database migration status

The Neon PostgreSQL project and environment-variable placeholders have been prepared. The remaining work includes:

1. Add and pin a PostgreSQL driver.
2. Repair the SQLAlchemy model definitions.
3. Configure Flask-SQLAlchemy correctly.
4. Design and apply database migrations.
5. Replace SQLite-specific queries and placeholders with PostgreSQL-compatible database access.
6. Test product, cart, order, and payment-related database operations.
7. Establish backup and recovery procedures.

Until those steps are complete, SQLite remains the database used by the application routes.

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
