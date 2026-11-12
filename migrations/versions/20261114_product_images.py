"""Add product image references.

Revision ID: 20261114_product_images
Revises: 20261113_checkout_hardening
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20261114_product_images"
down_revision = "20261113_checkout_hardening"
branch_labels = None
depends_on = None

BUILT_IN_IMAGES = {
    "niacinamide-balancing-serum": "builtin/niacinamide-balancing-serum.svg",
    "gentle-cream-cleanser": "builtin/gentle-cream-cleanser.svg",
    "vitamin-c-glow-essence": "builtin/vitamin-c-glow-essence.svg",
    "hydrating-barrier-cream": "builtin/hydrating-barrier-cream.svg",
}


def upgrade() -> None:
    op.add_column("products", sa.Column("image_key", sa.String(length=255), nullable=True))
    bind = op.get_bind()
    for slug, image_key in BUILT_IN_IMAGES.items():
        bind.execute(
            sa.text(
                "UPDATE products SET image_key = :image_key "
                "WHERE slug = :slug AND image_key IS NULL"
            ),
            {"image_key": image_key, "slug": slug},
        )


def downgrade() -> None:
    op.drop_column("products", "image_key")
