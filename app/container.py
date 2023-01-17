import os
from functools import partial

import boto3
import requests

from .client import BlobS3Client, BlobDynamoDBClient, BlobStepFunctionClient, BlobRekognitionClient
from .lambdas import CheckUploadingHandler, ImageHasBeenUploadedHandler, \
    GetLabelsHandler, TransformLabelsHandler, SaveLabelsHandler, InvokeCallbackHandler, \
    GetRecognitionResultHandler, uuid_generator, InitializeUploadListeningHandler
from .usecase import UrlValidator, InitializeUploadListening, CheckUploading, StartRecognition, GetLabels, \
    TransformLabels, SaveLabels, InvokeCallback, Invoker, GetRecognitionResult


BLOBS_BUCKET_NAME = os.environ.get('blobsBucketName')
BLOBS_TABLE_NAME = os.environ.get('blobsTableName')
PRESIGNED_URL_TTL = os.environ.get('presignedUrlTTL')
UPLOADING_WAITING_TIME = os.environ.get('uploadingWaitingTime')
UPLOADING_STEP_FUNCTION_ARN = os.environ.get('uploadingStepFunctionArn')
RECOGNITION_STEP_FUNCTION_ARN = os.environ.get('recognitionStepFunctionArn')


class Container:

    def __init__(self, *, testing_mode=False):

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
            ttl=PRESIGNED_URL_TTL
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
            max_labels=10,  # todo: move to env var
            min_confidence=50  # todo: move to env var
        )

        # services

        self.url_validator = UrlValidator()

        self.invoker = Invoker(
            http_invoke=requests.post,
            timeout=10  # todo: move to env var
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

        self.get_recognition_result_handler = GetRecognitionResultHandler(
            get_recognition_result=self.get_recognition_result
        )
