from __future__ import annotations

from io import BytesIO
import re
import secrets
import warnings
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, ImageOps, UnidentifiedImageError


_PRODUCT_IMAGE_KEY_PATTERN = re.compile(r"^products/[a-f0-9]{32}\.webp$")
MAX_IMAGE_DIMENSION = 6000
MAX_IMAGE_PIXELS = 20_000_000


class ProductImageError(ValueError):
    pass


class ProductImageStorageError(Exception):
    pass


class S3ProductImageStorage:
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        public_base_url: str,
        endpoint_url: str | None = None,
    ):
        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")
        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            endpoint_url=endpoint_url or None,
        )

    def save(self, data: bytes) -> str:
        key = f"products/{secrets.token_hex(16)}.webp"
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType="image/webp",
                CacheControl="public, max-age=31536000, immutable",
            )
        except (BotoCoreError, ClientError) as error:
            raise ProductImageStorageError("Product image storage is unavailable.") from error
        return key

    def delete(self, key: str) -> None:
        if not _PRODUCT_IMAGE_KEY_PATTERN.fullmatch(key or ""):
            raise ProductImageStorageError("The product image reference is invalid.")
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            raise ProductImageStorageError("Product image cleanup failed.") from error

    def public_url(self, key: str) -> str | None:
        if not _PRODUCT_IMAGE_KEY_PATTERN.fullmatch(key or ""):
            return None
        return f"{self.public_base_url}/{key}"


def validate_product_image(file_storage, max_bytes: int) -> bytes:
    if file_storage is None:
        raise ProductImageError("Choose a product image to upload.")

    data = file_storage.stream.read(max_bytes + 1)
    if not data:
        raise ProductImageError("The selected product image is empty.")
    if len(data) > max_bytes:
        raise ProductImageError("Product images must be 4 MB or smaller.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(data))
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ProductImageError("Use a JPEG, PNG, or WebP product image.")
            if (
                image.width > MAX_IMAGE_DIMENSION
                or image.height > MAX_IMAGE_DIMENSION
                or image.width * image.height > MAX_IMAGE_PIXELS
            ):
                raise ProductImageError("The image dimensions are too large.")
            image.load()
            image = ImageOps.exif_transpose(image)
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            image = image.convert("RGBA" if has_alpha else "RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=86, method=5)
    except ProductImageError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        raise ProductImageError("The selected file is not a valid, readable image.") from error

    return output.getvalue()


def create_product_image_storage(config):
    values = (
        config.get("PRODUCT_IMAGE_STORAGE_BUCKET"),
        config.get("PRODUCT_IMAGE_STORAGE_REGION"),
        config.get("PRODUCT_IMAGE_STORAGE_ACCESS_KEY_ID"),
        config.get("PRODUCT_IMAGE_STORAGE_SECRET_ACCESS_KEY"),
        config.get("PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL"),
    )
    if not all(values):
        return None

    parsed = urlsplit(values[4])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError(
            "PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL must be a public HTTPS URL."
        )

    return S3ProductImageStorage(
        bucket=values[0],
        region=values[1],
        access_key_id=values[2],
        secret_access_key=values[3],
        public_base_url=values[4],
        endpoint_url=config.get("PRODUCT_IMAGE_STORAGE_ENDPOINT_URL"),
    )
