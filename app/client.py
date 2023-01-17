import json

from botocore.exceptions import ClientError


class BlobS3Client:

    def __init__(self, client, bucket_name, ttl):
        self._client = client
        self._bucket_name = bucket_name
        self._ttl = ttl

    def generate_presigned_url(self, key):
        return self._client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': self._bucket_name,
                'Key': key
            },
            ExpiresIn=self._ttl,
            HttpMethod='PUT'
        )

    def is_uploaded(self, key):
        try:
            self._client.head_object(
                Bucket=self._bucket_name,
                Key=key
            )
            return True
        except ClientError:
            return False


class BlobDynamoDBClient:

    def __init__(self, client, table_name):
        self._client = client
        self._table_name = table_name

    def create(self, blob_id, callback_url, status):
        return self._client.put_item(
            TableName=self._table_name,
            Item={
                'blob_id': {'S': blob_id},
                'callback_url': {'S': callback_url},
                'status': {'S': status}
            }
        )

    def update_status(self, blob_id, status):
        return self._client.update_item(
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
        return self._client.update_item(
            TableName=self._table_name,
            Key={'blob_id': {'S': blob_id}},
            UpdateExpression='SET labels = :labels',
            ExpressionAttributeValues={
                ':labels': data
            }
        )

    def get_blob(self, blob_id):
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
                for label_item in item.get('labels').get('L')
            ]
        }
        return blob


class BlobStepFunctionClient:

    def __init__(self, client, state_machine_arn):
        self._client = client
        self._state_machine_arn = state_machine_arn

    def launch(self, blob_id, execution_name=None):
        if execution_name is None:
            execution_name = f'uploading-execution-{blob_id}'
        return self._client.start_execution(
            stateMachineArn=self._state_machine_arn,
            name=execution_name,
            input=json.dumps({'blob_id': blob_id})
        )


class BlobRekognitionClient:

    def __init__(self, client, bucket_name, max_labels, min_confidence):
        self._client = client
        self._bucket_name = bucket_name
        self._max_labels = max_labels
        self._min_confidence = min_confidence

    def detect_labels(self, blob_id):
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
