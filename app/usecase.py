import requests.exceptions
from marshmallow.exceptions import ValidationError
from marshmallow.validate import URL

from .domain import RecognitionStatus
from .dto import UploadInitializingResult, RecognitionStepFunctionResult, BlobRecognitionResult
from .exception import CallbackUrlIsNotValid, BlobWasNotFound, BlobIsNotUploadedYet, BlobUploadTimedOut, \
    BlobRecognitionIsInProgress


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

        return UploadInitializingResult(
            blob_id=blob_id,
            upload_url=upload_url,
            callback_url=callback_url
        )

    def _validate_callback_url(self, url):
        if not self._validator.is_valid_url(url):
            raise CallbackUrlIsNotValid(
                message='Invalid callback url supplied.',
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


class StartRecognition:

    def __init__(
            self,
            recognition_step_function_client,
            blob_dynamodb_client
            ):
        self._recognition_step_function_client = recognition_step_function_client
        self._blob_dynamodb_client = blob_dynamodb_client

    def __call__(self, blob_id):
        self._blob_dynamodb_client.update_status(blob_id, RecognitionStatus.IN_PROGRESS.value)
        self._recognition_step_function_client.launch(blob_id)


class GetLabels:

    def __init__(self, blob_rekognition_client):
        self._blob_rekognition_client = blob_rekognition_client

    def __call__(self, blob_id):
        return RecognitionStepFunctionResult(
            blob_id=blob_id,
            labels=self._blob_rekognition_client.detect_labels(blob_id)
        )


class TransformLabels:

    def __call__(self, blob_id, raw_labels_data):
        return RecognitionStepFunctionResult(
            blob_id=blob_id,
            labels=self._transform(raw_labels_data)
        )

    def _transform(self, raw_labels_data):
        labels = raw_labels_data.get('Labels')
        return [
            {
                'label': label.get('Name', ''),
                'confidence': label.get('Confidence', ''),
                'parents': [parent.get('Name', '') for parent in label.get('Parents', {})]
            }
            for label in labels
        ]


class SaveLabels:

    def __init__(self, blob_dynamodb_client):
        self._blob_dynamodb_client = blob_dynamodb_client

    def __call__(self, blob_id, labels):
        self._blob_dynamodb_client.save_labels(blob_id, labels)
        return RecognitionStepFunctionResult(
            blob_id=blob_id,
            labels=labels
        )


class InvokeCallback:

    def __init__(self, blob_dynamodb_client, invoker):
        self._blob_dynamodb_client = blob_dynamodb_client
        self._invoker = invoker

    def __call__(self, blob_id, labels):
        blob = self._blob_dynamodb_client.get_blob(blob_id)
        callback_url = blob.get('callback_url')
        data_to_send = BlobRecognitionResult(
            blob_id=blob_id,
            labels=labels
        )
        status = self._invoker.invoke(callback_url, data_to_send.as_dict())
        if status == self._invoker.SUCCESS:
            self._blob_dynamodb_client.update_status(blob_id, RecognitionStatus.SUCCESS.value)
        elif status == self._invoker.CALLBACK_FAILURE:
            self._blob_dynamodb_client.update_status(blob_id, RecognitionStatus.FAILED_DUE_TO_CALLBACK_FAILURE.value)
        elif status == self._invoker.CONNECTION_TIMEOUT:
            self._blob_dynamodb_client.update_status(blob_id, RecognitionStatus.FAILED_DUE_TO_CALLBACK_TIME_OUT.value)
        elif status == self._invoker.CONNECTION_ERROR:
            self._blob_dynamodb_client.update_status(blob_id, RecognitionStatus.FAILED_DUE_TO_CALLBACK_CONNECTION.value)
        return RecognitionStepFunctionResult(
            blob_id=blob_id,
            labels=labels
        )


class Invoker:

    SUCCESS = 0
    CALLBACK_FAILURE = 1
    CONNECTION_TIMEOUT = 2
    CONNECTION_ERROR = 3

    def __init__(self, http_invoke, timeout):
        self._http_invoke = http_invoke
        self._timeout = timeout

    def invoke(self, url, data):
        try:
            response = self._http_invoke(url, json=data, timeout=self._timeout)
            if response.status_code == 204:
                return self.SUCCESS
            return self.CALLBACK_FAILURE
        except requests.exceptions.ConnectTimeout:
            return self.CONNECTION_TIMEOUT
        except requests.exceptions.ConnectionError:
            return self.CONNECTION_ERROR


class GetRecognitionResult:

    def __init__(self, blob_dynamodb_client):
        self._blob_dynamodb_client = blob_dynamodb_client

    def __call__(self, blob_id):
        blob = self._blob_dynamodb_client.get_blob(blob_id)
        if blob is None:
            raise BlobWasNotFound(
                message='Blob not found.',
                payload={'blob_id': blob_id, 'status': RecognitionStatus.NOT_FOUND.value}
            )
        status = blob.get('status')
        if status == RecognitionStatus.WAITING_FOR_UPLOAD.value:
            raise BlobIsNotUploadedYet(
                message='Blob hasn\'t been uploaded yet.',
                payload={'blob_id': blob_id, 'status': status}
            )
        elif status == RecognitionStatus.UPLOAD_TIMED_OUT.value:
            raise BlobUploadTimedOut(
                message='Blob upload is timed out.',
                payload={'blob_id': blob_id, 'status': status}
            )
        elif status == RecognitionStatus.IN_PROGRESS.value:
            raise BlobRecognitionIsInProgress(
                message='Recognition is in progress.',
                payload={'blob_id': blob_id, 'status': status}
            )
        return BlobRecognitionResult(
            blob_id=blob_id,
            labels=blob.get('labels')
        )
