import os
from functools import partial

import boto3

from .client import BlobS3Client, BlobDynamoDBClient, UploadingStepFunctionClient
from .lambdas import initialize_upload_listening_handler, check_uploading_handler
from .usecase import UrlValidator, InitializeUploadListening, CheckUploading

BLOBS_BUCKET_NAME = os.environ.get('blobsBucketName')
BLOBS_TABLE_NAME = os.environ.get('blobsTableName')
PRESIGNED_URL_TTL = os.environ.get('presignedUrlTTL')
UPLOADING_WAITING_TIME = os.environ.get('uploadingWaitingTime')
UPLOADING_STEP_FUNCTION_ARN = os.environ.get('uploadingStepFunctionArn')

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

    container.uploading_step_function_client = UploadingStepFunctionClient(
        client=_step_function_client,
        state_machine_arn=UPLOADING_STEP_FUNCTION_ARN
    )

    # services

    container.url_validator = UrlValidator()

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

    # lambdas

    container.initialize_upload_listening_handler = partial(
        initialize_upload_listening_handler,
        initialize_upload_listening=container.initialize_upload_listening
    )

    container.check_uploading_handler = partial(
        check_uploading_handler,
        check_uploading=container.check_uploading
    )

    return container
