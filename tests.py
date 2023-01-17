import json
import unittest
from collections import namedtuple
from unittest.mock import Mock

from botocore.exceptions import ClientError
from requests import ConnectTimeout, ConnectionError

from app.container import Container
from app.domain import RecognitionStatus
from app.dto import UploadInitializingResult, Dto
from app.exception import (
    CallbackUrlIsNotValid,
    BlobWasNotFound,
    BlobIsNotUploadedYet,
    BlobUploadTimedOut,
    BlobRecognitionIsInProgress, InvalidBlobHasBeenUploaded, TooLargeBlobHasBeenUploaded, RecognitionStepHasBeenFailed
)
from app.usecase import UrlValidator, Invoker


ResponseMock = namedtuple('ResponseMock', ['status_code'])


class TestBlobS3Client(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.actual_client = Mock()
        self.bucket = 'bucket'
        self.ttl = 30
        self.key = 'key'

    def set_up_client(self):
        client = self.container.blob_s3_client
        client._client = self.actual_client
        client._bucket_name = self.bucket
        client._ttl = self.ttl
        return client

    def test_generating_presigned_url(self):
        link = 'link'
        self.actual_client.generate_presigned_url = Mock(return_value=link)
        client = self.set_up_client()

        client.generate_presigned_url(self.key)

        self.actual_client.generate_presigned_url.assert_called_with(
            'put_object',
            Params={
                'Bucket': self.bucket,
                'Key': self.key
            },
            ExpiresIn=self.ttl,
            HttpMethod='PUT'
        )

    def test_is_uploaded_successfully(self):
        self.actual_client.head_object = Mock(return_value=None)
        client = self.set_up_client()

        result = client.is_uploaded(self.key)

        self.actual_client.head_object.assert_called_with(
            Bucket=self.bucket,
            Key=self.key
        )
        self.assertTrue(result)

    def test_is_not_uploaded(self):
        self.actual_client.head_object = Mock(side_effect=ClientError({}, {}))
        client = self.set_up_client()

        result = client.is_uploaded(self.key)
        self.actual_client.head_object.assert_called_with(
            Bucket=self.bucket,
            Key=self.key
        )
        self.assertFalse(result)


class TestBlobDynamoDBClient(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.actual_client = Mock()
        self.table_name = 'table_name'

    def set_up_client(self):
        client = self.container.blob_dynamodb_client
        client._client = self.actual_client
        client._table_name = self.table_name
        return client

    def test_create(self):
        self.actual_client.put_item = Mock()
        client = self.set_up_client()

        blob_id = 'blob_id'
        callback_url = 'callback_url'
        status = 'status'
        client.create(blob_id, callback_url, status)

        self.actual_client.put_item.assert_called_with(
            TableName=self.table_name,
            Item={
                'blob_id': {'S': blob_id},
                'callback_url': {'S': callback_url},
                'status': {'S': status}
            }
        )

    def test_update_status(self):
        self.actual_client.update_item = Mock()
        client = self.set_up_client()

        blob_id = 'blob_id'
        status = 'status'
        client.update_status(blob_id, status)

        self.actual_client.update_item.assert_called_with(
            TableName=self.table_name,
            Key={'blob_id': {'S': blob_id}},
            UpdateExpression='SET #status = :status',
            ExpressionAttributeValues={
                ':status': {'S': status}
            },
            ExpressionAttributeNames={
                '#status': 'status'
            }
        )

    def test_save_labels(self):
        self.actual_client.update_item = Mock()
        client = self.set_up_client()

        blob_id = 'blob_id'
        labels = [{'label': '1', 'confidence': 100, 'parents': ['foo', 'bar']}]
        client.save_labels(blob_id, labels)

        self.actual_client.update_item.assert_called_with(
            TableName=self.table_name,
            Key={'blob_id': {'S': blob_id}},
            UpdateExpression='SET labels = :labels',
            ExpressionAttributeValues={
                ':labels': {
                    'L': [
                        {
                            'M': {
                                'label': {'S': '1'},
                                'confidence': {'N': '100'},
                                'parents': {'L': [{'S': 'foo'}, {'S': 'bar'}]}
                            }
                        }
                    ]
                }
            }
        )

    def test_get_existing_blob(self):
        blob_id = 'blob_id'
        callback_url = 'callback_url'
        status = 'status'
        actual_client_result = {
            'Item': {
                'blob_id': {'S': blob_id},
                'callback_url': {'S': callback_url},
                'status': {'S': status},
                'labels': {
                    'L': [
                        {
                            'M': {
                                'label': {'S': '1'},
                                'confidence': {'N': '100'},
                                'parents': {'L': [{'S': 'foo'}, {'S': 'bar'}]}
                            }
                        }
                    ]
                }
            }
        }
        self.actual_client.get_item = Mock(return_value=actual_client_result)
        client = self.set_up_client()

        blob = client.get_blob(blob_id)

        self.actual_client.get_item.assert_called_with(
            TableName=self.table_name,
            Key={
                'blob_id': {'S': blob_id}
            }
        )
        self.assertEqual(
            blob,
            {
                'blob_id': blob_id,
                'callback_url': callback_url,
                'status': status,
                'labels': [{'label': '1', 'confidence': 100, 'parents': ['foo', 'bar']}]
            }
        )

    def test_get_missing_blob(self):
        self.actual_client.get_item = Mock(return_value={})
        client = self.set_up_client()

        blob_id = 'blob_id'
        blob = client.get_blob(blob_id)

        self.actual_client.get_item.assert_called_with(
            TableName=self.table_name,
            Key={
                'blob_id': {'S': blob_id}
            }
        )
        self.assertIsNone(blob)


class TestUploadingStepFunctionClient(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.actual_client = Mock()
        self.arn = 'arn'

    def set_up_client(self):
        client = self.container.uploading_step_function_client
        client._client = self.actual_client
        client._state_machine_arn = self.arn
        return client

    def test_launch(self):
        self.actual_client.start_execution = Mock()
        client = self.set_up_client()

        blob_id = 'blob_id'
        client.launch(blob_id)

        self.actual_client.start_execution.assert_called_with(
            stateMachineArn=self.arn,
            name=f'uploading-execution-{blob_id}',
            input=json.dumps({'blob_id': blob_id})
        )

    def test_launch_with_specified_execution_name(self):
        self.actual_client.start_execution = Mock()
        client = self.set_up_client()

        blob_id = 'blob_id'
        execution_name = 'execution_name'
        client.launch(blob_id, execution_name)

        self.actual_client.start_execution.assert_called_with(
            stateMachineArn=self.arn,
            name=execution_name,
            input=json.dumps({'blob_id': blob_id})
        )


class TestBlobRekognitionClient(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.actual_client = Mock()
        self.bucket = 'bucket'
        self.max_labels = 10
        self.min_confidence = 50

    def set_up_client(self):
        client = self.container.blob_rekognition_client
        client._client = self.actual_client
        client._bucket_name = self.bucket
        client._max_labels = self.max_labels
        client._min_confidence = self.min_confidence
        return client

    def test_detect_labels(self):
        self.actual_client.detect_labels = Mock()
        client = self.set_up_client()

        blob_id = 'blob_id'
        client.detect_labels(blob_id)

        self.actual_client.detect_labels.assert_called_with(
            Image={
                'S3Object': {
                    'Bucket': self.bucket,
                    'Name': blob_id
                }
            },
            MaxLabels=self.max_labels,
            MinConfidence=self.min_confidence
        )

    def test_unsuccessful_labels_detection_due_to_invalid_blob_format(self):
        self.actual_client.exceptions = Mock()
        self.actual_client.exceptions.InvalidImageFormatException = TypeError
        self.actual_client.exceptions.ImageTooLargeException = ValueError
        self.actual_client.detect_labels = Mock(side_effect=self.actual_client.exceptions.InvalidImageFormatException)

        client = self.set_up_client()

        blob_id = 'blob_id'
        with self.assertRaises(InvalidBlobHasBeenUploaded) as cm:
            client.detect_labels(blob_id)
        exception = cm.exception
        self.assertEqual(str(exception), 'Invalid image format has been uploaded.')
        self.assertEqual(exception.payload, {'blob_id': blob_id})
        self.actual_client.detect_labels.assert_called_with(
            Image={
                'S3Object': {
                    'Bucket': self.bucket,
                    'Name': blob_id
                }
            },
            MaxLabels=self.max_labels,
            MinConfidence=self.min_confidence
        )

    def test_unsuccessful_labels_detection_due_to_too_large_blob(self):
        self.actual_client.exceptions = Mock()
        self.actual_client.exceptions.InvalidImageFormatException = TypeError
        self.actual_client.exceptions.ImageTooLargeException = ValueError
        self.actual_client.detect_labels = Mock(side_effect=self.actual_client.exceptions.ImageTooLargeException)

        client = self.set_up_client()

        blob_id = 'blob_id'
        with self.assertRaises(TooLargeBlobHasBeenUploaded) as cm:
            client.detect_labels(blob_id)
        exception = cm.exception
        self.assertEqual(str(exception), 'Too large image has been uploaded.')
        self.assertEqual(exception.payload, {'blob_id': blob_id})
        self.actual_client.detect_labels.assert_called_with(
            Image={
                'S3Object': {
                    'Bucket': self.bucket,
                    'Name': blob_id
                }
            },
            MaxLabels=self.max_labels,
            MinConfidence=self.min_confidence
        )


class TestInitializeUploadListening(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.blob_s3_client = Mock()
        self.blob_dynamodb_client = Mock()
        self.uploading_step_function_client = Mock()
        self.validator = UrlValidator()

    def set_up_use_case(self):
        use_case = self.container.initialize_upload_listening
        use_case._blob_s3_client = self.blob_s3_client
        use_case._blob_dynamodb_client = self.blob_dynamodb_client
        use_case._uploading_step_function_client = self.uploading_step_function_client
        use_case._validator = self.validator
        return use_case

    def test_passing_in_incorrect_url(self):
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        callback_url = 'foobar'

        with self.assertRaises(CallbackUrlIsNotValid) as cm:
            use_case(blob_id, callback_url)
        exception = cm.exception
        self.assertEqual(str(exception), 'Invalid callback url supplied.')
        self.assertEqual(exception.payload, {'callback_url': callback_url})

    def test_successful_call(self):
        upload_url = 'upload_url'
        self.blob_dynamodb_client.create = Mock()
        self.uploading_step_function_client.launch = Mock()
        self.blob_s3_client.generate_presigned_url = Mock(return_value=upload_url)
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        callback_url = 'http://foo.bar'
        result = use_case(blob_id, callback_url)

        self.assertEqual(
            result.as_dict(),
            {
                'blob_id': blob_id,
                'upload_url': upload_url,
                'callback_url': callback_url
            }
        )
        self.blob_dynamodb_client.create.assert_called_with(
            blob_id, callback_url, RecognitionStatus.WAITING_FOR_UPLOAD.value
        )
        self.uploading_step_function_client.launch.assert_called_with(blob_id)
        self.blob_s3_client.generate_presigned_url.assert_called_with(blob_id)


class TestCheckUploading(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.blob_s3_client = Mock()
        self.blob_dynamodb_client = Mock()

    def set_up_use_case(self):
        use_case = self.container.check_uploading
        use_case._blob_s3_client = self.blob_s3_client
        use_case._blob_dynamodb_client = self.blob_dynamodb_client
        return use_case

    def test_uploaded_blob(self):
        self.blob_s3_client.is_uploaded = Mock(return_value=True)
        self.blob_dynamodb_client.update_status = Mock()
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        use_case(blob_id)

        self.blob_s3_client.is_uploaded.assert_called_with(blob_id)
        self.blob_dynamodb_client.update_status.assert_not_called()

    def test_not_uploaded_blob(self):
        self.blob_s3_client.is_uploaded = Mock(return_value=False)
        self.blob_dynamodb_client.update_status = Mock()
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        use_case(blob_id)

        self.blob_s3_client.is_uploaded.assert_called_with(blob_id)
        self.blob_dynamodb_client.update_status.assert_called_with(
            blob_id, RecognitionStatus.UPLOAD_TIMED_OUT.value
        )


class TestStartRecognition(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.recognition_step_function_client = Mock()
        self.blob_dynamodb_client = Mock()

    def set_up_use_case(self):
        use_case = self.container.start_recognition
        use_case._recognition_step_function_client = self.recognition_step_function_client
        use_case._blob_dynamodb_client = self.blob_dynamodb_client
        return use_case

    def test_call(self):
        self.blob_dynamodb_client.update_status = Mock()
        self.recognition_step_function_client.launch = Mock()
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        use_case(blob_id)

        self.blob_dynamodb_client.update_status.assert_called_with(
            blob_id, RecognitionStatus.IN_PROGRESS.value
        )
        self.recognition_step_function_client.launch.assert_called_with(blob_id)


class TestGetLabels(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.blob_rekognition_client = Mock()
        self.blob_dynamodb_client = Mock()

    def set_up_use_case(self):
        use_case = self.container.get_labels
        use_case._blob_rekognition_client = self.blob_rekognition_client
        use_case._blob_dynamodb_client = self.blob_dynamodb_client
        return use_case

    def test_call(self):
        data = 'data'
        self.blob_rekognition_client.detect_labels = Mock(return_value=data)
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        result = use_case(blob_id)

        self.blob_rekognition_client.detect_labels.assert_called_with(blob_id)
        self.assertEqual(
            result.as_dict(),
            {
                'blob_id': blob_id,
                'labels': data
            }
        )

    def test_unsuccessful_call_due_to_invalid_blob_format(self):
        self.blob_rekognition_client.detect_labels = Mock(side_effect=InvalidBlobHasBeenUploaded(''))
        self.blob_dynamodb_client.update_status = Mock()
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        with self.assertRaises(RecognitionStepHasBeenFailed):
            use_case(blob_id)

        self.blob_rekognition_client.detect_labels.assert_called_with(blob_id)
        self.blob_dynamodb_client.update_status.assert_called_with(
            blob_id, RecognitionStatus.INVALID_BLOB_HAS_BEEN_UPLOADED.value
        )

    def test_unsuccessful_call_due_to_too_large_blob(self):
        self.blob_rekognition_client.detect_labels = Mock(side_effect=TooLargeBlobHasBeenUploaded(''))
        self.blob_dynamodb_client.update_status = Mock()
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        with self.assertRaises(RecognitionStepHasBeenFailed):
            use_case(blob_id)

        self.blob_rekognition_client.detect_labels.assert_called_with(blob_id)
        self.blob_dynamodb_client.update_status.assert_called_with(
            blob_id, RecognitionStatus.TOO_LARGE_BLOB_HAS_BEEN_UPLOADED.value
        )


class TestTransformLabels(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_call(self):
        use_case = self.container.transform_labels

        blob_id = 'blob_id'
        raw_labels_data = {
            'Labels': [
                {
                    'Name': 'foo',
                    'Confidence': 100,
                    'Parents': [
                        {'Name': 'bar'}
                    ]
                },

            ]
        }
        result = use_case(blob_id, raw_labels_data)

        self.assertEqual(
            {
                'blob_id': blob_id,
                'labels': [
                    {
                        'label': 'foo',
                        'confidence': 100,
                        'parents': ['bar']
                    }
                ]
            },
            result.as_dict()
        )


class TestSaveLabels(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.blob_dynamodb_client = Mock()

    def set_up_use_case(self):
        use_case = self.container.save_labels
        use_case._blob_dynamodb_client = self.blob_dynamodb_client
        return use_case

    def test_call(self):
        self.blob_dynamodb_client.save_labels = Mock()
        use_case = self.set_up_use_case()

        blob_id = 'blob_id'
        labels = [
            {
                'label': 'foo',
                'confidence': 100,
                'parents': ['bar']
            }
        ]

        result = use_case(blob_id, labels)

        self.blob_dynamodb_client.save_labels.assert_called_with(blob_id, labels)
        self.assertEqual(
            {
                'blob_id': blob_id,
                'labels': labels
            },
            result.as_dict()
        )


class TestInvoker(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.http_invoke = Mock()
        self.timeout = 10

    def set_up_invoker(self):
        invoker = self.container.invoker
        invoker._http_invoke = self.http_invoke
        invoker._timeout = self.timeout
        return invoker

    def test_successful_invocation(self):
        self.http_invoke = Mock(return_value=ResponseMock(status_code=204))
        invoker = self.set_up_invoker()

        url = 'foobar'
        data = {'baz': 'egg'}
        status = invoker.invoke(url, data)

        self.http_invoke.assert_called_with(url, json=data, timeout=self.timeout)
        self.assertEqual(status, invoker.SUCCESS)

    def test_failed_invocation_due_to_callback_failure(self):
        self.http_invoke = Mock(return_value=ResponseMock(status_code=200))
        invoker = self.set_up_invoker()

        url = 'foobar'
        data = {'baz': 'egg'}
        status = invoker.invoke(url, data)

        self.http_invoke.assert_called_with(url, json=data, timeout=self.timeout)
        self.assertEqual(status, invoker.CALLBACK_FAILURE)

    def test_failed_invocation_due_to_connection_timeout(self):
        self.http_invoke = Mock(side_effect=ConnectTimeout)
        invoker = self.set_up_invoker()

        url = 'foobar'
        data = {'baz': 'egg'}
        status = invoker.invoke(url, data)

        self.http_invoke.assert_called_with(url, json=data, timeout=self.timeout)
        self.assertEqual(status, invoker.CONNECTION_TIMEOUT)

    def test_failed_invocation_due_to_connection_error(self):
        self.http_invoke = Mock(side_effect=ConnectionError)
        invoker = self.set_up_invoker()

        url = 'foobar'
        data = {'baz': 'egg'}
        status = invoker.invoke(url, data)

        self.http_invoke.assert_called_with(url, json=data, timeout=self.timeout)
        self.assertEqual(status, invoker.CONNECTION_ERROR)


class TestInvokeCallback(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.blob_dynamodb_client = Mock()
        self.invoker = Mock()
        self.invoker.SUCCESS = Invoker.SUCCESS
        self.invoker.CALLBACK_FAILURE = Invoker.CALLBACK_FAILURE
        self.invoker.CONNECTION_TIMEOUT = Invoker.CONNECTION_TIMEOUT
        self.invoker.CONNECTION_ERROR = Invoker.CONNECTION_ERROR
        self.blob = {
            'blob_id': 'blob_id',
            'callback_url': 'callback_url'
        }

    def set_up_use_case(self):
        use_case = self.container.invoke_callback
        use_case._blob_dynamodb_client = self.blob_dynamodb_client
        use_case._invoker = self.invoker
        return use_case

    def test_successful_invocation(self):
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        self.blob_dynamodb_client.update_status = Mock()
        self.invoker.invoke = Mock(return_value=Invoker.SUCCESS)

        blob_id = 'blob_id'
        labels = []
        use_case = self.set_up_use_case()

        result = use_case(blob_id, labels)

        self.blob_dynamodb_client.get_blob.assert_called_with(blob_id)
        self.invoker.invoke.assert_called_with('callback_url', {'blob_id': blob_id, 'labels': labels})
        self.blob_dynamodb_client.update_status.assert_called_with(blob_id, RecognitionStatus.SUCCESS.value)
        self.assertEqual(
            {
                'blob_id': blob_id,
                'labels': labels
            },
            result.as_dict()
        )

    def test_failed_invocation_due_to_callback_failure(self):
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        self.blob_dynamodb_client.update_status = Mock()
        self.invoker.invoke = Mock(return_value=Invoker.CALLBACK_FAILURE)

        blob_id = 'blob_id'
        labels = []
        use_case = self.set_up_use_case()

        result = use_case(blob_id, labels)

        self.blob_dynamodb_client.get_blob.assert_called_with(blob_id)
        self.invoker.invoke.assert_called_with('callback_url', {'blob_id': blob_id, 'labels': labels})
        self.blob_dynamodb_client.update_status.assert_called_with(blob_id, RecognitionStatus.FAILED_DUE_TO_CALLBACK_FAILURE.value)
        self.assertEqual(
            {
                'blob_id': blob_id,
                'labels': labels
            },
            result.as_dict()
        )

    def test_failed_invocation_due_to_connection_timeout(self):
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        self.blob_dynamodb_client.update_status = Mock()
        self.invoker.invoke = Mock(return_value=Invoker.CONNECTION_TIMEOUT)

        blob_id = 'blob_id'
        labels = []
        use_case = self.set_up_use_case()

        result = use_case(blob_id, labels)

        self.blob_dynamodb_client.get_blob.assert_called_with(blob_id)
        self.invoker.invoke.assert_called_with('callback_url', {'blob_id': blob_id, 'labels': labels})
        self.blob_dynamodb_client.update_status.assert_called_with(blob_id, RecognitionStatus.FAILED_DUE_TO_CALLBACK_TIME_OUT.value)
        self.assertEqual(
            {
                'blob_id': blob_id,
                'labels': labels
            },
            result.as_dict()
        )

    def test_failed_invocation_due_to_connection_error(self):
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        self.blob_dynamodb_client.update_status = Mock()
        self.invoker.invoke = Mock(return_value=Invoker.CONNECTION_ERROR)

        blob_id = 'blob_id'
        labels = []
        use_case = self.set_up_use_case()

        result = use_case(blob_id, labels)

        self.blob_dynamodb_client.get_blob.assert_called_with(blob_id)
        self.invoker.invoke.assert_called_with('callback_url', {'blob_id': blob_id, 'labels': labels})
        self.blob_dynamodb_client.update_status.assert_called_with(blob_id, RecognitionStatus.FAILED_DUE_TO_CALLBACK_CONNECTION.value)
        self.assertEqual(
            {
                'blob_id': blob_id,
                'labels': labels
            },
            result.as_dict()
        )


class TestGetRecognitionResult(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)
        self.blob_dynamodb_client = Mock()
        self.blob = {
            'blob_id': 'blob_id',
            'labels': []
        }

    def set_up_use_case(self):
        use_case = self.container.get_recognition_result
        use_case._blob_dynamodb_client = self.blob_dynamodb_client
        return use_case

    def test_successful_result_retrieving(self):
        self.blob['status'] = RecognitionStatus.SUCCESS.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        result = use_case('blob_id')

        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')
        self.assertEqual(
            {'blob_id': 'blob_id', 'labels': []},
            result.as_dict()
        )

    def test_successful_result_retrieving_but_callback_failed(self):
        self.blob['status'] = RecognitionStatus.FAILED_DUE_TO_CALLBACK_FAILURE.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        result = use_case('blob_id')

        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')
        self.assertEqual(
            {'blob_id': 'blob_id', 'labels': []},
            result.as_dict()
        )

    def test_successful_result_retrieving_but_callback_failed_due_to_time_out(self):
        self.blob['status'] = RecognitionStatus.FAILED_DUE_TO_CALLBACK_TIME_OUT.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        result = use_case('blob_id')

        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')
        self.assertEqual(
            {'blob_id': 'blob_id', 'labels': []},
            result.as_dict()
        )

    def test_successful_result_retrieving_but_callback_failed_due_to_connection(self):
        self.blob['status'] = RecognitionStatus.FAILED_DUE_TO_CALLBACK_CONNECTION.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        result = use_case('blob_id')

        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')
        self.assertEqual(
            {'blob_id': 'blob_id', 'labels': []},
            result.as_dict()
        )

    def test_unsuccessful_result_retrieving_for_non_existent_blob(self):
        self.blob_dynamodb_client.get_blob = Mock(return_value=None)
        use_case = self.set_up_use_case()

        with self.assertRaises(BlobWasNotFound) as cm:
            use_case('blob_id')

        exception = cm.exception
        self.assertEqual('Blob not found.', str(exception))
        self.assertEqual(
            {'blob_id': 'blob_id', 'status': RecognitionStatus.NOT_FOUND.value},
            exception.payload
        )
        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')

    def test_unsuccessful_result_retrieving_for_blob_waiting_for_upload(self):
        self.blob['status'] = RecognitionStatus.WAITING_FOR_UPLOAD.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        with self.assertRaises(BlobIsNotUploadedYet) as cm:
            use_case('blob_id')

        exception = cm.exception
        self.assertEqual('Blob hasn\'t been uploaded yet.', str(exception))
        self.assertEqual(
            {'blob_id': 'blob_id', 'status': RecognitionStatus.WAITING_FOR_UPLOAD.value},
            exception.payload
        )
        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')

    def test_unsuccessful_result_retrieving_for_blob_with_timed_out_upload(self):
        self.blob['status'] = RecognitionStatus.UPLOAD_TIMED_OUT.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        with self.assertRaises(BlobUploadTimedOut) as cm:
            use_case('blob_id')

        exception = cm.exception
        self.assertEqual('Blob upload is timed out.', str(exception))
        self.assertEqual(
            {'blob_id': 'blob_id', 'status': RecognitionStatus.UPLOAD_TIMED_OUT.value},
            exception.payload
        )
        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')

    def test_unsuccessful_result_retrieving_for_blob_in_progress(self):
        self.blob['status'] = RecognitionStatus.IN_PROGRESS.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        with self.assertRaises(BlobRecognitionIsInProgress) as cm:
            use_case('blob_id')

        exception = cm.exception
        self.assertEqual('Recognition is in progress.', str(exception))
        self.assertEqual(
            {'blob_id': 'blob_id', 'status': RecognitionStatus.IN_PROGRESS.value},
            exception.payload
        )
        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')

    def test_unsuccessful_result_retrieving_for_invalid_uploaded_blob(self):
        self.blob['status'] = RecognitionStatus.INVALID_BLOB_HAS_BEEN_UPLOADED.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        with self.assertRaises(InvalidBlobHasBeenUploaded) as cm:
            use_case('blob_id')

        exception = cm.exception
        self.assertEqual('Invalid image format has been uploaded.', str(exception))
        self.assertEqual(
            {'blob_id': 'blob_id', 'status': RecognitionStatus.INVALID_BLOB_HAS_BEEN_UPLOADED.value},
            exception.payload
        )
        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')

    def test_unsuccessful_result_retrieving_for_too_large_blob(self):
        self.blob['status'] = RecognitionStatus.TOO_LARGE_BLOB_HAS_BEEN_UPLOADED.value
        self.blob_dynamodb_client.get_blob = Mock(return_value=self.blob)
        use_case = self.set_up_use_case()

        with self.assertRaises(TooLargeBlobHasBeenUploaded) as cm:
            use_case('blob_id')

        exception = cm.exception
        self.assertEqual('Too large image has been uploaded.', str(exception))
        self.assertEqual(
            {'blob_id': 'blob_id', 'status': RecognitionStatus.TOO_LARGE_BLOB_HAS_BEEN_UPLOADED.value},
            exception.payload
        )
        self.blob_dynamodb_client.get_blob.assert_called_with('blob_id')


class TestInitializeUploadListeningLambda(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_successful_initializing(self):
        blob_id = 'blob_id'
        callback_url = 'callback_url'
        upload_url = 'upload_url'
        initialize_upload_listening_handler = self.container.initialize_upload_listening_handler
        initialize_upload_listening_handler._id_generator = Mock(
            return_value=blob_id
        )
        initialize_upload_listening_handler._initialize_upload_listening = Mock(
            return_value=(
                UploadInitializingResult(
                    blob_id=blob_id,
                    upload_url=upload_url,
                    callback_url=callback_url
                )
            )
        )

        body = json.dumps({'callback_url': callback_url})
        result = initialize_upload_listening_handler.handle(
            {'body': body}, {}
        )

        self.assertEqual(
            {
                'isBase64Encoded': False,
                'statusCode': 201,
                'headers': {'Content-Type': 'application/json'},
                'body': ({
                    'blob_id': blob_id,
                    'callback_url': callback_url,
                    'upload_url': upload_url
                })
            },
            {**result, 'body': json.loads(result['body'])}
        )
        initialize_upload_listening_handler._id_generator.assert_called_with()
        initialize_upload_listening_handler._initialize_upload_listening.assert_called_with(blob_id, callback_url)

    def test_unsuccessful_upload_initializing(self):
        blob_id = 'blob_id'
        callback_url = 'callback_url'
        initialize_upload_listening_handler = self.container.initialize_upload_listening_handler
        initialize_upload_listening_handler._id_generator = Mock(
            return_value=blob_id
        )
        initialize_upload_listening_handler._initialize_upload_listening = Mock(
            side_effect=CallbackUrlIsNotValid(
                message='Invalid callback url supplied.',
                payload={'callback_url': callback_url}
            )
        )

        body = json.dumps({'callback_url': callback_url})
        result = initialize_upload_listening_handler.handle({'body': body}, {})

        self.assertEqual(
            {
                'isBase64Encoded': False,
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': {
                    'description': 'Invalid callback url supplied.',
                    'payload': {'callback_url': callback_url}
                }
            },
            {**result, 'body': json.loads(result['body'])}
        )
        initialize_upload_listening_handler._id_generator.assert_called_with()
        initialize_upload_listening_handler._initialize_upload_listening.assert_called_with(blob_id, callback_url)


class TestCheckUploadingHandler(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_invocation(self):
        check_uploading_handler = self.container.check_uploading_handler
        check_uploading_handler._check_uploading = Mock()

        blob_id = 'blob_id'
        event = {'blob_id': blob_id}
        check_uploading_handler.handle(event, {})

        check_uploading_handler._check_uploading.assert_called_with(blob_id)


class TestImageHasBeenUploadedHandler(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_invocation(self):
        image_has_been_uploaded_handler = self.container.image_has_been_uploaded_handler
        image_has_been_uploaded_handler._start_recognition = Mock()

        blob_id = 'blob_id'
        event = {'Records': [
            {
                's3': {
                    'object': {
                        'key': blob_id
                    }
                }
            }
        ]}
        image_has_been_uploaded_handler.handle(event, {})

        image_has_been_uploaded_handler._start_recognition.assert_called_with(blob_id)


class TestGetLabelsHandler(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_invocation(self):
        get_labels_handler = self.container.get_labels_handler
        get_labels_handler._get_labels = Mock(return_value=Dto())

        blob_id = 'blob_id'
        event = {'blob_id': blob_id}
        get_labels_handler.handle(event, {})

        get_labels_handler._get_labels.assert_called_with(blob_id)


class TestTransformLabelsHandler(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_invocation(self):
        transform_labels_handler = self.container.transform_labels_handler
        transform_labels_handler._transform_labels = Mock(return_value=Dto())

        blob_id = 'blob_id'
        labels = []
        event = {'blob_id': blob_id, 'labels': labels}
        transform_labels_handler.handle(event, {})

        transform_labels_handler._transform_labels.assert_called_with(blob_id, labels)


class TestSaveLabelsHandler(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_invocation(self):
        save_labels_handler = self.container.save_labels_handler
        save_labels_handler._save_labels = Mock(return_value=Dto())

        blob_id = 'blob_id'
        labels = []
        event = {'blob_id': blob_id, 'labels': labels}
        save_labels_handler.handle(event, {})

        save_labels_handler._save_labels.assert_called_with(blob_id, labels)


class TestInvokeCallbackHandler(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_invocation(self):
        invoke_callback_handler = self.container.invoke_callback_handler
        invoke_callback_handler._invoke_callback = Mock(return_value=Dto())

        blob_id = 'blob_id'
        labels = []
        event = {'blob_id': blob_id, 'labels': labels}
        invoke_callback_handler.handle(event, {})

        invoke_callback_handler._invoke_callback.assert_called_with(blob_id, labels)


class TestGetRecognitionResultHandler(unittest.TestCase):  # pragma: no cover

    def setUp(self):
        self.container = Container(testing_mode=True)

    def test_successful_invocation(self):
        get_recognition_result_handler = self.container.get_recognition_result_handler
        get_recognition_result_handler._get_recognition_result = Mock(return_value=Dto())

        blob_id = 'blob_id'
        event = {
            'pathParameters': {
                'blob_id': blob_id
            }
        }
        result = get_recognition_result_handler.handle(event, {})

        get_recognition_result_handler._get_recognition_result.assert_called_with(blob_id)
        self.assertEqual(
            {
                'isBase64Encoded': False,
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': {}
            },
            {**result, 'body': json.loads(result['body'])}
        )

    def test_unsuccessful_invocation(self):
        get_recognition_result_handler = self.container.get_recognition_result_handler
        get_recognition_result_handler._get_recognition_result = Mock(side_effect=BlobWasNotFound(''))

        blob_id = 'blob_id'
        event = {
            'pathParameters': {
                'blob_id': blob_id
            }
        }

        result = get_recognition_result_handler.handle(event, {})

        get_recognition_result_handler._get_recognition_result.assert_called_with(blob_id)
        self.assertEqual(
            {
                'isBase64Encoded': False,
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': {'description': '', 'payload': {}}
            },
            {**result, 'body': json.loads(result['body'])}
        )
