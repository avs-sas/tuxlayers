"""Small module to print inforamtion about layer configuration."""

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import logging
import json
import os

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
    '--dot', '-d', required=False,
    type=click.Path(),
    help='Export the DAG to DOT format at the specified path.')
@click.option(
    '--paths', '-p', required=False,
    is_flag=False, flag_value='ALL', default=None,
    help='Identify unique paths from the root to the specified layer ID, or all nodes if no ID provided.')
@click.pass_context
def info(ctx, layers, config, tree, dot, paths):
    '''Prints information.'''
    if layers:
        print_layer_info(ctx)
    if config:
        print_configuration(ctx)
    if tree:
        print_tree_info(ctx)
    if dot:
        print_dot(ctx, dot)
    if paths:
        print_paths(ctx, paths)

    if not layers and not config and not tree and not dot and not paths:
        print_all_info(ctx)

def print_layer_info(ctx):
    """Prints available top-level layers"""
    logger.info("Available leafs:")
    for leaf in ctx.obj['LEAVES']:
        logger.info("- %s: %s", leaf.identifier, leaf.data.title)


def print_configuration(ctx):
    """Prints layer and patch configuration in use"""
    logger.info("Layer source in use:")
    logger.info("Path: %s", ctx.obj['LAYER_SOURCE'])
    logger.info("Layers found:")
    for layer in ctx.obj['LAYER_FILES']:
        logger.info("- %s", layer)

def print_tree_info(ctx):
    '''Prints the tree created by the layer configuration.'''
    need_layer_config(ctx)
    layer_tree = ctx.obj['LAYER_DAG']
    layer_tree.show()

def print_dot(ctx, dot_path):
    '''Exports the DAG to DOT.'''
    need_layer_config(ctx)
    layer_dag = ctx.obj['LAYER_DAG']
    layer_dag.to_dot(dot_path)

def print_paths(ctx, target_id):
    '''Prints all unique paths to a specific layer or all layers.'''
    need_layer_config(ctx)
    layer_dag = ctx.obj['LAYER_DAG']

    if target_id == 'ALL':
        logger.info("Printing paths for all nodes in the DAG:")
        for node_id in layer_dag.nodes:
            logger.info("Paths to layer '%s'", node_id)
            _print_paths_for_node(layer_dag, node_id)
    else:
        _print_paths_for_node(layer_dag, target_id)

def _print_paths_for_node(layer_dag, target_id):
    """Helper to print paths for a single node."""
    paths = layer_dag.get_all_paths(target_id)
    if not paths:
        logger.info("No paths found to layer '%s'", target_id)
    else:
        logger.info("Found %d unique path(s) to layer '%s':", len(paths), target_id)
        for i, path in enumerate(paths, 1):
            logger.info("Path %d: %s", i, " -> ".join(path))
            logger.info("   Use: -l %s", ",".join(path))

def print_all_info(ctx):
    """Prints all available information topics"""
    print_layer_info(ctx)
    print_configuration(ctx)
    print_tree_info(ctx)
