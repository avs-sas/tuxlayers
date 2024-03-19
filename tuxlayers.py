#!/usr/bin/env python
'''tuxlayers is used to maintain a hiearchy of
patches for git repos with submodules'''

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import glob
import logging
import os

import click
import coloredlogs
import treelib

from commands import baseline, info, patchset
from configuration.data import PatchLayer
from shared.helpers import exit_with_error

# Logging setup...
logger = logging.getLogger(__name__)


@click.group(
    help='''tuxlayers is used to maintain a hiearchy
    of patches for git repositories with submodules''')
# pass configuration via the context
@click.option(
    '--layersdir', '-d', required=False,
    type=click.Path(),
    default=os.path.join(os.path.dirname(os.path.realpath(__file__)), "config", "layers"),
    help='Folder that holds layer configuration. Defaults to config/layers above the executable.')
@click.option(
    '--log_level', '-L', required=False, default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR"],
                      case_sensitive=False),
    show_default=True,
    help='Set log level.')
@click.pass_context
def cli(ctx, log_level, layersdir):
    """This is run before all other commands;
    used to provide context content."""
    # activate logging first...
    coloredlogs.install(level=log_level, milliseconds=True)
    logger.info("Reading layer configuration from %s", layersdir)
    # now prepare config & pass it via context
    ctx.ensure_object(dict)
    if layersdir:
        ctx.obj['LAYER_SOURCE'] = layersdir
        ctx.obj['LAYER_TREE'] = parse_tree_from_layers(ctx)

        leaves = ctx.obj['LAYER_TREE'].leaves()

        ctx.obj['LEAVES'] = leaves
    else:
        logger.info("No layers selected. Continuing without them.")


def parse_tree_from_layers(ctx):
    '''load all json files found in the config
    folder that contain a valid layer config'''

    previous_dir = os.path.abspath(os.getcwd())
    layers_dir = ctx.obj['LAYER_SOURCE']

    if not os.path.isdir(layers_dir):
        exit_with_error("Layers dir invalid")
    os.chdir(layers_dir)

    layer_files = glob.glob("**/*.json", recursive=True)
    ctx.obj['LAYER_FILES'] = layer_files
    layers = {}
    base_layer = None

    os.chdir(previous_dir)

    for layer_file in layer_files:
        logger.info("Loading layer configuration from: %s", layer_file)
        layer_config = load_layer_config(layers_dir, layer_file)
        layer_id = layer_config.id
        if len(layer_config.parent) == 0:
            if base_layer is not None:
                exit_with_error(
                    '''Found duplicate base layer
                    in layer configuration: ''' + layer_file)
            base_layer = layer_config
        else:
            if layer_id in layers:
                exit_with_error(
                    "Found duplicate in layer configuration: " + layer_file)
            layers[layer_id] = layer_config

    layer_tree = treelib.Tree()
    if base_layer is None:
        return layer_tree
    layer_tree.create_node(base_layer.id, base_layer.id, data=base_layer)
    new_leaves = True
    while new_leaves:
        new_leaves = False
        leaves = layer_tree.leaves()
        # now we iterate though all leaves and check if we find a layer that
        # makes one of them as a parent.
        for leaf in leaves:
            for layer in layers.values():
                if layer.parent == leaf.data.id:
                    layer_tree.create_node(layer.id, layer.id,
                                           parent=leaf.data.id, data=layer)
                    new_leaves = True
    return layer_tree


def load_layer_config(config_folder, layer_filename):
    """Loads layer config for a given type"""
    layer_file = os.path.abspath(os.path.join(config_folder, layer_filename))
    if not os.path.isfile(layer_file):
        exit_with_error("Could not find " + layer_file)

    with open(layer_file, encoding='UTF-8') as json_content:
        # Further file processing goes here
        data_json = json_content.read()
        try:
            # pylint: disable=no-member
            data_layer = PatchLayer.from_json(data_json)
            return data_layer
        except ValueError as value_error:
            exit_with_error(value_error)
    return PatchLayer(id='', parent='', description='', title='')


cli.add_command(info.info)
cli.add_command(patchset.patchset)
cli.add_command(patchset.apply)
cli.add_command(patchset.document)
cli.add_command(baseline.listsubmodules)
cli.add_command(baseline.addbaseline)
cli.add_command(baseline.reverttobaseline)
cli.add_command(baseline.showbaselines)
cli.add_command(baseline.createpatches)

if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    cli()
