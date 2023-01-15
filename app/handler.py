from .container import create_container


container = create_container()


initialize_upload_listening_handler = container.initialize_upload_listening_handler
check_uploading_handler = container.check_uploading_handler


def image_has_been_uploaded_handler(event, context):
    print(event)
