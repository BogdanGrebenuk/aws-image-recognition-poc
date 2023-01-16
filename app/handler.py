from .container import create_container


container = create_container()

# todo: add Catch flow to the step functions

initialize_upload_listening_handler = container.initialize_upload_listening_handler
check_uploading_handler = container.check_uploading_handler
image_has_been_uploaded_handler = container.image_has_been_uploaded_handler
get_labels_handler = container.get_labels_handler
transform_labels_handler = container.transform_labels_handler
save_labels_handler = container.save_labels_handler
invoke_callback_handler = container.invoke_callback_handler
