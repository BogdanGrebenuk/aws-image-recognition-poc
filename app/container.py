import os
from functools import partial

import boto3
import requests

from .client import BlobS3Client, BlobDynamoDBClient, BlobStepFunctionClient, BlobRekognitionClient
from .lambdas import initialize_upload_listening_handler, check_uploading_handler, image_has_been_uploaded_handler, \
    get_labels_handler, transform_labels_handler, save_labels_handler, invoke_callback_handler, \
    get_recognition_result_handler
from .usecase import UrlValidator, InitializeUploadListening, CheckUploading, StartRecognition, GetLabels, \
    TransformLabels, SaveLabels, InvokeCallback, Invoker, GetRecognitionResult

BLOBS_BUCKET_NAME = os.environ.get('blobsBucketName')
BLOBS_TABLE_NAME = os.environ.get('blobsTableName')
PRESIGNED_URL_TTL = os.environ.get('presignedUrlTTL')
UPLOADING_WAITING_TIME = os.environ.get('uploadingWaitingTime')
UPLOADING_STEP_FUNCTION_ARN = os.environ.get('uploadingStepFunctionArn')
RECOGNITION_STEP_FUNCTION_ARN = os.environ.get('recognitionStepFunctionArn')

_s3_client = boto3.client('s3')
_dynamodb_client = boto3.client('dynamodb')
_rekognition_client = boto3.client('rekognition')
_step_function_client = boto3.client('stepfunctions')


class _Container:
    ... # todo


def create_container():
    container = _Container()

    # clients

    container.blob_s3_client = BlobS3Client(
        client=_s3_client,
        bucket_name=BLOBS_BUCKET_NAME,
        ttl=PRESIGNED_URL_TTL
    )

    container.blob_dynamodb_client = BlobDynamoDBClient(
        client=_dynamodb_client,
        table_name=BLOBS_TABLE_NAME
    )

    container.uploading_step_function_client = BlobStepFunctionClient(
        client=_step_function_client,
        state_machine_arn=UPLOADING_STEP_FUNCTION_ARN
    )

    container.recognition_step_function_client = BlobStepFunctionClient(
        client=_step_function_client,
        state_machine_arn=RECOGNITION_STEP_FUNCTION_ARN
    )

    container.blob_rekognition_client = BlobRekognitionClient(
        client=_rekognition_client,
        bucket_name=BLOBS_BUCKET_NAME,
        max_labels=10,  # todo: move to env var
        min_confidence=50  # todo: move to env var
    )

    # services

    container.url_validator = UrlValidator()

    container.invoker = Invoker(
        http_invoke=requests.post,
        timeout=10  # todo: move to env var
    )

    # use cases

    container.initialize_upload_listening = InitializeUploadListening(
        blob_s3_client=container.blob_s3_client,
        blob_dynamodb_client=container.blob_dynamodb_client,
        uploading_step_function_client=container.uploading_step_function_client,
        validator=container.url_validator
    )

    container.check_uploading = CheckUploading(
        blob_s3_client=container.blob_s3_client,
        blob_dynamodb_client=container.blob_dynamodb_client
    )

    container.start_recognition = StartRecognition(
        recognition_step_function_client=container.recognition_step_function_client,
        blob_dynamodb_client=container.blob_dynamodb_client
    )

    container.get_labels = GetLabels(
        blob_rekognition_client=container.blob_rekognition_client
    )

    container.transform_labels = TransformLabels()

    container.save_labels = SaveLabels(
        blob_dynamodb_client=container.blob_dynamodb_client
    )

    container.invoke_callback = InvokeCallback(
        blob_dynamodb_client=container.blob_dynamodb_client,
        invoker=container.invoker
    )

    container.get_recognition_result = GetRecognitionResult(
        blob_dynamodb_client=container.blob_dynamodb_client
    )

    # lambdas

    container.initialize_upload_listening_handler = partial(
        initialize_upload_listening_handler,
        initialize_upload_listening=container.initialize_upload_listening
    )

    container.check_uploading_handler = partial(
        check_uploading_handler,
        check_uploading=container.check_uploading
    )

    container.image_has_been_uploaded_handler = partial(
        image_has_been_uploaded_handler,
        start_recognition=container.start_recognition
    )

    container.get_labels_handler = partial(
        get_labels_handler,
        get_labels=container.get_labels
    )

    container.transform_labels_handler = partial(
        transform_labels_handler,
        transform_labels=container.transform_labels
    )

    container.save_labels_handler = partial(
        save_labels_handler,
        save_labels=container.save_labels
    )

    container.invoke_callback_handler = partial(
        invoke_callback_handler,
        invoke_callback=container.invoke_callback
    )

    container.get_recognition_result_handler = partial(
        get_recognition_result_handler,
        get_recognition_result=container.get_recognition_result
    )

    return container
