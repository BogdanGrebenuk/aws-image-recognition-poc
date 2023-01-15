from marshmallow.exceptions import ValidationError
from marshmallow.validate import URL

from .domain import RecognitionStatus
from .exception import CallbackUrlIsNotValid


class InitializeUploadListening:

    def __init__(
            self,
            blob_s3_client,
            blob_dynamodb_client,
            uploading_step_function_client,
            validator
            ):
        self._blob_s3_client = blob_s3_client
        self._blob_dynamodb_client = blob_dynamodb_client
        self._uploading_step_function_client = uploading_step_function_client
        self._validator = validator

    def __call__(self, blob_id, callback_url):
        self._validate_callback_url(callback_url)
        self._blob_dynamodb_client.create(
            blob_id, callback_url, RecognitionStatus.WAITING_FOR_UPLOAD.value
        )
        self._uploading_step_function_client.launch(blob_id)
        upload_url = self._blob_s3_client.generate_presigned_url(blob_id)

        return upload_url

    def _validate_callback_url(self, url):
        if not self._validator.is_valid_url(url):
            raise CallbackUrlIsNotValid(
                message='Invalid callback url supplied',
                payload={'callback_url': url}
            )


class UrlValidator:

    def __init__(self, schemes=None):
        if schemes is None:
            schemes = ['http', 'https']
        self._validate = URL(schemes=schemes)

    def is_valid_url(self, url):
        try:
            self._validate(url)
            return True
        except ValidationError:
            return False


class CheckUploading:

    def __init__(self, blob_s3_client, blob_dynamodb_client):
        self._blob_s3_client = blob_s3_client
        self._blob_dynamodb_client = blob_dynamodb_client

    def __call__(self, blob_id):
        if self._blob_s3_client.is_uploaded(blob_id):
            return
        self._blob_dynamodb_client.update_status(blob_id, RecognitionStatus.UPLOAD_TIMED_OUT.value)
