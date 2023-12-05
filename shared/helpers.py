'''Small helper functions shared across the application'''

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import logging
import sys
import os

logger = logging.getLogger(__name__)


def exit_application(message):
    '''Quits the application (with an optional message)'''
    if message:
        logger.info(message)
    logger.info("Exiting!")
    sys.exit(0)


def exit_with_error(message):
    '''Quits the application (with an optional message)'''
    if message:
        logger.error(message)
    logger.error("Exiting!")
    sys.exit(1)

def need_layer_config(ctx):
    '''Check if a layer configuration was found in the config path'''
    if not layer_config_exists(ctx):
        exit_with_error("No locations given for layer sources or layer configuration empty.")

def layer_config_exists(ctx):
    '''Check if we parsed a layer config'''
    return 'LAYER_SOURCE' in ctx.obj and 'LAYER_TREE' in ctx.obj and ctx.obj['LAYER_TREE'].root is not None

def remove_empty_folders(path, remove_base=True):
    'Function to recursively remove empty folders'

    if not os.path.isdir(path):
        exit_with_error("Need so pass a path into remove_empty_folders")

    dir_contents = os.listdir(path)
    if dir_contents:
        for entry in dir_contents:
            if os.path.isdir(os.path.join(path, entry)):
                remove_empty_folders(os.path.join(path, entry), True)

    dir_contents = os.listdir(path)
    if not dir_contents and remove_base:
        if remove_base:
            os.rmdir(path)
