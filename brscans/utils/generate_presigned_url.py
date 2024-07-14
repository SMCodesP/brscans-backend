from django.conf import settings
from brscans.services.s3 import s3_client


def generate_presigned_url(key: str, file: dict):
    response = s3_client.generate_presigned_post(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Fields={"Content-Type": file.get("type", ""), "key": key},
        Conditions=[
            {"Content-Type": file.get("type", "")},
            ["content-length-range", 0, settings.MAX_UPLOAD_SIZE],
        ],
        ExpiresIn=3600,
    )
    return {"url": response["url"], "fields": response["fields"]}
