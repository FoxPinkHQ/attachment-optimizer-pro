import hashlib
import logging

from odoo import _

from odoo.addons.attachment_optimizer.services.s3_bridge import (
    S3Bridge,
    S3BridgeError,
)

_logger = logging.getLogger(__name__)


class ProS3Bridge(S3Bridge):
    """S3 bridge extended for multi-bucket routing, server-side encryption,
    object deletion and provider-to-provider copy."""

    def _bucket_config(self, bucket_name):
        bucket = self.env['attachment.storage.bucket'].search(
            [('name', '=', bucket_name)], limit=1,
        )
        if bucket:
            return bucket._s3_config()
        return dict(self._get_config(), sse='none')

    def _client_config(self, bucket, config=None):
        if config is not None:
            return config
        return self._bucket_config(bucket)

    def _get_client(self, config=None):
        cfg = config if config is not None else self._get_config()
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise S3BridgeError(_('boto3 is not installed'))
        params = {
            'aws_access_key_id': cfg.get('access_key_id'),
            'aws_secret_access_key': cfg.get('secret_access_key'),
            'region_name': cfg.get('region') or 'us-east-1',
            'config': Config(
                connect_timeout=2,
                read_timeout=5,
                retries={'max_attempts': 1, 'mode': 'standard'},
            ),
        }
        if cfg.get('endpoint_url'):
            params['endpoint_url'] = cfg['endpoint_url']
        try:
            return boto3.client('s3', **params)
        except Exception as e:
            raise S3BridgeError(_('Failed to create S3 client: %s') % str(e))

    def _put_kwargs(self, config=None):
        sse = (config or {}).get('sse')
        if sse == 'aes256':
            return {'ServerSideEncryption': 'AES256'}
        return {}

    def head(self, bucket, key, config=None):
        cfg = self._client_config(bucket, config)

        def _do_head():
            self._get_client(cfg).head_object(Bucket=bucket, Key=key)
            return True

        try:
            return self._retry_call(_do_head)
        except S3BridgeError:
            return False

    def upload(self, bucket, key, data, checksum=None, config=None):
        cfg = self._client_config(bucket, config)

        def _do_upload():
            self._get_client(cfg).put_object(
                Bucket=bucket, Key=key, Body=data, **self._put_kwargs(cfg),
            )

        self._retry_call(_do_upload)
        if checksum:
            return self.verify(bucket, key, checksum, config=cfg)
        return True

    def verify(self, bucket, key, expected_checksum, config=None):
        cfg = self._client_config(bucket, config)

        def _do_verify():
            obj = self._get_client(cfg).get_object(Bucket=bucket, Key=key)
            actual = hashlib.sha256(obj['Body'].read()).hexdigest()
            return actual == expected_checksum

        return self._retry_call(_do_verify)

    def get_object(self, bucket, key, config=None):
        cfg = self._client_config(bucket, config)
        try:
            obj = self._get_client(cfg).get_object(Bucket=bucket, Key=key)
            return obj['Body'].read()
        except S3BridgeError:
            raise
        except Exception as e:
            raise S3BridgeError(_('S3 read failed: %s') % str(e))

    def delete_object(self, bucket, key, config=None):
        cfg = self._client_config(bucket, config)

        def _do_delete():
            self._get_client(cfg).delete_object(Bucket=bucket, Key=key)

        self._retry_call(_do_delete)

    def copy_object(self, src_bucket, src_key, dst_bucket, dst_key,
                    src_config=None, dst_config=None):
        """Provider-to-provider copy with end-to-end checksum verification.

        Data flows through Odoo so the copy is verified on the destination
        before it is considered complete. The source object is never removed.
        """
        src_cfg = self._client_config(src_bucket, src_config)
        dst_cfg = self._client_config(dst_bucket, dst_config)
        data = self.get_object(src_bucket, src_key, config=src_cfg)
        checksum = hashlib.sha256(data).hexdigest()
        self.upload(dst_bucket, dst_key, data, checksum=checksum, config=dst_cfg)
        return checksum
