"""Module with actual lambda handlers."""

from collections import namedtuple
from functools import wraps
from http import HTTPStatus
from json import dumps, loads
from uuid import uuid4

from .exception import (
    CallbackUrlIsNotValid,
    BlobIsNotUploadedYet,
    BlobUploadTimedOut,
    BlobRecognitionIsInProgress,
    BlobWasNotFound,
    InvalidBlobHasBeenUploaded,
    TooLargeBlobHasBeenUploaded,
    UnexpectedErrorOccurred
)


Response = namedtuple('Response', ['body', 'status_code'])
"""namedtuple: Simple response structure  

Used for passing result from lambda to response formatter.
"""


def with_http_api_response_format(function):
    """Decorator that wraps lambda handler to format its result to match HTTP API spec."""
    @wraps(function)
    def inner(*args, **kwargs):
        """Formats lambda result to match HTTP API spec."""
        response = function(*args, **kwargs)
        return {
            'isBase64Encoded': False,
            'statusCode': response.status_code,
            'headers': {'Content-Type': 'application/json'},
            'body': dumps(response.body)
        }
    return inner


class InitializeUploadListeningHandler:
    """Lambda handler that generates pre-signed url and starts upload listening."""

    def __init__(self, id_generator, initialize_upload_listening):
        self._id_generator = id_generator
        self._initialize_upload_listening = initialize_upload_listening

    @with_http_api_response_format
    def handle(self, event, context):
        blob_id = self._id_generator()
        callback_url = get_callback_url_from_event(event)
        try:
            result = self._initialize_upload_listening(blob_id, callback_url)
        except CallbackUrlIsNotValid as exception:
            return Response(
                body={
                    'description': str(exception),
                    'payload': exception.payload
                },
                status_code=HTTPStatus.BAD_REQUEST.value
            )
        return Response(
            body=result.as_dict(),
            status_code=HTTPStatus.CREATED.value
        )


class CheckUploadingHandler:
    """Lambda handler that moves blob status to the 'not uploaded' one
    if pre-signed url hasn't been used.
    """

    def __init__(self, check_uploading):
        self._check_uploading = check_uploading

    def handle(self, event, context):
        blob_id = event.get('blob_id')
        self._check_uploading(blob_id)


class ImageHasBeenUploadedHandler:
    """Lambda handler that gets triggered when new file appears in the bucket."""

    def __init__(self, start_recognition):
        self._start_recognition = start_recognition

    def handle(self, event, context):
        blob_id = event.get('Records')[0].get('s3').get('object').get('key')
        self._start_recognition(blob_id)


class GetLabelsHandler:
    """Lambda handler that calls Rekognition service and passes result forward.

    Note: This is part of StepFunction.

    """

    def __init__(self, get_labels):
        self._get_labels = get_labels

    def handle(self, event, context):
        blob_id = event.get('blob_id')
        return self._get_labels(blob_id).as_dict()


class TransformLabelsHandler:
    """Lambda handler that normalize labels and passes result forward.

    Note: This is part of StepFunction.

    """

    def __init__(self, transform_labels):
        self._transform_labels = transform_labels

    def handle(self, event, context):
        blob_id = event.get('blob_id')
        labels = event.get('labels')
        return self._transform_labels(blob_id, labels).as_dict()


class SaveLabelsHandler:
    """Lambda handler that saves labels to the DynamoDB and passes result forward.

    Note: This is part of StepFunction.

    """

    def __init__(self, save_labels):
        self._save_labels = save_labels

    def handle(self, event, context):
        blob_id = event.get('blob_id')
        labels = event.get('labels')
        return self._save_labels(blob_id, labels).as_dict()


class InvokeCallbackHandler:
    """Lambda handler that invokes callback with recognition result.

    Note: This is part of StepFunction.

    """
    def __init__(self, invoke_callback):
        self._invoke_callback = invoke_callback

    def handle(self, event, context):
        blob_id = event.get('blob_id')
        labels = event.get('labels')
        return self._invoke_callback(blob_id, labels).as_dict()


class UnexpectedErrorFallbackHandler:
    """Lambda handler that gets triggered when unexpected error occurs
    while performing recognition process.

    Note: This is part of StepFunction.

    """

    def __init__(self, handle_unexpected_error):
        self._handle_unexpected_error = handle_unexpected_error

    def handle(self, event, context):
        blob_id = event.get('ExecutionName')
        if blob_id is None:
            return
        self._handle_unexpected_error(blob_id)


class GetRecognitionResultHandler:
    """Lambda handler that returns recognition result."""

    def __init__(self, get_recognition_result):
        self._get_recognition_result = get_recognition_result

    @with_http_api_response_format
    def handle(self, event, context):
        blob_id = event.get('pathParameters').get('blob_id')
        try:
            result = self._get_recognition_result(blob_id)
        except (
                BlobWasNotFound,
                BlobIsNotUploadedYet,
                BlobUploadTimedOut,
                BlobRecognitionIsInProgress,
                InvalidBlobHasBeenUploaded,
                TooLargeBlobHasBeenUploaded,
                UnexpectedErrorOccurred
        ) as e:
            return Response(
                body={
                    'description': str(e),
                    'payload': e.payload
                },
                status_code=HTTPStatus.NOT_FOUND.value
            )
        return Response(
            body=result.as_dict(),
            status_code=HTTPStatus.OK.value
        )


def uuid_generator():
    return str(uuid4())


def get_callback_url_from_event(event):
    body = loads(event.get('body'))
    return body.get('callback_url', '').strip()
