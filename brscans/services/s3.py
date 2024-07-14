import boto3
from django.conf import settings


session = boto3.Session()
s3_client = (
    session.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_SESSION_TOKEN,
        region_name=settings.AWS_S3_REGION_NAME,
        endpoint_url=f"https://s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com",
    )
    if settings.USE_S3
    else None
)
