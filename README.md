# Staircase test task

## Task description

Create API for recognition of images. API should have 2 endpoints:
1. POST /blobs - should accept callback_url for receiving callback when recognition will be
ended, and return upload_url for uploading pictures
2. GET /blobs/{blob_id} - Should return information about recognition results for specified
blob
API should be done according to this OpenAPI specification https://gist.github.com/movsiienko/
e2f8bcffe1b9dc6c1cc21e6346fe7e78

Requirements:
1. You have to use Serverless framework for describing infrastructure. As a user I have to
be able to deploy service to any account with sls deploy. DO NOT USE SAM OR ANY
OTHER IaC tool.
2. Code should be written in python
3. It is okay to use any other AWS service

## Architecture

Solution overview is presented on the diagram below:

![alt text](https://www.dropbox.com/s/w57u7e6e7mp6xyc/staircase-test-task-architecture.jpg?dl=1)

1. **POST /blobs** triggers lambda that will:
    * generate pre-signed url for blob uploading (default ttl is 30 seconds);
    * start step function that observes blob uploading. If blob hasn't been uploaded, it will mark it as "not uploaded" (default delay before check is 40 seconds);
    * save blob info to the DynamoDB table.
2. Blob uploading triggers lambda that will start recognition step function. The steps are:
    * extract labels from the Rekognition service (default max_labels are 10 and min_confidence is 50);
    * normalize labels data;
    * save labels data;
    * invoke callback (default timeout is 10 seconds).
3. **GET /blobs/{blob_id}** will return recognition results in the callback request schema format.

## Notes

### Recognition status
Recognition process consists of several steps so system will track its current status. Here's the complete list:
* **waiting-for-upload** - pre-signed url has been generated but image hasn't been uploaded yet;
* **in-progress** - image has been uploaded and recognition process is in progress;
* **success** - recognition process completed successfully;
* **upload-timed-out** - blob upload has never been completed;
* **invalid-blob-has-been-uploaded** - invalid image format has been uploaded;
* **too-large-blob-has-been-uploaded** - too large image has been uploaded;
* **failed-due-to-callback-failure** - callback failed to return valid status code (but in this case recognition results still can be fetched from GET /blobs/{blob_id} API);
* **failed-due-to-callback-time-out** - callback invocation timeout exceeds the limit (but in this case recognition results still can be fetched from GET /blobs/{blob_id} API);
* **failed-due-to-callback-connection** - connection with callback can't be established (but in this case recognition results still can be fetched from GET /blobs/{blob_id} API);
* **unexpected-error** - unexpected error occurred while performing recognition.

Recognition status is stored in DynamoDB table and doesn't appear in the GET /blobs/{blob_id} API 'success' response schema (to match given OpenAPI specification), but it appears in GET /blobs/{blob_id} API 'failed' response schema.

### Callback format
Callback invoker expects callback to return 204 status code. If different status code is returned, 
blob status becomes "failed-due-to-callback-failure".

### Callback invocation errors
If invocation was unsuccessful, recognition process still will be treated as successful and results can be fetched from GET /blobs/{blob_id} API.

### Status code inconsistency
The task was completed with intent to match the proposed OpenApi spec as close as possible, so 404 status code in GET /blobs/{blob_id} API is used even when it doesn't match the actual recognition status.
For example, recognition process that failed due to invalid image uploaded still will return 404 status code instead of 422.

### Test coverage
Unit tests were written for each service.

![alt text](https://www.dropbox.com/s/bz8z4ovsw7lt6h5/coverage.png?dl=1)
