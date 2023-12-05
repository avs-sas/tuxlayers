"""Small module to print inforamtion about layer configuration."""

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import logging
import json

import click

from shared.helpers import need_layer_config

# Logging setup...
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    '--layers', '-l', is_flag=True, required=False,
    type=click.BOOL, default=False, help='Show available layers')
@click.option(
    '--config', '-c', is_flag=True, required=False,
    type=click.BOOL, default=False, help='Show configuration file in use')
@click.option(
    '--tree', '-t', is_flag=True, required=False,
    type=click.BOOL, default=False, help='Show created tree structure from parsed layer files')
@click.option(
    '-treeformat', '-f', show_default=True, default="display",
    type=click.Choice([
        "display", "json", "graphviz"
    ], case_sensitive=True), help='Display format for the layer tree')
@click.pass_context
def info(ctx, layers, config, tree, treeformat):
    '''Prints information.'''
    if layers:
        print_layer_info(ctx)
    if config:
        print_configuration(ctx)
    if tree:
        print_tree_info(ctx, treeformat)

    if not layers and not config and not tree:
        print_all_info(ctx, treeformat)

def print_layer_info(ctx):
    """Prints available top-level layers"""
    logger.info("Available leafs:")
    for leaf in ctx.obj['LEAVES']:
        logger.info("- %s: %s", leaf.tag, leaf.data.title)


def print_configuration(ctx):
    """Prints layer and patch configuration in use"""
    logger.info("Layer source in use:")
    logger.info("Path: %s", ctx.obj['LAYER_SOURCE'])
    logger.info("Layers found:")
    for layer in ctx.obj['LAYER_FILES']:
        logger.info("- %s", layer)

def print_tree_info(ctx, treeformat):
    '''Prints the tree created by the layer configuration.'''
    need_layer_config(ctx)
    layer_tree = ctx.obj['LAYER_TREE']
    match treeformat:
        case "display":
            layer_tree.show()
        case "json":
            print(json.dumps(json.loads(layer_tree.to_json()), indent=2))
        case "graphviz":
            layer_tree.to_graphviz()

def print_all_info(ctx, treeformat):
    """Prints all available information topics"""
    print_layer_info(ctx)
    print_configuration(ctx)
    print_tree_info(ctx, treeformat)
