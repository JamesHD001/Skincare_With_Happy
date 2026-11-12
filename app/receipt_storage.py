from __future__ import annotations

import re
import secrets

import boto3
from botocore.exceptions import BotoCoreError, ClientError


_RECEIPT_KEY_PATTERN = re.compile(r"^receipts/[a-f0-9]{32}\.(?:png|jpg|webp|pdf)$")


class ReceiptStorageError(Exception):
    pass


class ReceiptNotFound(ReceiptStorageError):
    pass


class S3ReceiptStorage:
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str | None = None,
    ):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            endpoint_url=endpoint_url or None,
        )

    def save(self, data: bytes, extension: str, content_type: str) -> str:
        key = f"receipts/{secrets.token_hex(16)}.{extension}"
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ContentDisposition="attachment",
                ServerSideEncryption="AES256",
            )
        except (BotoCoreError, ClientError) as error:
            raise ReceiptStorageError("Private receipt storage is unavailable.") from error
        return key

    def read(self, key: str, max_bytes: int) -> bytes:
        if not _RECEIPT_KEY_PATTERN.fullmatch(key):
            raise ReceiptNotFound("Receipt not found.")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            if response.get("ContentLength", max_bytes + 1) > max_bytes:
                response["Body"].close()
                raise ReceiptStorageError("Stored receipt exceeds the permitted size.")
            body = response["Body"]
            try:
                data = body.read(max_bytes + 1)
            finally:
                body.close()
            if not data or len(data) > max_bytes:
                raise ReceiptStorageError("Stored receipt is empty or exceeds the permitted size.")
            return data
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "NotFound", "404"}:
                raise ReceiptNotFound("Receipt not found.") from error
            raise ReceiptStorageError("Private receipt storage is unavailable.") from error
        except BotoCoreError as error:
            raise ReceiptStorageError("Private receipt storage is unavailable.") from error

    def delete(self, key: str) -> None:
        if not _RECEIPT_KEY_PATTERN.fullmatch(key):
            return
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            raise ReceiptStorageError("Unable to clean up an unused receipt.") from error


def create_receipt_storage(config):
    values = (
        config.get("RECEIPT_STORAGE_BUCKET"),
        config.get("RECEIPT_STORAGE_REGION"),
        config.get("RECEIPT_STORAGE_ACCESS_KEY_ID"),
        config.get("RECEIPT_STORAGE_SECRET_ACCESS_KEY"),
    )
    if not all(values):
        return None
    return S3ReceiptStorage(
        bucket=values[0],
        region=values[1],
        access_key_id=values[2],
        secret_access_key=values[3],
        endpoint_url=config.get("RECEIPT_STORAGE_ENDPOINT_URL"),
    )
