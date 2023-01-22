"""Module with simple wrappers for AWS clients."""

import json

from botocore.exceptions import ClientError

from app.exception import InvalidBlobHasBeenUploaded, TooLargeBlobHasBeenUploaded


class BlobS3Client:
    """Simple wrapper for S3 client.

    Puts facade in front of actual client and provides
    simple interface to communicate with S3.

    Attributes:
        _client (obj): Actual client, object that implements boto3.client('s3') interface.
        _bucket_name (str):  Name of the bucket.
        _ttl (int): Number of seconds after which pre-signed url will expire.

    """

    def __init__(self, client, bucket_name, ttl):
        """Object initializer.

        Args:
            client (obj): Actual client, object that implements boto3.client('s3') interface.
            bucket_name (str):  Name of the bucket.
            ttl (int): Number of seconds after which pre-signed url will expire.

        """
        self._client = client
        self._bucket_name = bucket_name
        self._ttl = ttl

    def generate_presigned_url(self, key):
        """Generates pre-singed url for blob uploading.

        Args:
            key (str): S3 resource key where blob should be uploaded.

        Returns:
            str: Pre-signed URL.

        """
        return self._client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': self._bucket_name,
                'Key': key,
                'ContentType': 'application/octet-stream'
            },
            ExpiresIn=self._ttl,
            HttpMethod='PUT'
        )

    def is_uploaded(self, key):
        """Returns S3 resource upload status for specified key.

         Args:
             key (str): S3 resource key.

         Returns:
             bool: Whether blob has been uploaded or not.

         """
        try:
            self._client.head_object(
                Bucket=self._bucket_name,
                Key=key
            )
            return True
        except ClientError:
            return False


class BlobDynamoDBClient:
    """Simple wrapper for DynamoDB client.

    Puts facade in front of actual client and provides
    simple interface to communicate with DynamoDB.

    Attributes:
        _client (obj): Actual client, object that implements boto3.client('dynamodb') interface.
        _table_name (str):  Name of the table.

    """

    def __init__(self, client, table_name):
        """Object initializer.

        Args:
            client (obj): Actual client, object that implements boto3.client('dynamodb') interface.
            table_name (str):  Name of the table.

        """
        self._client = client
        self._table_name = table_name

    def create(self, blob_id, callback_url, status):
        """Creates new table item.

        Args:
            blob_id (str): Item ID (simple primary key).
            callback_url (str): Callback that will be invoked after recognition.
            status (str): Recognition status.

        """
        self._client.put_item(
            TableName=self._table_name,
            Item={
                'blob_id': {'S': blob_id},
                'callback_url': {'S': callback_url},
                'status': {'S': status}
            }
        )

    def update_status(self, blob_id, status):
        """Update item status.

        Args:
            blob_id (str): Item ID (simple primary key).
            status (str): Recognition status.

        """
        self._client.update_item(
            TableName=self._table_name,
            Key={'blob_id': {'S': blob_id}},
            UpdateExpression='SET #status = :status',
            ExpressionAttributeValues={
                ':status': {'S': status}
            },
            ExpressionAttributeNames={
                '#status': 'status'
            }
        )

    def save_labels(self, blob_id, labels):
        """Save labels to the item.

        Args:
            blob_id (str): Item ID (simple primary key).
            labels (list): List of labels to be saved.

        """
        data = {
            'L': [
                {
                    'M': {
                        'label': {'S': item['label']},
                        'confidence': {'N': str(item['confidence'])},
                        'parents': {'L': [{'S': i} for i in item['parents']]}
                    }
                }
                for item in labels
            ]
        }
        self._client.update_item(
            TableName=self._table_name,
            Key={'blob_id': {'S': blob_id}},
            UpdateExpression='SET labels = :labels',
            ExpressionAttributeValues={
                ':labels': data
            }
        )

    def get_blob(self, blob_id):
        """Returns blob by its ID.

        Args:
            blob_id (str): Item ID (simple primary key).

        Returns:
            Fetched blob if found, None otherwise

        """
        response = self._client.get_item(
            TableName=self._table_name,
            Key={
                'blob_id': {'S': blob_id}
            }
        )
        item = response.get('Item')
        if item is None:
            return None
        blob = {
            'blob_id': item.get('blob_id').get('S'),
            'callback_url': item.get('callback_url').get('S'),
            'status': item.get('status').get('S'),
            'labels': [
                {
                    'label': label_item.get('M').get('label').get('S'),
                    'confidence': float(label_item.get('M').get('confidence').get('N')),
                    'parents': [parent.get('S') for parent in label_item.get('M').get('parents').get('L')]
                }
                for label_item in item.get('labels', {}).get('L', [])
            ]
        }
        return blob


class BlobStepFunctionClient:
    """Simple wrapper for StepFunction client.

    Puts facade in front of actual client and provides
    simple interface to communicate with StepFunction.

    Attributes:
        _client (obj): Actual client, object that implements boto3.client('stepfunctions') interface.
        _state_machine_arn (str):  ARN of the state machine to launch.

    """

    def __init__(self, client, state_machine_arn):
        """Object initializer.

        Args:
            client (obj): Actual client, object that implements boto3.client('stepfunctions') interface.
            state_machine_arn (str):  ARN of the state machine to launch.

        """
        self._client = client
        self._state_machine_arn = state_machine_arn

    def launch(self, blob_id):
        """Starts state machine execution.

        Execution name will be the same as passed in blob_id.
        Passes in input the object with blob_id key (as json string).

        Args:
            blob_id: Item ID to recognize.

        """
        return self._client.start_execution(
            stateMachineArn=self._state_machine_arn,
            name=blob_id,
            input=json.dumps({'blob_id': blob_id})
        )


class BlobRekognitionClient:
    """Simple wrapper for Rekognition client.

    Puts facade in front of actual client and provides
    simple interface to communicate with Rekognition.

    Attributes:
        _client (obj): Actual client, object that implements boto3.client('rekognition') interface.
        _bucket_name (str): Name of the bucket from which Rekognition will get image.
        _max_labels (int): Max number of labels to detect while recognition.
        _min_confidence (int): Min amount of confidence for recognition.

    """

    def __init__(self, client, bucket_name, max_labels, min_confidence):
        """Object initializer.

        Args:
            client (obj): Actual client, object that implements boto3.client('rekognition') interface.
            bucket_name (str): Name of the bucket from which Rekognition will get image.
            max_labels (int): Max number of labels to detect while recognition.
            min_confidence (int): Min amount of confidence for recognition.

        """
        self._client = client
        self._bucket_name = bucket_name
        self._max_labels = max_labels
        self._min_confidence = min_confidence

    def detect_labels(self, blob_id):
        """Returns recognition result.

        Args:
            blob_id (str): Item ID.

        Returns:
            List of labels.

        Raises:
            InvalidBlobHasBeenUploaded: If invalid image format has been uploaded.
            TooLargeBlobHasBeenUploaded: If too large image has been uploaded.

        """
        try:
            return self._client.detect_labels(
                Image={
                    'S3Object': {
                        'Bucket': self._bucket_name,
                        'Name': blob_id
                    }
                },
                MaxLabels=self._max_labels,
                MinConfidence=self._min_confidence
            )
        except self._client.exceptions.InvalidImageFormatException as e:
            raise InvalidBlobHasBeenUploaded(
                message='Invalid image format has been uploaded.',
                payload={'blob_id': blob_id}
            )
        except self._client.exceptions.ImageTooLargeException as e:
            raise TooLargeBlobHasBeenUploaded(
                message='Too large image has been uploaded.',
                payload={'blob_id': blob_id}
            )
