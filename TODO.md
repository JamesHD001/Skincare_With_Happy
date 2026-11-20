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

## Two-stage checkout and delivery
- [x] Stage payment reference and validated receipt privately without creating an order or deducting inventory.
- [x] Add a second checkout stage for recipient and delivery details, with server-side validation and CSRF protection.
- [x] Preserve staged receipt and cart when delivery validation or stock checks fail; expire drafts after two hours and clean up expired receipts when encountered.
- [x] Save editable delivery details for signed-in customers while keeping guest checkout account-free.
- [x] Store an immutable delivery-details snapshot on each order.
- [x] Build a customer-friendly confirmation page with order number, payment status, delivery summary, and next steps.
- [x] Add tests for payment-stage separation, invalid delivery retry, duplicate payment references, stock conflicts, guest checkout, invalid email addresses, signed-in saved-address persistence, immutable order snapshots, and expired receipt cleanup.
- [x] Add signed-in saved-address persistence and immutable-snapshot tests, plus explicit expired-receipt cleanup tests.
- [x] Update README checkout documentation after implementation.
- [ ] Add reliable scheduled cleanup for abandoned staged receipts; current cleanup is opportunistic when an expired draft is revisited.
- [x] Exercise the migration chain against disposable SQLite databases in the automated legacy-schema upgrade tests; verify the new delivery columns and preservation of legacy orders.
- [x] Verify checkout stages, delivery validation, guest/signed-in flows, saved-address persistence, and immutable order snapshots through the automated test suite (62 tests passed in GitHub Actions run #20).
- [ ] Perform a browser-based checkout walkthrough against a local development database before merging; do not run production migrations.

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

## Storefront catalog, images, and footer
- [x] Add nullable product image references and a migration assigning original built-in illustrations only to known seeded products with no existing image.
- [x] Add separate optional S3-compatible product-image storage with content validation, WebP normalization, generated object keys, and safe replacement/removal ordering.
- [x] Add authenticated, CSRF-protected admin image upload, replacement, and removal controls.
- [x] Add live client-side previews for newly selected product images in both add-product and replace-image forms.
- [x] Require a valid product image before creating a new catalog product in both the admin form and server-side validation.
- [x] Replace hard-coded homepage and catalog products with database-backed listings and shared responsive product cards.
- [x] Build shop and catalog skin-type filters and category links from the product data.
- [x] Use the active `product_details.html` route template and remove unused conflicting product-detail and filter templates.
- [x] Restore the reference four-column footer layout, forest-green styling, and responsive spacing.
- [x] Remove repeated Shop, About, Contact, and Privacy links from the footer bottom row; retain the copyright line.
- [x] Replace the shared footer across storefront and information pages; show contact and social links only when configured.
- [x] Keep newsletter subscriptions clearly unavailable until a real subscription workflow exists.
- [x] Add product image validation, admin storage lifecycle, catalog rendering, and legacy migration preservation tests.
- [ ] Configure a separate public product-image bucket/CDN and credentials in each deployment environment before enabling uploads.
- [ ] Apply migration `20261114_product_images` to intended deployment databases after verifying the target and backup.

## Second-round security and migration corrections
- [x] Require a unique, sufficiently long production `SECRET_KEY`; reject missing and known insecure values without logging the secret.
- [x] Make online Alembic migrations use `DIRECT_DATABASE_URL`, with an intentional `DATABASE_URL` fallback, and normalize conventional PostgreSQL URLs to Psycopg 3.
- [x] Normalize PostgreSQL test URLs, preserve connection options, and isolate the opt-in migration test in a disposable schema with targeted cleanup.
- [x] Add temporary SQLite upgrade tests for both the initial legacy baseline and the historical `db.create_all()` schema, including data preservation and migration preflight failure behavior.
- [x] Preserve offline Alembic SQL generation and warn that offline output cannot run schema checks or the money preflight.
- [x] Document the tested legacy baseline, the manual backup/rehearsal procedure, and PostgreSQL test setup in `README.md`.
- [x] Run the complete local suite after the migration corrections: 50 passed, 1 skipped (51 total); the opt-in PostgreSQL migration test was skipped because no disposable PostgreSQL database was configured.
- [ ] Run the fresh PostgreSQL migration test against a disposable PostgreSQL database; it has not been run unless explicitly configured.
- [ ] Rehearse the legacy migration procedure on a restorable copy of each real database before applying migrations to that database.
- [ ] Apply pending migrations to intended deployment databases only after reviewing the data preflight and verifying the direct migration connection.

## Landing page and storefront experience
- [x] Replace the basic homepage with a premium and clinical editorial-style landing page.
- [x] Add responsive hero, brand philosophy, skin-type discovery, skincare education, routine guidance, featured products, trust values, and final shop call to action.
- [x] Keep featured products connected to the existing database and shared product-card component.
- [x] Limit homepage featured products to the first four catalogue entries.
- [x] Make the shared logo and Home navigation link return to the landing page.
- [x] Remove the default underline from the shared header logo link.
- [x] Improve mobile navigation accessibility and prevent missing page-specific controls from breaking shared JavaScript.
- [x] Give the shop a dedicated catalogue introduction rather than repeating the landing-page hero.
- [x] Add a five-slide editorial skincare hero carousel with automatic seven-second transitions, underscore indicators, and reduced-motion support.
- [x] Ensure all hero slides preload so hidden slides are ready when the carousel advances.
- [x] Keep automatic slide rotation enabled for reduced-motion users while disabling fade animations.
- [x] Remove manual slide controls, slide numbering, and the redundant circular brand stamp from the hero.
- [x] Add direct All products, Dry skin, and Oily skin discovery links.
- [x] Include all-skin-type products in specific skin-type catalogue results.
- [x] Add background add-to-cart requests and a shared live cart quantity indicator.
- [x] Rename basket-facing customer copy to Cart.
- [x] Reorder the mobile header so Cart appears before the hamburger menu.
- [x] Move the Account link into the navigation menu so it is not shown as a separate mobile header button.
- [x] Stack the mobile hero carousel above its headline and supporting copy, with clear spacing between sections.
- [ ] Verify the new landing page and shop locally at desktop, tablet, and mobile widths.
- [ ] Confirm featured product cards, add-to-cart, product details, account, and checkout still work end to end.
- [ ] Review editorial image loading and replace temporary remote imagery with approved brand photography when available.
- [ ] Build a real treatment/service management workflow only if the business confirms the treatments it offers.

Email verification and customer password recovery remain incomplete. Do not treat the second-round corrections or SQLite migration tests as evidence of production readiness.

### Automated verification
- [x] Remove a stray syntax fragment found during the checkout-route audit that would prevent `app/app.py` from importing.
- [x] Add a GitHub Actions workflow to run the Python unittest suite on pushes to the checkout feature branch and relevant pull requests.
- [x] Diagnose the zero-job workflow failure: GitHub identified a YAML syntax error at line 23 of `.github/workflows/tests.yml`.
- [x] Quote the SQLite in-memory database URL in the workflow environment to address the reported YAML parsing error.
- [x] Confirm the workflow creates a job and reaches the Python test command.
- [x] Update legacy customer-account checkout tests to submit delivery details as the second stage.
- [x] Update migration-head expectations for `20261118_delivery_details`.
- [x] Correct the expired-draft test to reassign the nested session draft so Flask persists the expiry change.
- [x] Align the shop filter test with the intended inclusion of all-skin-type products.
- [x] Update the admin product-creation test to provide the now-required product image.
- [x] Confirm the checkout suite passes: all 62 tests passed in GitHub Actions run #20.
- [x] Add migration assertions for all saved-address and order-snapshot columns, nullable legacy snapshots, and preservation of existing orders.
- [x] Confirm the expanded migration assertions pass in GitHub Actions run #23 and the latest branch state passes in run #24.


## Copilot audit remediation

### Phase 1: baseline security hardening
- [x] Move Flask development-server debug mode to explicit environment configuration and refuse DEBUG=true in production.
- [x] Add baseline response security headers: content-type protection, frame denial, referrer policy, permissions policy, and CSP frame-ancestors.
- [x] Enable HSTS only for production responses.
- [x] Confirm receipt uploads already request server-side AES256 encryption in the S3 put_object call; no duplicate change needed.
- [ ] Add automated tests for production DEBUG rejection and security response headers.
- [ ] Add login, signup, and recovery rate limiting with a shared production-safe store.

### Remaining audit phases
- [ ] Implement an idempotent timeout policy for awaiting-verification orders and release reserved inventory safely.
- [ ] Add reliable scheduled cleanup for expired checkout drafts and abandoned receipt objects.
- [ ] Add private receipt-bucket configuration/preflight checks for every deployment environment.
- [ ] Add the missing skin quiz template or remove the route if the quiz is no longer part of the product.
- [ ] Replace naive UTC model timestamps with timezone-aware UTC values and plan a compatible migration if needed.
- [ ] Complete email verification and single-use, expiring password recovery.
- [ ] Add pagination to admin orders, customers, and product catalog views.
- [ ] Add indexes for common payment-status and creation-date filters after query-plan review.
- [ ] Consolidate duplicate catalog routes without breaking existing URLs.
- [ ] Review unused Paystack configuration/helper code and retain it only if card payments are on the near-term roadmap.
- [ ] Align dependency pins and Python runtime across local development, CI, and Vercel.
- [ ] Expand PostgreSQL migration tests to verify the full migration chain through head.
- [ ] Add upload and desktop/tablet/mobile checkout integration coverage.
- [ ] Introduce structured, request-correlated application logging and startup health checks.
- [ ] Split app routes into focused Flask blueprints and extract checkout/payment/storage services incrementally.
- [ ] Document backup retention, restore drills, rollback steps, and operational alerts.
- [ ] Verify repository hygiene for virtual environments, database files, backups, and Python cache artifacts.
- [ ] Complete a local browser walkthrough before merging; keep production migrations and deployment separately approved.
