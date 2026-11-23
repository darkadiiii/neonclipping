"""Cloud Storage Abstraction Layer for NeonClipping:
Supports local disk storage (default) or S3/Cloudflare R2/GCS compatible
object storage when deployed in the cloud.
"""
import os
import shutil
from pathlib import Path

class StorageAdapter:
    def __init__(self, local_data_dir: Path):
        self.local_dir = Path(local_data_dir)
        self.mode = os.environ.get('NEONCLIPPING_STORAGE', 'local').lower()
        self.s3_client = None
        self.bucket = os.environ.get('S3_BUCKET_NAME', '')

        if self.mode in ('s3', 'r2'):
            try:
                import boto3
                endpoint = os.environ.get('S3_ENDPOINT_URL')
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=endpoint,
                    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                    region_name=os.environ.get('AWS_REGION', 'auto')
                )
            except Exception as e:
                print(f"[Warning] S3 storage mode requested but boto3 init failed: {e}. Falling back to local.")
                self.mode = 'local'

    def save_clip(self, file_name: str, src_path: Path) -> str:
        """Saves file to local disk and/or syncs to cloud storage."""
        dest_local = self.local_dir / file_name
        if src_path != dest_local:
            shutil.copy2(src_path, dest_local)

        if self.mode in ('s3', 'r2') and self.s3_client and self.bucket:
            try:
                self.s3_client.upload_file(str(dest_local), self.bucket, f"clips/{file_name}")
                public_cdn = os.environ.get('CDN_BASE_URL', '').rstrip('/')
                if public_cdn:
                    return f"{public_cdn}/clips/{file_name}"
            except Exception as e:
                print(f"[Warning] Cloud sync failed: {e}")

        return f"/media/{Path(file_name).stem}"

    def get_clip_url(self, file_name: str, base_host: str = '') -> str:
        if self.mode in ('s3', 'r2') and os.environ.get('CDN_BASE_URL'):
            return f"{os.environ['CDN_BASE_URL'].rstrip('/')}/clips/{file_name}"
        return f"{base_host.rstrip('/')}/media/{Path(file_name).stem}"

_adapter = None
def get_storage(data_dir: Path) -> StorageAdapter:
    global _adapter
    if _adapter is None:
        _adapter = StorageAdapter(data_dir)
    return _adapter
