from collections import namedtuple
from functools import wraps
from http import HTTPStatus
from json import dumps
from uuid import uuid4

from .exception import CallbackUrlIsNotValid


Response = namedtuple('Response', ['body', 'status_code'])


def with_http_api_response_format(function):
    @wraps(function)
    def inner(*args, **kwargs):
        response = function(*args, **kwargs)
        return {
            'isBase64Encoded': False,
            'statusCode': response.status_code,
            'headers': {'Content-Type': 'application/json'},
            'body': dumps(response.body)
        }
    return inner


@with_http_api_response_format
def initialize_upload_listening_handler(
        event, context, initialize_upload_listening
        ):
    blob_id = str(uuid4())
    callback_url = get_callback_url_from_event(event)
    try:
        upload_url = initialize_upload_listening(blob_id, callback_url)
    except CallbackUrlIsNotValid as exception:
        return Response(
            body={
                'description': str(exception),
                'payload': exception.payload
            },
            status_code=HTTPStatus.BAD_REQUEST.value
        )
    return Response(
        body={
            'blob_id': blob_id,
            'callback_url': callback_url,
            'upload_url': upload_url
        },
        status_code=HTTPStatus.CREATED.value
    )


def get_callback_url_from_event(event):
    return event.get('body', {}).get('callback_url', '').strip()
