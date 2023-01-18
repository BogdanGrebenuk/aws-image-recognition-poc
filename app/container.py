"""Module with DI configuration."""

import os

import boto3
import requests

from .client import (
    BlobS3Client,
    BlobDynamoDBClient,
    BlobStepFunctionClient,
    BlobRekognitionClient
)
from .lambdas import (
    CheckUploadingHandler,
    ImageHasBeenUploadedHandler,
    GetLabelsHandler,
    TransformLabelsHandler,
    SaveLabelsHandler,
    InvokeCallbackHandler,
    GetRecognitionResultHandler,
    uuid_generator,
    InitializeUploadListeningHandler,
    UnexpectedErrorFallbackHandler
)
from .usecase import (
    UrlValidator,
    InitializeUploadListening,
    CheckUploading,
    StartRecognition,
    GetLabels,
    TransformLabels,
    SaveLabels,
    InvokeCallback,
    Invoker,
    GetRecognitionResult,
    HandleUnexpectedError
)


BLOBS_BUCKET_NAME = os.environ.get('blobsBucketName')
BLOBS_TABLE_NAME = os.environ.get('blobsTableName')
PRESIGNED_URL_TTL = os.environ.get('presignedUrlTTL', 30)
UPLOADING_WAITING_TIME = os.environ.get('uploadingWaitingTime')
UPLOADING_STEP_FUNCTION_ARN = os.environ.get('uploadingStepFunctionArn')
RECOGNITION_STEP_FUNCTION_ARN = os.environ.get('recognitionStepFunctionArn')
MAX_LABELS = os.environ.get('maxLabels', 10)
MIN_CONFIDENCE = os.environ.get('minConfidence', 50)
CALLBACK_TIMEOUT = os.environ.get('callbackTimeout', 10)


class Container:

    def __init__(self, *, testing_mode=False):
        """Container initializer.

        Args:
            testing_mode (bool): Whether container should be set up in testing mode or not.

        """
        if testing_mode:
            s3_client = object()
            dynamodb_client = object()
            rekognition_client = object()
            step_function_client = object()
        else:
            s3_client = boto3.client('s3')
            dynamodb_client = boto3.client('dynamodb')
            rekognition_client = boto3.client('rekognition')
            step_function_client = boto3.client('stepfunctions')

        # clients

        self.blob_s3_client = BlobS3Client(
            client=s3_client,
            bucket_name=BLOBS_BUCKET_NAME,
            ttl=int(PRESIGNED_URL_TTL)
        )

        self.blob_dynamodb_client = BlobDynamoDBClient(
            client=dynamodb_client,
            table_name=BLOBS_TABLE_NAME
        )

        self.uploading_step_function_client = BlobStepFunctionClient(
            client=step_function_client,
            state_machine_arn=UPLOADING_STEP_FUNCTION_ARN
        )

        self.recognition_step_function_client = BlobStepFunctionClient(
            client=step_function_client,
            state_machine_arn=RECOGNITION_STEP_FUNCTION_ARN
        )

        self.blob_rekognition_client = BlobRekognitionClient(
            client=rekognition_client,
            bucket_name=BLOBS_BUCKET_NAME,
            max_labels=int(MAX_LABELS),
            min_confidence=int(MIN_CONFIDENCE)
        )

        # services

        self.url_validator = UrlValidator()

        self.invoker = Invoker(
            http_invoke=requests.post,
            timeout=int(CALLBACK_TIMEOUT)
        )

        # use cases

        self.initialize_upload_listening = InitializeUploadListening(
            blob_s3_client=self.blob_s3_client,
            blob_dynamodb_client=self.blob_dynamodb_client,
            uploading_step_function_client=self.uploading_step_function_client,
            validator=self.url_validator
        )

        self.check_uploading = CheckUploading(
            blob_s3_client=self.blob_s3_client,
            blob_dynamodb_client=self.blob_dynamodb_client
        )

        self.start_recognition = StartRecognition(
            recognition_step_function_client=self.recognition_step_function_client,
            blob_dynamodb_client=self.blob_dynamodb_client
        )

        self.get_labels = GetLabels(
            blob_rekognition_client=self.blob_rekognition_client,
            blob_dynamodb_client=self.blob_dynamodb_client
        )

        self.transform_labels = TransformLabels()

        self.save_labels = SaveLabels(
            blob_dynamodb_client=self.blob_dynamodb_client
        )

        self.invoke_callback = InvokeCallback(
            blob_dynamodb_client=self.blob_dynamodb_client,
            invoker=self.invoker
        )

        self.handle_unexpected_error = HandleUnexpectedError(
            blob_dynamodb_client=self.blob_dynamodb_client
        )

        self.get_recognition_result = GetRecognitionResult(
            blob_dynamodb_client=self.blob_dynamodb_client
        )

        # lambdas

        self.initialize_upload_listening_handler = InitializeUploadListeningHandler(
            id_generator=uuid_generator,
            initialize_upload_listening=self.initialize_upload_listening
        )

        self.check_uploading_handler = CheckUploadingHandler(
            check_uploading=self.check_uploading
        )

        self.image_has_been_uploaded_handler = ImageHasBeenUploadedHandler(
            start_recognition=self.start_recognition
        )

        self.get_labels_handler = GetLabelsHandler(
            get_labels=self.get_labels
        )

        self.transform_labels_handler = TransformLabelsHandler(
            transform_labels=self.transform_labels
        )

        self.save_labels_handler = SaveLabelsHandler(
            save_labels=self.save_labels
        )

        self.invoke_callback_handler = InvokeCallbackHandler(
            invoke_callback=self.invoke_callback
        )

        self.unexpected_error_fallback_handler = UnexpectedErrorFallbackHandler(
            handle_unexpected_error=self.handle_unexpected_error
        )

        self.get_recognition_result_handler = GetRecognitionResultHandler(
            get_recognition_result=self.get_recognition_result
        )
